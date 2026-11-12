# -*- coding: utf-8 -*-
"""
scrape_19hitoyasumi.py

19HITOYASUMI(いっきゅうひとやすみ、富山県砺波市幸町3-5、公式 https://19hitoyasumi.com/、
カラーミーショップ https://19hitoyasumi.shop-pro.jp/)の自家焙煎スペシャルティコーヒー豆の
商品情報を取得する。カラーミーショップ(shop-pro.jp)。

【店舗発見の経緯】
全国再調査(北陸3県)の新規発掘で発見(2026-11)。

【実店舗・自家焙煎の根拠(2026-11-03確認)】
特商法 https://19hitoyasumi.shop-pro.jp/?mode=sk に「販売業者 19HITOYASUMI 渡邉功一」
「住所 富山県砺波市幸町3-5」。公式サイトに砺波店・高岡戸出店・南砺アミュー福野店・
富山総曲輪店の4店舗(11店舗未満)。商品ページに「コーヒー豆の焙煎は国際資格SCAA/CQI認定
QグレーダーとSCAJ認定コーヒーマイスターを取得した、当店の焙煎師(渡邉功一)が責任を持って
最高の状態でご用意致します」、ショップのカテゴリ名「自家焙煎」。

robots.txt確認済み(2026-11-03): User-agent: * は /cart/ のみ Disallow。

【文字コード】EUC-JP。

【商品の取得】
カテゴリ「スペシャルティ珈琲豆」(?mode=cate&cbid=1453852&csid=0、2ページ)から取得する。
水出しコーヒードリップパック・ドリップパックのアソート・ドリップバッグ・ギフトは除外。

【価格・重量】
詳細ページの var Colorme の variants は「重量(100g/200g)×挽き方」の組み合わせで、
商品ページ冒頭の表示価格は100g・豆のままの価格(200gは別価格)。最小重量(100g)・
豆のままの価格(税込)を代表に採用する。
"""

import html as html_lib
import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "19HITOYASUMI",
    "url": "https://19hitoyasumi.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "富山県砺波市幸町3-5",
    "prefecture": "富山県",
    "robots_txt_status": "許可(2026-11-03確認。/cart/以外は制限なし)",
    "source_note": "https://19hitoyasumi.shop-pro.jp/ のカテゴリ「スペシャルティ珈琲豆」(2026-11-03確認)。住所は特商法ページ。2026年冬のクリスマスケーキ特集あり、更新は新しい",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://19hitoyasumi.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=cate&cbid=1453852&csid=0"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
NON_BEAN_KEYWORDS = ["ドリッ", "パック", "アソート", "ギフト", "セット", "マグネット"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"^(\d+)\s*g$", re.IGNORECASE)
SUFFIX_PATTERN = re.compile(r"\s*\[スペシャルティーコーヒー豆ブレンド\]\s*")

# 商品名から検出できない産地の補完
ORIGIN_OVERRIDES = {
    "61416836": "インドネシア",  # インドネシア・スマトラ・マンデリン
    "166384217": "ブラジル",     # ブラジル ゴールデンマウンテン
}
# 焙煎度は商品説明に「深煎り」とある銘柄のみ明示する
ROAST_OVERRIDES = {"184505333": "深煎り"}


def fetch_page(url: str):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(text, "html.parser"), text


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()


def scrape_list() -> list[str]:
    pids: list[str] = []
    for page in range(1, 6):
        url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        soup, _ = fetch_page(url)
        found = 0
        for a in soup.select('a[href*="pid="]'):
            m = re.search(r"pid=(\d+)", a["href"])
            name = clean(a.get_text())
            if not m or not name or m.group(1) in pids:
                continue
            if any(k in name for k in NON_BEAN_KEYWORDS):
                continue
            pids.append(m.group(1))
            found += 1
        time.sleep(CRAWL_DELAY_SECONDS)
        if found == 0:
            break
    return pids


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    soup, text = fetch_page(url)
    m = COLORME_JSON_PATTERN.search(text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product")
    if not product:
        return None
    name = SUFFIX_PATTERN.sub("", clean(product.get("name")))

    # 豆のまま×最小重量のバリエーションを代表にする
    best = None
    for v in product.get("variants") or []:
        opts = [clean(v.get("option1_value")), clean(v.get("option2_value"))]
        if "豆のまま" not in opts:
            continue
        w = next((int(WEIGHT_PATTERN.match(o).group(1)) for o in opts if WEIGHT_PATTERN.match(o)), None)
        price = v.get("option_price_including_tax")
        if w is None or price is None:
            continue
        if best is None or w < best[0]:
            best = (w, price, v.get("stock_num"))
    if best is None:
        return None
    weight, price, stock_num = best
    out = isinstance(stock_num, int) and stock_num <= 0

    exp = soup.select_one("div.product_exp")
    desc = None
    if exp:
        for br in exp.find_all("br"):
            br.replace_with("\n")
        body = clean(exp.get_text(" "))
        desc = html_lib.unescape(body)[:400] or None

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if "デカフェ" in name:
        parsed["category"] = "デカフェ"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    elif "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if pid in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
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
        "roast_level": ROAST_OVERRIDES.get(pid) or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price),
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in scrape_list():
        try:
            rec = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if rec is not None:
            records.append(rec)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_19hitoyasumi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_19hitoyasumi.json に出力しました")


if __name__ == "__main__":
    main()
