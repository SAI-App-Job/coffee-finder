# -*- coding: utf-8 -*-
"""
scrape_coffeaexlibris.py

COFFEA EXLIBRIS(コフィア エクスリブリス、東京都府中市八幡町3-19-3 東府中 kettle、
公式 https://coffeaexlibris.com/、通販 https://coffeaexlibris.shop-pro.jp/)の
スペシャルティコーヒー豆の商品情報を取得する。カラーミーショップ(shop-pro.jp)、EUC-JP。

【実店舗・自家焙煎の根拠】(2026-10-25確認)
特商法表記(?mode=sk)の販売業者「株式会社 COFFEA EXLIBRIS」所在地は東京都府中市八幡町3-19-3。
?mode=f5「東府中 COFFEA EXLIBRIS kettle」に「2015年にスペシャルティコーヒーロースターとしてオープン。
ドイツ・プロバット社の焙煎機で焙煎しています。コーヒー豆の販売、テイクアウト」「〒183-0016 東京都府中市八幡町3-19-3」。
?mode=f2に下北沢店(東京都世田谷区代沢5-8-16、豆販売・テイクアウト)。店舗は2店のみ(11店未満)。
登録住所は焙煎拠点の府中店とする。

【robots.txt】/secure/ と /cart/ のみ Disallow(2026-10-25確認)。

【対象商品】
カテゴリ COFFEES(cbid=764612、全ページ)の豆。各銘柄は100g/250g/500gが別商品として並ぶため、
最小重量の100g商品を代表とする(商品名が100gで終わるもの)。価格は「豆のまま」の税込価格。
COFFEE BAG(ドリップバッグ)・GIFT SET・器具は対象外。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "COFFEA EXLIBRIS",
    "url": "https://coffeaexlibris.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都府中市八幡町3-19-3",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-25確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ(https://coffeaexlibris.shop-pro.jp/)のCOFFEESカテゴリ(cbid=764612)と各商品ページを2026-10-25に確認。特商法表記(?mode=sk)・東府中kettle店案内(?mode=f5)で所在地・プロバット焙煎機・実店舗を確認。2店舗(府中、下北沢)のため焙煎拠点の府中を登録住所とした。秋のブレンド・新入荷(2026-10-03)を掲載",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://coffeaexlibris.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=cate&cbid=764612&csid=0"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
CRAWL_DELAY_SECONDS = 2
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
W100 = re.compile(r"[\s　]*100\s*[gｇ]\s*$")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|深煎り|中煎り|浅煎り)")


def fetch(url: str) -> tuple[BeautifulSoup, str]:
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(text, "html.parser"), text


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def scrape_list() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 8):
        url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        soup, _ = fetch(url)
        lis = soup.select("li.productlist_list")
        for li in lis:
            a = li.select_one("a[href^='?pid=']")
            nm = li.select_one("span.item_name")
            if not a or not nm:
                continue
            name = clean(nm.get_text())
            if a["href"] in seen:
                continue
            seen.add(a["href"])
            if not W100.search(name):
                continue
            items.append({
                "url": BASE_URL + a["href"],
                "list_name": name,
                "sold_out": bool(re.search(r"売り切れ|SOLD ?OUT|在庫なし", li.get_text(" "))),
            })
        time.sleep(CRAWL_DELAY_SECONDS)
        if not lis:
            break
    return items


def build_record(item: dict) -> dict | None:
    soup, text = fetch(item["url"])
    m = COLORME_JSON_PATTERN.search(text)
    if not m:
        print(f"[warn] Colorme JSON なし: {item['url']}")
        return None
    product = json.loads(m.group(1)).get("product") or {}
    price = None
    for v in product.get("variants") or []:
        if v.get("option1_value") == "豆のまま":
            price = v.get("option_price_including_tax")
            break
    if price is None:
        price = product.get("sales_price_including_tax")
    name = clean(W100.sub("", clean(product.get("name") or item["list_name"])))
    stock = product.get("stock_num")
    sold_out = item["sold_out"] or (isinstance(stock, int) and stock <= 0)

    for e in soup.select("script,style"):
        e.decompose()
    lines = [clean(l) for l in soup.get_text("\n", strip=True).split("\n") if clean(l)]
    desc_lines = []
    if "商品説明" in lines:
        k = lines.index("商品説明")
        for l in lines[k + 1:k + 40]:
            if l in ("イメージ", "この商品を購入する", "イメージはありません。") or l.startswith("一緒に購入"):
                if l == "イメージ":
                    continue
                break
            desc_lines.append(l)
    desc = " ".join(desc_lines)
    fields = {}
    for l in desc_lines:
        mm = re.match(r"^(国名|地区|標高|生産処理場|農園|品種|生産処理方法|生産者|オーナー)[：:](.+)$", l)
        if mm:
            fields[mm.group(1)] = mm.group(2).strip()

    is_blend = "ブレンド" in name
    is_decaf = "ディカフェ" in name or "デカフェ" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        raw_country = fields.get("国名") or ""
        raw_country = {"ブルンディ": "ブルンジ"}.get(raw_country, raw_country)  # 表記ゆれ(ブルンディ→ブルンジ)
        c = detect_country_name(raw_country) or detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "product_page"
        parsed = apply_category_hint_fallback(parsed, name)
    process = parsed["processing_method"]
    if fields.get("生産処理方法") and not process:
        process = normalize_processing_method(fields["生産処理方法"])
    roast = None
    rm = ROAST_PATTERN.search(name) or ROAST_PATTERN.search(desc)
    if rm:
        roast = rm.group(1)
    farm_parts = []
    for key in ("地区", "標高", "生産処理場", "農園", "品種"):
        if fields.get(key):
            farm_parts.append(f"{key}: {fields[key]}")
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": process,
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc[:400] or None,
        "farm_note": " / ".join(farm_parts) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "decaf_process": ("マウンテンウォータープロセス" if "マウンテンウ" in desc else "デカフェ(除去方法の詳細記載なし)") if is_decaf else None,
        "price": price,
        "weight_g": 100,
        "stock_status": "一時的に品切れ" if sold_out else "販売中",
        "out_of_stock": bool(sold_out),
        "product_url": item["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in scrape_list():
        try:
            rec = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['url']} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeaexlibris.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeaexlibris.json に出力しました")


if __name__ == "__main__":
    main()
