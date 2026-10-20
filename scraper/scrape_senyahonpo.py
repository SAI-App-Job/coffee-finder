# -*- coding: utf-8 -*-
"""
scrape_senyahonpo.py

煎谷本舗(アロマスコーヒーマーケット / AROMAS COFFEE MARKET、福岡県久留米市国分町1600-2、
店頭販売 11-18時・水木定休、焙煎作業店舗は大刀洗町)の通販サイト(www.aromascoffeemarket.com、
ショップサーブ)の商品情報を取得する。

【対象商品について】
ストレート(/SHOP/1032198)・ブレンド(/SHOP/1032457)・メール便コーナー(/SHOP/1034574)の商品一覧
(1ページ10件、2ページ目は /SHOP/<cat>/t02/list2.html)から全商品(2026-10-20時点23件)を集め、
業務用の1kg・3kg・5kg、飲み比べセット、水出しアイスコーヒー(バッグ)を除く。
各銘柄は1kg未満の最小重量(いずれも400g・メール便)の単品を代表とする。400gが無く1kg以上のみの銘柄
(マンデリン リントン3kg、ACMエスプレッソブレンド、ACMダーク 等)は除外。価格は「価格」(税込販売価格)を採用。
店頭の価格表示は2018年頃の更新のままのページが多く(サイトフッターは2015年)、更新の古さに注意。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "煎谷本舗",
    "url": "http://www.aromascoffeemarket.com/",
    "platform": "ショップサーブ",
    "address": "福岡県久留米市国分町1600-2",
    "prefecture": "福岡県",
    "robots_txt_status": "robots.txt なし(2026-10-20確認、/robots.txt は通常のHTMLページを返す。禁止指定なし)",
    "source_note": "aromascoffeemarket.com の商品一覧と各商品ページを2026-10-20に確認。特商法(/hpgen/HPB/shop/business.html)と店舗情報(/hpgen/HPB/categories/102667.html)で所在地・店頭販売・焙煎作業店舗(大刀洗町)を確認。サイトの作成・更新は2015〜2018年頃が中心で更新が古い",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "http://www.aromascoffeemarket.com"
LIST_CATEGORIES = ["1032198", "1032457", "1034574"]  # ストレート、ブレンド、メール便送料無料コーナー
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2

EXCLUDE_TITLE_KEYWORDS = ("飲み比べ", "セット", "水出し", "ドリップ")
ROAST_WORDS = ["極深煎り", "中深煎り", "深煎り", "浅～中煎り", "浅煎り", "中煎り"]
# ブレンド商品のタイトルに焙煎度が無い場合の補足(トップページ「中煎りブレンド!ミディアムロースト」)
ROAST_OVERRIDES = {"acmb1": "中煎り"}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    time.sleep(REQUEST_INTERVAL)
    return resp.text


def list_items() -> dict:
    items: dict[str, str] = {}
    for cat in LIST_CATEGORIES:
        page = 1
        while True:
            url = f"{BASE_URL}/SHOP/{cat}/list.html" if page == 1 else f"{BASE_URL}/SHOP/{cat}/t02/list{page}.html"
            html_text = fetch(url)
            soup = BeautifulSoup(html_text, "html.parser")
            for sec in soup.select("section.column4"):
                a = sec.select_one("h2 a")
                if a and a.get("href", "").startswith("/SHOP/"):
                    items.setdefault(a["href"], a.get_text(strip=True))
            m = re.search(r"(\d+)件中(\d+)件～(\d+)件", html_text)
            if not m or int(m.group(3)) >= int(m.group(1)):
                break
            page += 1
    return items


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def weight_g(title: str) -> int | None:
    t = norm(title)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", t, re.IGNORECASE)
    if not m:
        return None
    v = float(m.group(1))
    return int(v * 1000) if m.group(2).lower() == "kg" else int(v)


def base_name(title: str) -> str:
    t = norm(title)
    t = re.sub(r"\d+(?:\.\d+)?\s*(?:kg|g)\b", "", t, flags=re.IGNORECASE)
    for w in ROAST_WORDS + ["メール便"]:
        t = t.replace(w, "")
    return re.sub(r"\s+", "", t)


def select_representatives(items: dict) -> list[tuple[str, str]]:
    groups: dict[str, list[tuple[int, str, str]]] = {}
    for href, title in items.items():
        if any(k in title for k in EXCLUDE_TITLE_KEYWORDS):
            continue
        w = weight_g(title)
        if w is None:
            continue
        groups.setdefault(base_name(title), []).append((w, href, title))
    reps = []
    for g in groups.values():
        w, href, title = min(g)
        if w < 1000:  # 1kg以上のみの銘柄(業務用)は除外
            reps.append((href, title))
    return reps


def build_record(href: str, title: str) -> dict | None:
    soup = BeautifulSoup(fetch(BASE_URL + href), "html.parser")
    text = soup.get_text("\n")
    pm = re.search(r"(?<!小売)価格:\s*¥([\d,]+)", text)  # 「希望小売価格:」ではなく販売「価格:」
    price = int(pm.group(1).replace(",", "")) if pm else None
    if price is None:
        print(f"[warn] 価格取得失敗: {title}")
        return None
    stock_lines = re.findall(r"在庫あり|在庫なし|売り切れ|入荷待ち|SOLD\s*OUT|品切れ", text)
    out_of_stock = bool(stock_lines) and "在庫あり" not in stock_lines
    name = norm(title)
    slug = href.rsplit("/", 1)[-1].replace(".html", "")
    roast = ROAST_OVERRIDES.get(slug) or next((r for r in ROAST_WORDS if r in name), None)
    # 説明文: 「返品についての詳細はこちら」〜「返品交換について」の間
    m = re.search(r"返品についての詳細はこちら(.*?)返品交換について", text, re.S)
    desc = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    desc = re.sub(r"https?://\S+", "", desc).strip()
    is_ice_or_blend = "ブレンド" in name
    parsed = parse_product(name)
    if is_ice_or_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        country = detect_country_name(name)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g(title),
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": BASE_URL + href,
    }


def scrape_all_products() -> list[dict]:
    items = list_items()
    print(f"[info] 一覧から {len(items)} 商品を検出")
    records = []
    for href, title in select_representatives(items):
        rec = build_record(href, title)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_senyahonpo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_senyahonpo.json に出力しました")


if __name__ == "__main__":
    main()
