# -*- coding: utf-8 -*-
"""
scrape_mamedio.py

豆dio(マメディオ、東京都大田区中央3-20-16、無農薬・直火焙煎の自家焙煎コーヒー豆店)の
ショップ(mamedio.shop、旧 mamedio.shop-pro.jp からリダイレクト、カラーミーショップ・EUC-JP)から
商品情報を取得する。

【対象商品について】
ショップのカテゴリ「コーヒー豆」(2ページ・14件)に加え、どのカテゴリにも属さない豆商品
(オリジナルブレンド・ローマ、カフェインレスブレンド・カノン、ハロウイーンブレンド2026、
夏季限定ヨーロピアンブレンドNapoli 2026)がサイト内検索(キーワード「g」)でのみ見つかるため、
カテゴリ一覧とキーワード検索「g」の結果(1〜2ページ)の和集合から取得する。
除外: ドリップバッグ(コーヒーバッグ・水出しバッグ・中国雲南ダブルファーメンテーションのバッグ)、
チョコ菓子、器具(ドリッパー・スケール・ストッカー)。
商品は1銘柄1ページで、ほとんどが200g(商品名に表記)。焙煎度(ハイ/シティ/フレンチ)と挽き方は購入時に選択式で、価格は全選択肢で同額。
商品名に焙煎度が明記されているもの(例: 「(フレンチロースト)」)のみ roast_level を設定し、選択式のものは null。
「エチオピア無農薬 ジマ・ゲラ農園」は商品名・ページに重量表記が無いため weight_g は null。
価格は税込(一覧の「1,850円(税137円)」は税込価格)。在庫は一覧のSOLD OUT表示で判定する(SOLD OUT商品は一覧に価格が出ないため詳細ページの販売価格を使う)。

robots.txt(https://mamedio.shop/robots.txt): User-agent:* で /secure/ と /cart/ のみ Disallow(2026-10-25確認)。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "豆dio",
    "url": "https://mamedio.shop/",
    "platform": "カラーミーショップ",
    "address": "東京都大田区中央3-20-16",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-25確認。/secure/ と /cart/ のみ禁止)",
    "source_note": "ショップのカテゴリ「コーヒー豆」とサイト内検索の結果を2026-10-25に確認。住所は公式 http://mamedio.shop/ ・特定商取引法の記載(大田区中央3-20-16)。自家焙煎の根拠は公式の『直火焙煎コーヒー豆店 豆dio…自家焙煎,直火焙煎』。ハロウイーンブレンド2026・Napoli 2026・価格改定告知など2026年の商品あり",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://mamedio.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
CATEGORY_ID = "2401876"
SEARCH_KEYWORD = "g"

EXCLUDE_KEYWORDS = ["ドリップ", "バッグ", "チョコ", "ドリッパー", "スケール", "ストッカー", "ギフト", "セット"]
UNIT_SPLIT = re.compile(r'<li class="product-list__unit product-list__unit-lg[^"]*">')
ROAST_PATTERN = re.compile(r"(ハイ|シティ|フレンチ)ロースト")
ROAST_MAP = {"ハイ": "浅煎り", "シティ": "中煎り", "フレンチ": "深煎り"}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    time.sleep(REQUEST_INTERVAL)
    return resp.text


def parse_units(html: str) -> list[dict]:
    out = []
    for b in UNIT_SPLIT.split(html)[1:]:
        b = b.split("</li>")[0]
        n = re.search(r'class="product-list__name[^"]*">(.*?)</a>', b, flags=re.S)
        pid = re.search(r"pid=(\d+)", b)
        if not n or not pid:
            continue
        pm = re.search(r"([\d,]+)円", re.sub(r"<[^>]+>", " ", b.split("product-list__prices")[-1]))
        out.append({
            "pid": pid.group(1),
            "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", n.group(1))).strip(),
            "price": int(pm.group(1).replace(",", "")) if pm else None,
            "sold_out": bool(re.search(r"SOLD ?OUT", b)),
        })
    return out


def fetch_candidates() -> list[dict]:
    items: dict[str, dict] = {}
    urls = [f"{BASE_URL}/?mode=cate&cbid={CATEGORY_ID}&csid=0",
            f"{BASE_URL}/?mode=cate&cbid={CATEGORY_ID}&csid=0&page=2",
            f"{BASE_URL}/?mode=srh&cid=&keyword={SEARCH_KEYWORD}",
            f"{BASE_URL}/?mode=srh&cid=&keyword={SEARCH_KEYWORD}&page=2"]
    for url in urls:
        for u in parse_units(fetch(url)):
            items.setdefault(u["pid"], u)
    return list(items.values())


def fetch_detail_price(pid: str):
    html = fetch(f"{BASE_URL}/?pid={pid}")
    i = html.find("モバイルショップ")
    m = re.search(r"([\d,]+)円\(税", re.sub(r"<[^>]+>", " ", html[i:] if i >= 0 else html))
    return int(m.group(1).replace(",", "")) if m else None


def build_record(it: dict) -> dict:
    title = it["title"]
    wm = re.search(r"(\d+)\s*[gｇ]", title)
    weight = int(wm.group(1)) if wm else None
    name = re.sub(r"\s*\d+\s*[gｇ]\s*", " ", title)
    name = re.sub(r"\s*[（(]?\s*(?:ハイ|シティ|フレンチ)ロースト\s*[）)]?", "", name)
    name = re.sub(r"[　\s]+", " ", name).strip()
    name = re.sub(r"\s*[（(]\s*$", "", name)
    rm = ROAST_PATTERN.search(title)
    roast = ROAST_MAP[rm.group(1)] if rm else None
    parsed = parse_product(name)
    is_blend = "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
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
        "roast_level": roast,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": f"{BASE_URL}/?pid={it['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in fetch_candidates():
        if any(kw in it["title"] for kw in EXCLUDE_KEYWORDS):
            continue
        if it["price"] is None:
            # SOLD OUT の商品は一覧に価格が出ないので、詳細ページの販売価格を使う
            it["price"] = fetch_detail_price(it["pid"])
        records.append(build_record(it))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamedio.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamedio.json に出力しました")


if __name__ == "__main__":
    main()
