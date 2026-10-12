# -*- coding: utf-8 -*-
"""
scrape_genzya.py

玄豆屋(genzya.shop-pro.jp、公式 www.genzya.com、福島県白河市道場町29、店主 金澤裕史)の
商品情報を取得する。カラーミーショップ(shop-pro.jp)。

【店舗発見の経緯】
全国再調査(福島県)の新規発掘で発見。

【文字コード】EUC-JP(実データ確認済み)。

【対象商品について】
実データ確認済み(2026-10-12、sitemap.xml上の商品ID46件、うち6件は「現在、この商品は扱って
おりません」の404): カテゴリ「コーヒー豆(1)」8件・「コーヒー豆(2)」5件・「コーヒー豆(ブレンド)」
4件の計17件が対象のコーヒー豆。非対象は紅茶・中国茶・アルガンオイル・書籍・ミル・炭サシェ。
商品ページ内の「買い物を続ける」リンクのカテゴリID(cbid)で豆カテゴリを判定する。
全商品とも重量は200g(説明末尾の「(ミディアム・ロースト:200g)」「(200g)」等)。説明に重量表記が
無い「RAコロンビアNR」は、他の全豆商品が200gのためDEFAULT_WEIGHT_Gを適用している。
焙煎度は説明末尾の括弧書き(ハイ・ロースト/シティ・ロースト/フレンチ・ロースト等)から取る。
価格は税込(「1,404円(税104円)」の前者)。在庫表示が無く、タイトルに「復活をお待ちください…」が
付く商品のみ品切れ扱い(ワイルドモカ・自生アビシニアン・9th)。商品IDは?pid=…で一意。

【robots.txtについて】
確認済み(2026-10-12): User-agent: * は/secure/と/cart/のみ制限。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    detect_processing_method,
)

SHOP_INFO = {
    "name": "玄豆屋",
    "url": "http://genzya.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福島県白河市道場町29",
    "prefecture": "福島県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "http://genzya.shop-pro.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

BEAN_CATEGORY_IDS = {"872109", "872110", "872111"}  # コーヒー豆(1)/(2)/(ブレンド)
BLEND_CATEGORY_ID = "872111"
DEFAULT_WEIGHT_G = 200
SOLD_OUT_MARK = "復活をお待ちください"

# 国名が名前・説明に出ない銘柄の産地
ORIGIN_KEYWORDS = {
    "キリマンジャロ": "タンザニア",
    "マンデリン": "インドネシア",
    "トラジャ": "インドネシア",
    "モカ": "エチオピア",
}

TITLE_PATTERN = re.compile(r'<table class="main_title".*?<td>(.*?)</td>', re.S)
PRICE_PATTERN = re.compile(r'class="price_detail">\s*([\d,]+)円')
CATEGORY_PATTERN = re.compile(r'class="link-nextShopping"><a href="[^"]*cbid=(\d+)')
EXPL_PATTERN = re.compile(r'<div class="expl">(.*?)</div>', re.S)
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)・?ロースト")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "EUC-JP"
    return resp.text


def fetch_pids() -> list[str]:
    text = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30).text
    return list(dict.fromkeys(re.findall(r"\?pid=(\d+)", text)))


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}/?pid={pid}"
    page = fetch(url)
    title_m = TITLE_PATTERN.search(page)
    cat_m = CATEGORY_PATTERN.search(page)
    if not title_m or not cat_m or cat_m.group(1) not in BEAN_CATEGORY_IDS:
        return None  # 取扱終了(404)ページ・紅茶・中国茶・オイル・書籍・器具

    title = unicodedata.normalize("NFKC", strip_tags(title_m.group(1)))
    sold_out = SOLD_OUT_MARK in title
    name = re.sub(rf"^{SOLD_OUT_MARK}[…\.]*", "", title).strip()
    expl_m = EXPL_PATTERN.search(page)
    desc = unicodedata.normalize("NFKC", strip_tags(expl_m.group(1))) if expl_m else ""
    price_m = PRICE_PATTERN.search(page)

    # 名前末尾/説明末尾の焙煎度・重量表記(NFKCで半角カナ「ﾊｲ･ﾛｰｽﾄ」を全角に正規化済み)
    roast_m = ROAST_PATTERN.search(name) or ROAST_PATTERN.search(desc)
    roast = (roast_m.group(1) + "ロースト") if roast_m else None
    name = re.sub(r"[（(][^()（）]*ロースト[^()（）]*[）)]\s*$", "", name).strip()
    weight_m = WEIGHT_PATTERN.search(desc)
    weight_g = int(weight_m.group(1)) if weight_m else DEFAULT_WEIGHT_G

    parsed = parse_product(name)
    is_blend = cat_m.group(1) == BLEND_CATEGORY_ID or parsed["category"] == "ブレンド"
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        origin = detect_country_name(name)
        source = "raw_name"
        if not origin:
            origin = next((c for k, c in ORIGIN_KEYWORDS.items() if k in name), None)
        if not origin:
            origin = detect_country_name(desc)
            source = "description"
        if origin and not parsed["origin_country"]:
            parsed["origin_country"] = origin
            parsed["origin_source"] = source
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or detect_processing_method(desc),
        "grade": parsed["grade"],
        # ブレンド名「ミディアム・ブレンド」の「ミディアム」を焙煎度と誤認しないよう、ブレンドは括弧書きのみ採用
        "roast_level": roast if is_blend else (roast or parsed["roast_level"]),
        "roast_hint": None,
        "flavor_notes": desc or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in fetch_pids():
        try:
            record = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_genzya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_genzya.json に出力しました")


if __name__ == "__main__":
    main()
