# -*- coding: utf-8 -*-
"""
scrape_coffeemeikan.py

珈琲鳴館(coffeemeikan.com、東京都八王子市椚田町572-1(本社・八王子店)、ほか府中宮町店・府中店・
千歳烏山店・長沼店・湘南辻堂焙煎所・湘南モールフィル店など7〜8拠点)の通信販売ページの
商品情報を取得する。「世界の厳選コーヒーを毎日、生から焙煎」する自家焙煎店で、通販は独自の
PHPカート(teiban.php→cart.php)。店舗数は11未満のため対象内。

【住所について】
特定商取引法に基づく表示の所在地(本社)「東京都八王子市椚田町572-1」を採用(2026-10確認)。
府中市宮町は府中宮町店(東京都府中市宮町1-25-5 杉村ビル1F)の所在地。

【対象商品について】
実データ確認済み(2026-10時点): 通販ページ「コーヒー豆リスト」(/teiban.php、焙煎の浅い順)の
32銘柄のうち、価格行(カゴ入れ)が有効な28銘柄を収録する(カフェインレスライト・モカマタリ
イエメニア・ブルーマウンテンNo.1・エチオピアゲイシャの4銘柄は価格行がHTMLコメントアウトされ
販売停止中のため除外)。各銘柄の見出し
「●銘柄名 / 産地 焙煎度」(div.slidebox)と、直下の「生産国」「ロースト」「特徴」表、
サイズ別の価格行(500g・250g複数・250g・200g・100g・50g)を解析する。
ギフト(gift.php)・生豆は対象外。PDF価格表(/pdf/price.pdf)も存在するが、通販ページの
価格行と同じ内容のためHTMLのみを使用する(PDFは解析しない)。

【重量・価格】
最小サイズは「50g(定価)」の行(例:セロ・カームク 50g=600円(税込))。50gが無い銘柄は
最小の行を採用する(価格は税込)。「250g複数/500g」は複数購入の30%引き特価のため最小サイズでは
ないので使わない。完売表示は2026-10時点で無し(在庫あり扱い)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import ROAST_KEYWORDS, parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲鳴館",
    "url": "https://coffeemeikan.com/",
    "platform": "独自カート(teiban.php)",
    "address": "東京都八王子市椚田町572-1",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://coffeemeikan.com"
LIST_URL = f"{BASE_URL}/teiban.php"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
SIZE_PATTERN = re.compile(r"(\d+)\s*g")
ORIGIN_OVERRIDES = {"グァテマラ": "グアテマラ", "ハワイ": "アメリカ(ハワイ)"}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_list(html_text: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    items = []
    for box in soup.select("div.slidebox"):
        a = box.select_one("a[name]")
        if not a:
            continue
        label = a["name"]
        font = a.select_one("font")
        roast_label = font.get_text(strip=True) if font else None
        heading = a.get_text(" ", strip=True)
        if roast_label:
            heading = heading.replace(roast_label, "")
        heading = re.sub(r"^●\s*", "", heading).strip()
        heading = re.sub(r"\s*/\s*$", "", heading).strip()
        row = box.find_next_sibling("div", class_="row")
        if row is None:
            continue
        desc_p = row.find("p")
        desc = desc_p.get_text(" ", strip=True) if desc_p else None
        fields: dict[str, str] = {}
        t1 = row.select_one("table.shop-table-type1")
        if t1:
            for tr in t1.select("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                for i in range(0, len(cells) - 1, 2):
                    if cells[i]:
                        fields[cells[i]] = cells[i + 1]
        sizes = []
        t2 = row.select_one("table.shop-table-type2")
        if t2:
            for tr in t2.select("tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                sm = SIZE_PATTERN.search(unicodedata.normalize("NFKC", tds[0].get_text(" ", strip=True)))
                pm = re.search(r"([\d,]+)\s*円", tds[1].get_text())
                if sm and pm:
                    sizes.append((int(sm.group(1)), int(pm.group(1).replace(",", "")), tds[0].get_text(" ", strip=True)))
        items.append({
            "label": label,
            "heading": heading,
            "roast_label": roast_label,
            "desc": desc,
            "fields": fields,
            "sizes": sizes,
            "sold_out": "完売" in row.get_text() or "売り切れ" in row.get_text() or "在庫切れ" in row.get_text(),
        })
    return items


def build_record(item: dict) -> dict | None:
    if not item["sizes"]:
        return None
    heading = unicodedata.normalize("NFKC", item["heading"])
    origin_field = unicodedata.normalize("NFKC", item["fields"].get("生産国", ""))
    # 小さいサイズの行。「複数」付き(まとめ買い特価)は除く
    cands = [s for s in item["sizes"] if "複数" not in s[2]]
    weight_g, price, _ = min(cands or item["sizes"], key=lambda s: s[0])
    parsed = parse_product(heading)
    is_blend = "ブレンド" in heading or "ブレンド" in origin_field or parsed["category"] == "ブレンド"
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, heading)
        if not parsed["origin_country"]:
            c = next((v for k, v in ORIGIN_OVERRIDES.items() if k in origin_field or k in heading), None)
            c = c or detect_country_name(origin_field) or detect_country_name(heading)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "origin_field"
    roast_hint = item["fields"].get("ロースト") or item["roast_label"]
    roast_level = None
    if roast_hint:
        for kw, roast in ROAST_KEYWORDS.items():
            if roast_hint.startswith(kw):
                roast_level = roast
                break
    out = item["sold_out"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": heading,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": (item["desc"] or "")[:300] or None,
        "farm_note": item["fields"].get("特徴") or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": f"{LIST_URL}#{item['label']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in parse_list(fetch(LIST_URL)):
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeemeikan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeemeikan.json に出力しました")


if __name__ == "__main__":
    main()
