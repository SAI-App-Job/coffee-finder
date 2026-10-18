# -*- coding: utf-8 -*-
"""
scrape_cafecompany.py

カフェカンパニー(Cafe Company、山口県岩国市南岩国町1丁目17-45)の楽天市場店
(www.rakuten.co.jp/cafecom6100)の商品情報を取得する。
楽天市場(item.rakuten.co.jp、UTF-8)。

【楽天市場店を採用した理由】
公式(goope)・BASE(cafecom.base.shop)・楽天・Yahooを2026-10-15に確認した。
BASEは「100g×3種セット」「ギフトセット」「ドリップバッグ」「カレンダー」のみで豆の単品が無い。
Yahoo!ショッピングは商品ページ(beans001.html)が404で、店舗トップからも商品が取得できなかった。
楽天市場店は「世界各国の珈琲豆」カテゴリ(c/0000000122)に豆の単品9銘柄(調査時は10銘柄だったが、イエメン モカマタリが掲載終了)があり、
各商品ページに100g/200g/500g × 豆のまま/挽き(中挽き・細挽き・粗挽き)のSKU情報
(価格・ロースト度合い・原産地)が埋め込まれているため、これを採用する。

【対象商品について】
除外: 飲み比べセット・お試し・福袋(compass1767084688, tennchoset600/900, otanoshimi-002)、
ブレンド4種選択の1kgセット(blend100)、ギフト(gift*, specialty*, blend-can, compass1762073944)、
ドリップバッグ・ドリップパック(drip*)、アイスコーヒー、器具。
各銘柄は100g/200g/500gのSKUがあり、最小重量の100g・豆のままの価格(税込、メール便送料込み表記)を代表とする。
在庫はitemprop="availability"(商品単位)。「【欠品中】」表記のイエメン モカマタリはOutOfStock。
ロースト度合いは各SKUの商品属性(ミディアム/ハイ/シティ/フルシティ)、焙煎度の呼称は商品名の
「中浅煎り」「中煎り」等から取る。
販売業者(特定商取引法・商品情報): (有)オフィスカワムラ 山口県岩国市南岩国町1-17-45。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "カフェカンパニー",
    "url": "https://www.rakuten.co.jp/cafecom6100/",
    "platform": "楽天市場",
    "address": "山口県岩国市南岩国町1丁目17-45",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/cafecom6100/)の世界各国の珈琲豆カテゴリと各商品ページ(SKU情報)を2026-10-15に確認。公式(goope)・BASE・Yahoo!は豆の単品が取得できないため不採用",
    "last_verified_at": "2026-10-15",
}

SHOP_ID = "cafecom6100"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 1.5

# (商品コード, 商品名(商品ページ題名の【 】内が取れない場合の既定), 精製(表記があれば))
# 商品名は題名の【 】内を優先する(店側が随時更新するため)。
# beans002(イエメン モカマタリ No.9)は2026-10-15時点で販売ページあり(欠品中)だったが、
# その後ページが404(掲載終了)となったため対象外。
ITEMS = [
    ("beans-el-200", "エルサルバドル SHG ジュリア Qグレード", None),
    ("beans001", "パプアニューギニア ワイルドハイランド", None),
    ("beans003", "コロンビア スプレモ", None),
    ("beans005", "タンザニア AA スノートップ", None),
    ("beans007", "ブラジル モジアナブレンド", None),
    ("beans008", "グアテマラ アルタルス農園 Qグレード", None),
    ("compass1766929071", "エチオピア モカ イルガチャフェ G2 ウォッシュド", None),
    ("mandheling", "インドネシア マンデリン G1", None),
    ("toraja200", "トラジャ ランテカルア 有機 JAS 栽培", None),
]

ATTR_ROAST = {
    "ライト": "ライトロースト", "シナモン": "シナモンロースト", "ミディアム": "ミディアムロースト",
    "ハイ": "ハイロースト", "シティ": "シティロースト", "フルシティ": "フルシティロースト",
    "フレンチ": "フレンチロースト", "イタリアン": "イタリアンロースト",
}
COARSE_ROASTS = ("中浅煎り", "中深煎り", "極深煎り", "浅煎り", "中煎り", "深煎り")
AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
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


def build_record(code: str, name: str, process: str | None) -> dict | None:
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    title = unicodedata.normalize("NFKC", soup.title.get_text(strip=True)) if soup.title else ""

    # 最小重量(100g)・豆のままのSKU
    cand = None
    for s in extract_skus(html_text):
        sel = s.get("selectorValues") or []
        attrs = {a["title"]: a.get("value") for a in s.get("attributes", [])}
        try:
            weight = int(float(attrs.get("総重量")))
        except (TypeError, ValueError):
            continue
        if not any(v.startswith("豆のまま") for v in sel):
            continue
        if cand is None or weight < cand[0]:
            cand = (weight, s, attrs)
    if cand is None:
        print(f"[warn] SKU情報なし: {code}")
        return None
    weight, sku, attrs = cand
    price = int(sku["taxIncludedPrice"])
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    roast_level = ATTR_ROAST.get(attrs.get("ロースト度合い") or "")
    title = title.replace("【楽天市場】", "")
    nm = re.search(r"【([^】]+)】", title)
    if nm:
        name = re.sub(r"\s+", " ", nm.group(1)).strip()
    desc_el = soup.select_one(".sale_desc")
    desc = unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True)) if desc_el else ""
    first_bullet = desc[desc.find("・"):][:60] if "・" in desc else ""
    first_bullet = first_bullet.replace("入り", "煎り")  # 「中深入り」等の誤記を補正
    roast_hint = next((r for r in COARSE_ROASTS if r in title or r in first_bullet), None)
    origin = attrs.get("コーヒー・茶の原料原産地")
    origin = {"グァテマラ": "グアテマラ"}.get(origin, origin)

    bullets = desc[desc.find("・"):] if "・" in desc else desc
    flavor = re.sub(r"\s+", " ", bullets)[:400] or None

    parsed = parse_product(name)
    parsed = apply_category_hint_fallback(parsed, name)
    detected = detect_country_name(name)
    if not origin:
        origin = parsed["origin_country"] or detected
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": "ストレート",
        "origin_country": origin,
        "origin_source": "shop_attribute",
        "designated_brand": parsed["designated_brand"],
        "processing_method": normalize_processing_method(process) if process else parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list[dict]:
    records = []
    for i, (code, name, process) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        rec = build_record(code, name, process)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafecompany.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafecompany.json に出力しました")


if __name__ == "__main__":
    main()
