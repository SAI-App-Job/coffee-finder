# -*- coding: utf-8 -*-
"""
scrape_hiroshigecoffee.py

ひろしげ珈琲倶楽部(大阪府泉南郡岬町淡輪1478-1。古民家の自家焙煎珈琲専門店。
hiroshigecoffee.shop-pro.jp、カラーミーショップ、charset=EUC-JP)の商品情報を取得する。

【対象】商品検索一覧(?mode=srh&keyword=&sort=n、全35件・3ページ)から、焙煎豆(ブレンド・ストレート)のみ。
次は対象外: ドリップパック、ギフトセット、バラエティーセット、アイスリキッドコーヒー(期間限定)、
ペーパーフィルター。
【価格・重量】商品名の【100ｇ】/【500ｇ】が販売単位の重量で、表示価格はその重量の税込価格(内税)。
「スタンダードブレンド/エスプレッソ&アイスブレンド/クラシックブレンド」は500gのみの販売で、
他は100g(数量を増やして200g以上も可)。選択肢は挽き方のみ(豆のまま/細挽き/中挽き/粗挽き)で同額。
【産地】説明文冒頭の「原産国:」から取得。複数国・「その他」があるものはブレンド。
【焙煎度】商品ページの説明文に書かれた焙煎度のみ採用(「浅煎りのブレンド」「一番深煎り」「フルシティーロースト」等)。
無い商品は null。選択不可(店が決めた焙煎度)。酸味・苦み・ボディの5段階評価は flavor_notes に記載。
【在庫】カートボタンが無ければ品切れ。
robots.txt(2026-10-26確認): User-agent: * は /secure/ と /cart/ のみ禁止。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import detect_country_name, detect_stock_status, parse_product

SHOP_INFO = {
    "name": "ひろしげ珈琲倶楽部",
    "url": "https://hiroshigecoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "大阪府泉南郡岬町淡輪1478-1",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "https://hiroshigecoffee.shop-pro.jp/ の商品一覧・各商品ページ(ページ下部の店舗表記・定休日火曜・営業時間11-18時)を"
                   "2026-10-26に確認。公式 http://hiroshige-coffee.com/ トップ「大阪府岬町の自家焙煎珈琲専門店」。"
                   "お知らせは2026年10月の営業時間変更を掲載(更新は新しい)。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://hiroshigecoffee.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=srh&keyword=&sort=n"
CRAWL_DELAY_SECONDS = 2.0
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("ドリップ", "ギフト", "セット", "リキッド", "フィルター")
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*")
WEIGHT_RE = re.compile(r"【\s*(\d+)\s*g\s*】")
COUNTRY_ALIAS = {"パプアニューギニ": "パプアニューギニア"}
ROAST_RE = re.compile(r"(フルシティーロースト|中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
ROAST_NORMALIZE = {"フルシティーロースト": "フルシティロースト"}


def fetch(url: str) -> str:
    time.sleep(CRAWL_DELAY_SECONDS)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> dict[str, str]:
    items: dict[str, str] = {}
    for page in range(1, 10):
        soup = BeautifulSoup(fetch(LIST_URL + ("" if page == 1 else f"&page={page}")), "html.parser")
        new = 0
        for a in soup.find_all("a", href=re.compile(r"^\?pid=\d+")):
            pid = re.search(r"pid=(\d+)", a["href"]).group(1)
            name = re.sub(r"[\s　]+", " ", a.get_text(" ", strip=True))
            if pid not in items:
                items[pid] = name
                new += 1
            elif name and not items[pid]:
                items[pid] = name
        if new == 0:
            break
    return items


def to_country(token: str) -> str | None:
    token = token.strip()
    token = COUNTRY_ALIAS.get(token, token)
    return detect_country_name(token)


def build_record(pid: str, list_name: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    product = (json.JSONDecoder().raw_decode(html, m.end())[0]).get("product") or {}
    raw = (product.get("name") or list_name)
    raw = re.sub(r"<br\s*/?>", " ", raw)
    title = re.sub(r"[\s　]+", " ", unicodedata.normalize("NFKC", raw)).strip()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    soup = BeautifulSoup(html, "html.parser")
    has_cart = "カートに入れる" in html
    desc_el = soup.select_one("div.product_description")
    desc_lines = [unicodedata.normalize("NFKC", l.strip()) for l in
                  (desc_el.get_text("\n", strip=True).split("\n") if desc_el else []) if l.strip()]

    wm = WEIGHT_RE.search(title)
    weight = int(wm.group(1)) if wm else None
    # 表示名: 【100g】以降の酸味/苦み/ボディ評価は説明に回し、商品名は銘柄部分にする
    name_only = re.split(r"\s*酸味\s*:", title)[0].strip()
    rating = None
    rm = re.search(r"酸味\s*[:：]\s*(\d*)\s*苦み\s*[:：]\s*(\d*)\s*ボディ\s*[:：]\s*(\d*)", title)
    if rm:
        rating = "酸味{}・苦み{}・ボディ{}(5段階)".format(*[v or "不明" for v in rm.groups()])

    price = product.get("sales_price_including_tax") or None

    origin_line = next((l for l in desc_lines if l.startswith("原産国")), "")
    origin_text = re.split(r"\s+酸味", origin_line.split(":", 1)[1])[0].strip() if ":" in origin_line else ""
    tokens = [t for t in re.split(r"[、,]", origin_text) if t.strip()]
    has_other = any(t.strip() in ("その他", "他") for t in tokens)
    countries = []
    for t in tokens:
        c = to_country(t)
        if c and c not in countries:
            countries.append(c)

    is_blend = "ブレンド" in name_only or len(countries) >= 2 or has_other
    parsed = parse_product(name_only)
    if is_blend:
        category, origin = "ブレンド", None
        parsed["designated_brand"] = None
        origin_source = None
    else:
        category = "ストレート"
        origin = countries[0] if countries else None
        if not origin:
            c = detect_country_name(name_only)
            origin = c
        origin_source = "product_description" if origin else None

    comment = [l for l in desc_lines
               if not l.startswith(("原産国", "酸味", "*ご注意", "ご注意", "1.", "2.", "2．", "1．", "ツイート", "この商品"))]
    comment_text = " ".join(comment).strip()
    rm2 = ROAST_RE.search(comment_text)
    roast_level = None
    if rm2:
        roast_level = ROAST_NORMALIZE.get(rm2.group(1), rm2.group(1))
    flavor_parts = [p for p in (rating, comment_text) if p]
    flavor = "。".join(flavor_parts) or None

    stock_status = detect_stock_status(title, structural_out_of_stock=not has_cart)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name_only,
        "category": category,
        "origin_country": origin,
        "origin_source": origin_source,
        "designated_brand": parsed["designated_brand"] if not is_blend else None,
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_selectable": False,
        "roast_hint": roast_level,
        "flavor_notes": flavor,
        "farm_note": ("原産国: " + "、".join(tokens)) if (is_blend and tokens) else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [{"origin_country": c} for c in countries] if is_blend else [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, name in list_items().items():
        if not name or any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        rec = build_record(pid, name)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_hiroshigecoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hiroshigecoffee.json に出力しました")


if __name__ == "__main__":
    main()
