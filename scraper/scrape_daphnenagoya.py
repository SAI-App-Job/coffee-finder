# -*- coding: utf-8 -*-
"""
scrape_daphnenagoya.py

ダフネコーヒー(daphne.shop-pro.jp、愛知県名古屋市中村区烏森7丁目260-1、名古屋の老舗・
株式会社ダフネコーヒー)の商品情報を取得する。カラーミーショップ(文字コードEUC-JP)。
※既存のscrape_daphne.py(東京都港区のDaphne、EC-CUBE)とは別の店舗のため、slugをdaphnenagoyaとした。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「こだわりのコーヒー豆」(cbid=2316654)の商品のうち、
商品名が「〇〇ブレンド  100g」の自家焙煎ブレンド5件(フレンチ・アメリカン・イタリアン・炭焼き・
ストロング)を対象とする。ドリップコーヒー3入・ドリップバッグ・コーヒーピーパック・お試しセット
(100g×5種類)・ギフトカテゴリは除外。100g単位の販売で、選択肢は「豆/粉」(同額)。
価格は税込(「780円(税58円)」表記の780円)。

【サイトの鮮度について(2026-10時点)】
トップページのお知らせが2026-09-23付(価格改定は直営店の2026/10/1改定の告知)で更新されており、
サイトは現行運営。ただしオンライン価格が直営店の価格改定に連動して変わる可能性は不明。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "ダフネコーヒー",
    "url": "https://daphne.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "愛知県名古屋市中村区烏森7丁目260-1",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(カラーミー標準構成)",
}

BASE_URL = "https://daphne.shop-pro.jp"
CATEGORY_ID = "2316654"  # こだわりのコーヒー豆
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 10

NAME_PATTERN = re.compile(r"^(.+?)\s*(\d+)\s*[gｇ]\s*$")
COLORME_PATTERN = re.compile(r"var Colorme = (\{.*?\});\s*\n")
ROAST_PATTERN = re.compile(r"(やや浅煎り|やや深煎り|中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
DESC_STOP_PATTERN = re.compile(r"こちらの(?:コーヒー|ブレンド)|<ご購入に際して")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_pids() -> list[str]:
    pids: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        t = fetch_html(f"{BASE_URL}/?mode=cate&cbid={CATEGORY_ID}&csid=0&page={page}")
        new = [p for p in dict.fromkeys(re.findall(r"[?&]pid=(\d+)", t)) if p not in pids]
        if not new:
            break
        pids += new
    return pids


def build_record(pid: str) -> dict | None:
    html_text = fetch_html(f"{BASE_URL}/?pid={pid}")
    m = COLORME_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1))["product"]
    raw = re.sub(r"\s+", " ", product["name"].replace("　", " ")).strip()
    nm = NAME_PATTERN.match(raw)
    if not nm or "ブレンド" not in nm.group(1):
        return None  # ドリップコーヒー・ピーパック・お試しセット等
    title = nm.group(1).strip()
    weight_g = int(nm.group(2))

    soup = BeautifulSoup(html_text, "html.parser")
    el = soup.select_one("div.product__explain")
    text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""
    text = re.sub(r"^(?:・\s*)+", "", text)
    cut = DESC_STOP_PATTERN.search(text)
    desc = (text[:cut.start()] if cut else text).strip()[:400] or None
    rm = ROAST_PATTERN.search(desc or "")

    parsed = parse_product(title)
    sold_out = product.get("stock_num") == 0

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": "ブレンド",
        "origin_country": None,
        "origin_source": None,
        "designated_brand": None,
        "processing_method": None,
        "grade": parsed["grade"],
        "roast_level": rm.group(1) if rm else None,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": product.get("sales_price_including_tax"),
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in list_pids():
        try:
            rec = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_daphnenagoya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_daphnenagoya.json に出力しました")


if __name__ == "__main__":
    main()
