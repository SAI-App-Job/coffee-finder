# -*- coding: utf-8 -*-
"""
scrape_minamiaoyamacoffee.py

南青山珈琲(オーガニックコーヒー豆専門店、札幌市清田区平岡2条3丁目4-11、運営 株式会社ミセル)の
楽天市場店(www.rakuten.co.jp/minamiaoyamacoffee/)の商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。

【販売先について】
公式サイト(organic-minamiaoyama-coffee.jp)は商品紹介のみで、購入はBASE(minamiaoyama.official.ec)または楽天市場店。
BASEは豆14品(ブレンド5・ストレート8・アイス用1、各200g)で楽天市場店とほぼ同数だが、公式・特商法に
「販売価格は税別(税込み)表記」「1,700円(税別)」とあり、BASEの表示価格が税別かどうか判別しづらいため、
税込価格が明示される楽天市場店を採用した(楽天は送料込み価格のため、BASEの表示価格より高めになる)。
BASE(https://minamiaoyama.official.ec/)にのみあるもの: グァテマラ。楽天にのみあるもの: エルサルバドル。

【対象商品について】
楽天市場店のオリジナルブレンド・ストレート・アイスコーヒーのうち、豆の単品(200g)14品。最小重量は200g
(各商品は 200g / 500g / 1kg の選択か、200g単品。100g設定は無い)。
除外: セット(おすすめブレンド3種・選べる飲み比べ・ブレンド4種セット)、2kg/1kg大容量セット、ギフト、ゼリー、ドリップパック。
 - 10000011(アイスコーヒー豆)と10000021(スペシャルブレンド)は SKU の 200g の価格を採用。他は200g単品(itemprop="price")。
 - 焙煎度は購入時に選択式(5〜10の6段階)のため roast_level は null、roast_selectable=True。
 - 商品ページの説明文は店全体の共通文面で個別の風味説明が無いため flavor_notes は null。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "南青山珈琲",
    "url": "https://www.rakuten.co.jp/minamiaoyamacoffee/",
    "platform": "楽天市場",
    "address": "北海道札幌市清田区平岡2条3丁目4-11",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/minamiaoyamacoffee/)のショップカテゴリと各商品ページ(SKU情報)を2026-10-20に確認。"
                   "公式サイト(https://www.organic-minamiaoyama-coffee.jp/)の店舗情報(札幌市清田区平岡2条3丁目4-11、10:00-14:00、火曜定休、ご注文後にお好みの焙煎度合いに仕上げ)。"
                   "特商法の販売業者(株式会社ミセル)所在地は同4-14",
    "last_verified_at": "2026-10-20",
}

SHOP_ID = "minamiaoyamacoffee"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')

# (商品コード, 商品名, SKUの選択肢に含まれるべき文字列(Noneは単品=SKUなし), 産地(Noneはブレンド))
ITEMS = [
    ("10000010", "オーガニック プレミアムブレンド", None, None),
    ("10000021", "オーガニック スペシャルブレンド", ["200g"], None),
    ("10000022", "オーガニック ドラゴンロード", None, None),
    ("10000026", "オーガニック 南青山ブレンド", None, None),
    ("10000024", "オーガニック 南JASブレンド", None, None),
    ("10000011", "オーガニック アイスコーヒー", ["200g"], None),
    ("10000023", "オーガニック ブラジル", None, "ブラジル"),
    ("10000032", "オーガニック コロンビア", None, "コロンビア"),
    ("10000025", "オーガニック エクアドル", None, "エクアドル"),
    ("10000027", "オーガニック メキシコ", None, "メキシコ"),
    ("10000029", "オーガニック ペルー", None, "ペルー"),
    ("10000031", "オーガニック エルサルバドル", None, "エルサルバドル"),
    ("10000028", "オーガニック マンデリン", None, "インドネシア"),
    ("10000009", "オーガニック モカ・シダモ", None, "エチオピア"),
]


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=HEADERS, timeout=90)
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


def build_record(code, name, sel, origin, html_text):
    price = None
    if sel is None:
        m = PRICE_PATTERN.search(html_text)
        price = int(m.group(1)) if m else None
    else:
        for s in extract_skus(html_text):
            vals = unicodedata.normalize("NFKC", " ".join(s.get("selectorValues") or []))
            if all(unicodedata.normalize("NFKC", k) in vals for k in sel):
                price = int(s["taxIncludedPrice"])
                break
    if price is None:
        print(f"[warn] 価格取得失敗: {code} {name}")
        return None
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    parsed = parse_product(name)
    if origin is None:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name"
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
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 200,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list:
    records = []
    for i, (code, name, sel, origin) in enumerate(ITEMS):
        if i:
            time.sleep(INTERVAL)
        resp = fetch(ITEM_URL.format(code=code))
        if resp.status_code != 200:
            print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
            continue
        rec = build_record(code, name, sel, origin, resp.text)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_minamiaoyamacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_minamiaoyamacoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
