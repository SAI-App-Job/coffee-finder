# -*- coding: utf-8 -*-
"""
scrape_cafeanis.py

カフェアニス(自家焙煎珈琲工房カフェアニス、https://cafeanis.shop-pro.jp/、山梨県南アルプス市荊沢1309、
カラーミーショップ/shop-pro.jp。公式サイトはグーペ https://r.goope.jp/sr-19-192081s0262 、
公式の表記は「自家焙煎珈琲工房 カフェアニス Cafe Anis」)の商品情報を取得する。

【店舗発見の経緯】
全国再調査(山梨県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-12時点): 全15商品(カテゴリ「深煎りコーヒー」「浅煎りコーヒー」
「コールドブリュー」。トップ・検索・カテゴリページの和集合)。
同一銘柄が「豆」と「粉」の別商品で並ぶため、豆の商品のみを代表として採用する。
除外: 「粉」商品(同一銘柄のバリエーション単独)、「セット」(深煎り/浅煎り各400gの2銘柄セット)、
コールドブリュー用コーヒー粉(50gパック8個。粉・パック商品)。
採用は豆5銘柄(ブラジル400g、コロンビア/トラジャ/タンザニア/エチオピア・モカ各200g)。
ブラジルは400gのみの設定(200g商品なし)。価格は税込・送料込。
焙煎度: 店の説明どおり深煎り=フルシティロースト、浅煎り=ハイロースト。
在庫: カラーミーの在庫管理は未使用(stock_num=null)で品切れ表示もないため販売中として扱う。

【robots.txtについて】
User-agent: * は /secure/ と /cart/ のみ制限(2026-10-12確認)。識別可能なUser-Agentを使用する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "カフェアニス(自家焙煎珈琲工房)",
    "url": "https://cafeanis.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "山梨県南アルプス市荊沢1309",
    "prefecture": "山梨県",
    "robots_txt_status": "許可(2026-10-12確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://cafeanis.shop-pro.jp/"
LIST_URLS = [
    BASE_URL,
    BASE_URL + "?mode=srh&cid=&keyword=",
    BASE_URL + "?mode=srh&cid=&keyword=&page=2",
    BASE_URL + "?mode=cate&cbid=2597040&csid=0",
    BASE_URL + "?mode=cate&cbid=2695084&csid=0",
    BASE_URL + "?mode=cate&cbid=2695086&csid=0",
]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_BY_TITLE = {"深煎り": "深煎り(フルシティロースト)", "浅煎り": "浅煎り(ハイロースト)"}
# 商品名の産地表記のうち、coffee_parserの国名辞書で拾えないもの
ORIGIN_BY_KEYWORD = {"トラジャ": "インドネシア", "エチオピア": "エチオピア"}


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def collect_pids() -> list[str]:
    pids: list[str] = []
    for url in LIST_URLS:
        try:
            html_text = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 一覧取得失敗: {url} ({e})")
            continue
        for pid in re.findall(r"pid=(\d+)", html_text):
            if pid not in pids:
                pids.append(pid)
        time.sleep(CRAWL_DELAY_SECONDS)
    return pids


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html_text = fetch_page(url)
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = re.sub(r"\s+", " ", (product.get("name") or "").replace("　", " ")).strip()

    # 豆の単品のみ(粉・セット・コールドブリュー用粉は除外)
    if not re.search(r"(深煎り|浅煎り)コーヒー 豆 ", title) or "セット" in title:
        return None

    roast_key = "深煎り" if title.startswith("深煎り") else "浅煎り"
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    # 「深煎りコーヒー 豆 ブラジル 400g」→「ブラジル 深煎り」
    origin_label = re.sub(r"^(深煎り|浅煎り)コーヒー 豆 ", "", title)
    origin_label = re.sub(r"\s*\d+\s*[gｇ]\s*$", "", origin_label).strip()
    name = f"{origin_label} {roast_key}"

    soup = BeautifulSoup(html_text, "html.parser")
    exp = soup.select_one("div.product_exp")
    flavor_notes = re.sub(r"\s+", " ", exp.get_text(" ", strip=True)).strip() if exp else None

    parsed = parse_product(origin_label)
    for kw, country in ORIGIN_BY_KEYWORD.items():
        if kw in origin_label:
            parsed["origin_country"] = country
            parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, origin_label)
    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": ROAST_BY_TITLE[roast_key],
        "roast_hint": None,
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": product.get("sales_price_including_tax"),
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in collect_pids():
        try:
            record = build_record(pid)
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafeanis.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafeanis.json に出力しました")


if __name__ == "__main__":
    main()
