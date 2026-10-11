# -*- coding: utf-8 -*-
"""
scrape_ibeanscoffee.py

アイ・ビーンズ・コーヒー(www.i-beans.jp、滋賀県犬上郡多賀町多賀1409-3〈本店。
3店舗展開〉、自家焙煎豆のオンライン販売)の商品情報を取得する。EC-CUBE 4系。
scrape_malkicoffee.py と同じ構造。

robots.txt確認済み(2026-10-11): User-agent: *に対し*.csv$のみDisallow。

【対象商品】カテゴリ「期間限定コーヒー」(10)・「ブレンドコーヒー」(11)・
「シングルオリジン(産地別)」(12、カフェインレス(29)は12に含まれる)の
商品を巡回(重複はIDで排除)。水出しコーヒーパック・カップオン(ドリップバッグ)・
ギフト・セット・器具・紅茶・予約販売/モニター/プレゼントは巡回しない。
全商品が200g表記(最小重量が200g)で、バリエーションは「豆のまま」「粉に挽く」
のみ(価格差なし)。重量は商品ページの「重さ：200.00 g」、焙煎度は
ec-productRole__tagのタグ(シティーロースト等)から取得する。
"""
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "アイ・ビーンズ・コーヒー",
    "url": "https://www.i-beans.jp/",
    "platform": "EC-CUBE",
    "address": "滋賀県犬上郡多賀町多賀1409-3",
    "prefecture": "滋賀県",
    "robots_txt_status": "実質許可(2026-10確認。User-agent: *に対し*.csv$のみDisallow)",
}
BASE_URL = "https://www.i-beans.jp"
CATEGORY_IDS = [10, 11, 12, 29]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ["水出し", "カップオン", "ドリップバッグ", "ドリップパック", "セット", "ギフト", "Pack"]
ROAST_TAGS = ["フレンチロースト", "イタリアンロースト", "フルシティーロースト", "シティーロースト", "ハイロースト", "ミディアムロースト", "ライトロースト", "シナモンロースト"]
WEIGHT_RE = re.compile(r"重さ[：:]\s*([\d.]+)\s*g")
TITLE_WEIGHT_RE = re.compile(r"【\s*(\d+)\s*[gｇ]\s*】")


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def fetch_product_ids():
    ids = []
    for cid in CATEGORY_IDS:
        s = BeautifulSoup(get(f"{BASE_URL}/products/list?category_id={cid}&disp_number=100"), "html.parser")
        for a in s.select('a[href*="/products/detail/"]'):
            m = re.search(r"/products/detail/(\d+)", a.get("href", ""))
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
    return sorted(ids, key=int)


def extract_class_categories(html_text):
    marker = "eccube.classCategories = "
    idx = html_text.find(marker)
    if idx == -1:
        return {}
    i = html_text.find("{", idx)
    depth = 0
    for j in range(i, len(html_text)):
        if html_text[j] == "{":
            depth += 1
        elif html_text[j] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html_text[i:j + 1])
                except json.JSONDecodeError:
                    return {}
    return {}


def extract_flavor(soup):
    els = soup.select("div.ec-productRole__description")
    if not els:
        return None
    lines = []
    for ln in els[-1].get_text("\n", strip=True).split("\n"):
        if ln.startswith("【"):
            break
        lines.append(ln)
    t = "".join(lines).strip()
    return t[:200] or None


def build_record(html_text, url):
    soup = BeautifulSoup(html_text, "html.parser")
    og = soup.select_one('meta[property="og:title"]')
    title = og["content"].strip() if og and og.get("content") else ""
    if not title or any(k in title for k in NON_BEAN_KEYWORDS):
        return None
    tags = [t.get_text(strip=True) for t in soup.select(".ec-productRole__tag")]
    roast = next((t for t in tags if t in ROAST_TAGS), None)
    page_text = soup.get_text("\n", strip=True)
    m = WEIGHT_RE.search(page_text)
    weight = int(float(m.group(1))) if m else None
    if weight is None:
        m = TITLE_WEIGHT_RE.search(title)
        weight = int(m.group(1)) if m else None
    cc = extract_class_categories(html_text)
    combos = [d for k1, v in cc.items() if k1 != "__unselected" for k2, d in v.items() if d.get("product_class_id")]
    in_stock = [d for d in combos if d.get("stock_find")]
    pool = in_stock or combos
    price = None
    if pool:
        p = (pool[0].get("price02_inc_tax") or "").replace(",", "")
        price = int(p) if p.isdigit() else None
    raw_name = title if (roast is None or roast.replace("ロースト", "") in title) else f"{title} {roast}"
    parsed = parse_product(raw_name)
    stock = detect_stock_status(raw_name, not in_stock)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"] or roast,
        "flavor_notes": extract_flavor(soup),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock,
        "out_of_stock": stock != "販売中",
        "product_url": url,
    }


if __name__ == "__main__":
    records, flavored = [], []
    for pid in fetch_product_ids():
        url = f"{BASE_URL}/products/detail/{pid}"
        try:
            rec = build_record(get(url), url)
        except requests.RequestException as e:
            print("[warn]", url, e)
            continue
        if rec:
            records.append(rec)
    with open("data_ibeanscoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ibeanscoffee.json に出力しました")
    for r in records:
        print(r["raw_name"][:60], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])
