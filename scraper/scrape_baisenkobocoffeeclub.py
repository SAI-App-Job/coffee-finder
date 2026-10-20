# -*- coding: utf-8 -*-
"""
scrape_baisenkobocoffeeclub.py

ばいせん工房珈琲倶楽部(大阪府羽曳野市栄町6-3 古市本店。2号店は道の駅しらとりの郷店)の
楽天市場店(www.rakuten.co.jp/baisen-coffee)の商品情報を取得する。
楽天市場(item.rakuten.co.jp、EUC-JP)。

【楽天市場店を採用した理由】
楽天市場店(https://www.rakuten.co.jp/baisen-coffee/)とYahoo!ショッピング店
(https://store.shopping.yahoo.co.jp/baisen-coffee/、326件)を2026-10-20に確認した。
Yahoo!ショッピング店は重量違いを別商品ページとして並べ(100g・200g・300g・400g…が別URL)、福袋・セット・
器具・雑貨も多数混在する。楽天市場店は1銘柄1ページに100g〜500gのSKU(価格つき)があり、
「特選豆(ストレート)」「シングルオリジンコーヒー」「特選豆(ブレンド)」カテゴリで豆の品目が揃っているため、
楽天市場店を採用し、Yahoo!ショッピング店は重複させない。

【対象商品について】
自家焙煎コーヒー豆(ストレート・ブレンド・デカフェ)のみ。各銘柄は最小重量(100g、100gが無い銘柄は最小SKU)の価格を代表とする。
除外: 1kg・2kg等の大容量ページ(*-20、*-10、2000等)、飲み比べ・お試しセット(mail-*、coffee-000*)、ブルマンブレンド3袋組(105-3)、
福袋、ドリップバッグ、アイスコーヒー液、黒豆珈琲(黒大豆入りのため)、器具・雑貨・菓子。
価格は税込。注記: 「当店は生豆時価格です。焙煎後の量目は10〜15%程度減少します」(商品ページ)とあり、
100g表記は生豆の重量での価格。ロースト度合い(ライト〜フルシティ、生豆)と挽き具合は購入時に選択する
(roast_selectable=True)。在庫は itemprop="availability"(商品単位)。
販売業者(特定商取引法): 株式会社ばいせん工房珈琲倶楽部 大阪府羽曳野市栄町6-3(古市本店)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "ばいせん工房珈琲倶楽部",
    "url": "https://www.rakuten.co.jp/baisen-coffee/",
    "platform": "楽天市場",
    "address": "大阪府羽曳野市栄町6-3",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/baisen-coffee/)のカテゴリ(特選豆ストレート・シングルオリジン・ブレンド)と各商品ページ(SKU情報)を2026-10-20に確認。"
                   "Yahoo!ショッピング店(store.shopping.yahoo.co.jp/baisen-coffee/)は重量違いが別ページで福袋等も混在するため不採用。"
                   "住所は楽天の会社概要と、タイガー珈琲「焙煎工房」店舗情報(http://tigercc.com/baisen/shopinfo/index.html)の古市本店。"
                   "価格は生豆時の重量の価格(焙煎後は10〜15%減)、焙煎度は購入時に選択",
    "last_verified_at": "2026-10-20",
}

SHOP_ID = "baisen-coffee"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')

# (商品コード, 商品名, 産地(Noneはブレンド), 単品の重量g(SKUが無いページのみ。SKUがあれば最小重量を自動採用))
ITEMS = [
    # 特選豆(ストレート)
    ("peru-", "ペルー", "ペルー", 100),
    ("st-14-1", "ブラジル ブルボン", "ブラジル", 100),
    ("st-15-1", "ブラジル ピーベリー", "ブラジル", 100),
    ("st-16-1", "ジャマイカ ブルーマウンテンNo.1", "ジャマイカ", 100),
    ("st-2-1", "インドモンスーン", "インド", 100),
    ("st-21-1-a", "モカマタリ アールマッカ", "イエメン", 100),
    ("st-25-1", "コロンビア ナリーニョ", "コロンビア", 100),
    ("st-36-1", "メキシコ", "メキシコ", 100),
    ("st-55-1", "ブラジル ハニー", "ブラジル", 100),
    ("143-2", "エメラルドマウンテン", "コロンビア", 100),
    ("381-2", "ブラジル サントスNo.2", "ブラジル", 100),
    ("st-56-2", "モカ レケンプティー", "エチオピア", 100),
    ("st-42-3", "ケニアAA", "ケニア", 100),
    ("st-53-3", "ブラジル ショコラ", "ブラジル", 100),
    ("161-5", "グアテマラ SHB", "グアテマラ", 100),
    ("171-5", "タンザニア キリマンジャロ AA", "タンザニア", 100),
    ("201-5", "コロンビア スプレモ", "コロンビア", 100),
    ("401-5", "ホンジュラス", "ホンジュラス", 100),
    ("411-5", "マンデリン G1", "インドネシア", 100),
    ("sanmarino", "ブラジル サンマリノ", "ブラジル", 100),
    ("st-4-5", "エチオピア シダモ", "エチオピア", 100),
    # デカフェ
    ("decafebura", "デカフェ ブラジル", "ブラジル", 100),
    ("decafecolom", "デカフェ コロンビア", "コロンビア", 100),
    ("decafeguate", "デカフェ グアテマラ", "グアテマラ", 100),
    ("decafemande", "デカフェ マンデリン", "インドネシア", 100),
    # シングルオリジンコーヒー
    ("164-2-a-t", "インドネシア ランテカルア G1", "インドネシア", 100),
    ("201-2-p", "コロンビア ピコ クリストバル スプレモ", "コロンビア", 100),
    ("antigua", "グアテマラ アンティグア APCA", "グアテマラ", 100),
    ("arco", "ブラジル アルコイリス NA", "ブラジル", 100),
    ("barahona", "ドミニカ バラオナ AA", "ドミニカ共和国", 100),
    ("bolivia", "ボリビア ビオ アラビカ", "ボリビア", 100),
    ("bragranreina", "ブラジル グランレイナ", "ブラジル", 100),
    ("caramelado", "ブラジル キャラメラード", "ブラジル", 100),
    ("casabla", "ニカラグア カツーラハニー カサブランカ農園", "ニカラグア", 100),
    ("egeisha", "エチオピア ゲイシャ G2 ウォッシュド", "エチオピア", 100),
    ("finca", "グアテマラ Finca Las Salinas", "グアテマラ", 100),
    ("hawaiicona", "ハワイコナ プライム", "アメリカ(ハワイ)", 100),
    ("higasicct", "東ティモール CCT", "東ティモール", 100),
    ("iemen9", "イエメン マタリ Pure 9", "イエメン", 100),
    ("ipanemacru", "ブラジル イパネマ農園 プレミアクリュ『ドライフルーツ』", "ブラジル", 100),
    ("jyagahani", "コスタリカ ジャガーハニー", "コスタリカ", 100),
    ("kiboab", "タンザニア AB キボー", "タンザニア", 100),
    ("kirihani", "タンザニア キリマンジャロ ハニー", "タンザニア", 100),
    ("kirimann", "タンザニア キリマンジャロ ナチュラル", "タンザニア", 100),
    ("maesasa", "パプアニューギニア マエササ A", "パプアニューギニア", 100),
    ("mandarina", "ペルー G1 フィンカ ラ・マンダリーナ", "ペルー", 100),
    ("oranji", "ニカラグア オレンジハニー N", "ニカラグア", 100),
    ("pacamara", "エルサルバドル パカマラ", "エルサルバドル", 100),
    ("raos", "ラオス アラビカ G1 ミン・ティエン農園", "ラオス", 100),
    ("rinton", "マンデリン G1 リントン", "インドネシア", 100),
    ("sanmigeru", "グアテマラ SHB サン・ミゲル農園", "グアテマラ", 100),
    ("st-ca", "ブラジル カフェ・ドルチェ", "ブラジル", 100),
    ("sweet", "コロンビア スウィート&フラワーズ", "コロンビア", 100),
    ("vetnam", "ベトナム アラビカ G1", "ベトナム", 100),
    ("wush", "エチオピア リム G1 ウシュウシュ W", "エチオピア", 100),
    # ブレンド
    ("104-1", "特選ブレンド", None, 100),
    ("109-2", "ティールームブレンド", None, 200),
    ("113", "はびきのシティーブレンド", None, 100),
    ("b-50-1", "エメラルドマウンテンブレンド", None, 100),
    ("bl-1-1", "アメリカンブレンド", None, 100),
    ("bl-12-1", "ロイヤルブレンド(しらとりの郷)", None, 100),
    ("karibu-1", "カリブ海ブレンド", None, 100),
    ("102-2", "コクのあるブレンド", None, 100),
    ("105-2", "ブルマンブレンド", None, 100),
    ("107-5", "モカブレンド", None, 100),
    ("siatoru", "シアトルブレンド", None, 100),
    ("st-32-1", "炭火焼コーヒー", None, 100),
    ("111ice", "アイスコーヒー特選", None, 100),
    ("112ice", "アイスコーヒーマイルド", None, 100),
    ("141-2", "エスプレッソイタリアン", None, 200),
]


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.encoding = "euc-jp"
    return resp


def extract_skus(html_text: str) -> list[dict]:
    """ページに埋め込まれた "sku":[...] のJSON配列を括弧対応で切り出す。"""
    i = html_text.find('"sku":[')
    if i < 0:
        return []
    start = i + len('"sku":')
    depth, in_str, esc = 0, False, False
    for k in range(start, len(html_text)):
        ch = html_text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == chr(92):
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html_text[start:k + 1])
    return []


def sku_weight(sku: dict):
    for v in sku.get("selectorValues") or []:
        m = re.search(r"(\d+)\s*g", unicodedata.normalize("NFKC", v).lower())
        if m and "×" not in v:
            return int(m.group(1))
    return None


def build_record(code: str, name: str, origin, single_weight: int):
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")

    skus = [(sku_weight(s), s) for s in extract_skus(html_text)]
    skus = [(w, s) for w, s in skus if w]
    if skus:
        weight, sku = min(skus, key=lambda x: x[0])
        price = int(sku["taxIncludedPrice"])
    else:
        m = PRICE_PATTERN.search(html_text)
        if not m:
            print(f"[warn] 価格取得失敗: {code} {name}")
            return None
        price, weight = int(m.group(1)), single_weight
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    desc_el = soup.select_one(".sale_desc")
    desc = unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True)) if desc_el else ""
    desc = re.sub(r"\s+", " ", desc)[:400] or None

    parsed = parse_product(name)
    if origin is None:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name" if origin.split("(")[0] in name else "shop_attribute"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_selectable": True,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list:
    records = []
    for i, (code, name, origin, w) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        rec = build_record(code, name, origin, w)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_baisenkobocoffeeclub.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_baisenkobocoffeeclub.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
