# -*- coding: utf-8 -*-
"""
scrape_iwatacoffeeyamaguchi.py

岩田珈琲店(iwata coffee、https://iwatacoffee.shop-pro.jp/、山口県熊毛郡上関町祝島3675)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。文字コードはEUC-JP。
(山梨県の「岩田屋珈琲」・岩手県の「岩田珈琲」とは別の店。山口県祝島の実在店。)

【店舗発見の経緯】
全国再調査(山口県)の新規発掘で発見。

【住所について(要確認)】
サイト内で2通りの記載がある。
- 店舗紹介(?mode=f1)とアクセスマップ(?mode=f4): 「〒742-1401 山口県熊毛郡上関町祝島3675 岩田珈琲店」
  (電話 0820-66-2550、営業 10:00〜18:00、定休火曜日。2014年に港近くの古民家を改装した店舗)
- 特定商取引法表示(?mode=sk): 「山口県熊毛郡上関町祝島644-2」(郵便番号は「742-140」と桁欠け。電話は同じ 0820-66-2550)
実店舗(喫茶営業・来店向けのアクセス案内)の所在地として店舗紹介・アクセスマップの「祝島3675」を採用した。
644-2 は特商法上の届出住所(運営統括責任者 堀田 圭介)で、店舗所在地と異なる可能性がある。

【robots.txt】
確認済み(2026-10-15時点): User-agent: * は /secure/ と /cart/ のみ制限。

【対象商品について】
実データ確認済み(2026-10-15時点): 商品検索一覧(?mode=srh、2ページ)の全16件は「豆のまま」「粉に挽いて」の
2形態が別商品として並ぶ8銘柄。豆のまま・粉は同一銘柄として統合し、豆のまま商品ページを代表とする(全て100g)。
8銘柄: 祝島ぶれんど / 桜ブレンド / フレンチキリマンジャロ / オープンセサミぶれんど / ブラジル ピーベリー /
マンデリン / グァテマラ・カフェインレス(デカフェ) / 本日のおすすめ珈琲豆(その時々の店主チョイス。銘柄・産地・焙煎度は不定)。
在庫表示(stock_num)は全て無し=販売中扱い。価格は商品ページの税込価格。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "岩田珈琲店",
    "url": "https://iwatacoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "山口県熊毛郡上関町祝島3675",
    "prefecture": "山口県",
    "robots_txt_status": "許可(2026-10-15確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://iwatacoffee.shop-pro.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1.5

# (豆のまま商品のpid, 商品名(形態表記除去後), 重量(g), ブレンドか, 焙煎度, 産地(ストレートのみ))
ITEMS = [
    ("116462242", "祝島ぶれんど", 100, True, "中煎り", None),
    ("116462841", "桜ブレンド", 100, True, "深煎り", None),
    ("116462992", "フレンチキリマンジャロ", 100, False, "深煎り", "タンザニア"),
    ("126010270", "オープンセサミぶれんど", 100, True, "極深煎り", None),
    ("126010387", "ブラジル ピーベリー", 100, False, None, "ブラジル"),
    ("145970402", "マンデリン", 100, False, None, "インドネシア"),
    ("164629641", "グァテマラ・カフェインレス", 100, False, None, "グアテマラ"),
    ("167014293", "本日のおすすめ珈琲豆", 100, False, None, None),
]


def fetch_page(url: str) -> tuple[BeautifulSoup, str]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def extract_colorme(raw_html: str) -> dict:
    m = re.search(r"var\s+Colorme\s*=\s*", raw_html)
    if not m:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(raw_html[m.end():])
    except json.JSONDecodeError:
        return {}
    return data.get("product") or {}


def extract_description(soup: BeautifulSoup) -> str | None:
    for x in soup(["script", "style"]):
        x.decompose()
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))
    m = re.search(r"\d+円\(税込\)\s*(.*?)\n型番|\d+円\(税込\)\s*(.*?)購入数", text, re.S)
    desc = (m.group(1) or m.group(2)) if m else ""
    desc = re.sub(r"\s+", " ", desc or "").strip()
    return desc[:400] or None


def detect_sold_out(product: dict, soup_text: str) -> bool:
    stock = product.get("stock_num")
    if stock is not None and stock <= 0:
        return True
    return "購入数" not in soup_text


def scrape_all_products() -> list[dict]:
    records = []
    for pid, name, weight, is_blend, roast, origin in ITEMS:
        time.sleep(CRAWL_DELAY_SECONDS)
        url = f"{BASE_URL}/?pid={pid}"
        try:
            soup, raw = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        product = extract_colorme(raw)
        price = product.get("sales_price_including_tax")
        if not price:
            print(f"[warn] 価格が取得できません: pid={pid}")
            continue
        sold_out = detect_sold_out(product, soup.get_text("\n"))
        desc = extract_description(soup)

        parsed = parse_product(name)
        if parsed["is_flavored"]:
            continue
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["processing_method"] = None
            parsed["grade"] = None
        elif origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "description"

        is_decaf = "カフェインレス" in name or "デカフェ" in name
        tags = list(parsed["post_processing_tags"])
        if is_decaf and "デカフェ" not in tags:
            tags.append("デカフェ")

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "デカフェ" if is_decaf else parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": tags,
            "blend_components": [],
            "price": int(price),
            "weight_g": weight,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_iwatacoffeeyamaguchi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_iwatacoffeeyamaguchi.json に出力しました")


if __name__ == "__main__":
    main()
