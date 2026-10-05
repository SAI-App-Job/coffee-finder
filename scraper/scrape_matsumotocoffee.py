# -*- coding: utf-8 -*-
"""
scrape_matsumotocoffee.py

松本珈琲工房(matsumoto-coffee.com、愛知県長久手市西浦901番地の長久手本店と、豊田市若宮町
1-57-1 T-FACE A館1階の豊田店の2店舗、自家焙煎のスペシャルティコーヒー専門店)の
商品情報を取得する。WordPress(カート機能なし、注文フォームのみ)。

【店舗情報の確認結果】
公式トップページの店舗情報(2026-10確認): 「松本珈琲工房|長久手本店 〒480-1171
愛知県長久手市西浦901番地(TEL 0561-56-2260)」と「松本珈琲工房|T-FACE 豊田店 〒471-0026
愛知県豊田市若宮町1-57-1 T-FACE A館1階(TEL 080-4303-1492)」の2店舗構成。
豆の注文フォーム(/purchase/)・電話注文窓口(0561-56-2260)は長久手本店のものであり、
本店が主たる拠点と判断してSHOP_INFOのaddressは長久手本店とした(豊田店は同一店の2店舗目)。

【対象商品について】
実データ確認済み(2026-10時点): トップページの「松本珈琲工房のスペシャルティコーヒー豆」
セクションに10銘柄の価格表(`article.beans-card`)が並ぶ(ストレート4・ブレンド6、
うちブレンド枠にカフェインレス〈メキシコ〉1)。全て200g/税込2,100〜2,300円の1サイズ。
商品個別ページ・在庫表示はないため、product_urlは「トップページURL#」+商品名の
パーセントエンコードとし、在庫は「販売中」(注文フォームで常時受付)とする。
焙煎度はカード上のラベル(Medium/Hi/City/French)を、ミディアム/ハイ/シティ/フレンチ
ローストに対応づけて採用する。
"""

import json
import re
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "松本珈琲工房",
    "url": "https://matsumoto-coffee.com/",
    "platform": "WordPress(注文フォームのみ・カートなし)",
    "address": "愛知県長久手市西浦901番地",
    "prefecture": "愛知県",
    "robots_txt_status": "確認済み(Disallow: /wp-admin/ のみ。商品ページは対象外)",
}

PAGE_URL = "https://matsumoto-coffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_MAP = {"Medium": "ミディアムロースト", "Hi": "ハイロースト", "High": "ハイロースト",
             "City": "シティロースト", "French": "フレンチロースト"}
PRICE_PATTERN = re.compile(r"(\d+)\s*g\s*[／/]\s*([\d,]+)円")


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("　", " ")).strip()


def scrape_all_products() -> list[dict]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    records = []
    for card in soup.select("article.beans-card"):
        price_p = next((p for p in card.select("p.beans-card__price") if PRICE_PATTERN.search(unicodedata.normalize("NFKC", p.get_text()))), None)
        if not price_p:
            continue
        pm = PRICE_PATTERN.search(unicodedata.normalize("NFKC", price_p.get_text(" ", strip=True)))
        weight, price = int(pm.group(1)), int(pm.group(2).replace(",", ""))

        title_el = card.select_one(".beans-card__title")
        name_el = card.select_one(".beans-card__name")
        if name_el:
            name = squash((title_el.get_text(" ", strip=True) + " " if title_el else "") + name_el.get_text(" ", strip=True))
            is_blend = "ブレンド" in name
        else:
            # ブレンド枠のカフェインレスは、商品名が価格と同じクラスの<p>に入っている
            name_p = next((p for p in card.select("p.beans-card__price") if p is not price_p), None)
            name = squash(name_p.get_text(" ", strip=True)) if name_p else ""
            is_blend = "ブレンド" in name
        if not name:
            continue
        name = unicodedata.normalize("NFKC", name) if re.search(r"[Ａ-Ｚａ-ｚ０-９]", name) else name
        # 「ＬＣＦ」等の全角英数のみ半角化(カナは変えない)
        name = re.sub(r"[Ａ-Ｚａ-ｚ０-９]+", lambda m: unicodedata.normalize("NFKC", m.group(0)), name)

        label_el = card.select_one(".roast-label")
        roast_key = label_el.get_text(strip=True) if label_el else None
        roast = ROAST_MAP.get(roast_key)
        desc_el = card.select_one(".beans-card__description")
        desc = squash(desc_el.get_text(" ", strip=True)) if desc_el else None

        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["processing_method"] = None
        else:
            parsed["category"] = "ストレート"
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        processing = parsed["processing_method"]
        if not processing and not is_blend and desc and re.search(r"ウォッシュ[ドト]|ナチュラル|ハニー|アナエロ|パルプド", desc):
            processing = detect_processing_method(desc)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": PAGE_URL + "#" + urllib.parse.quote(name),
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_matsumotocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_matsumotocoffee.json に出力しました")


if __name__ == "__main__":
    main()
