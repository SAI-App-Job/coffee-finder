# -*- coding: utf-8 -*-
"""
scrape_decocoffee.py

DECO Specialty Coffee Roaster(自家焙煎珈琲 DECO、千葉県東金市東金588、decocoffee.com)の商品情報を取得する。
浅煎り〜中煎り用の熱風焙煎機と深煎り用の半熱風焙煎機を使い分ける自家焙煎店。店舗は1店のみ。
グーペ(Goope)製サイトで、オンラインカートは無く、「メニュー」ページに豆の銘柄・価格を掲載する
(店頭でのスペシャルティコーヒー豆挽き売り。電話・店頭で購入)。

【対象商品について】
実データ確認済み(2026-10時点、シーズナルブレンド「秋風2026」掲載): 季節のおすすめ豆1・
ブレンド3・シングルオリジン4・デカフェ1の計9銘柄を対象とする。「水出し珈琲パック」2種は
パック製品のため除外。

【価格・重量について】
商品名に「200g」「150g」等の内容量が入っており、価格は税込のその重量の価格。シーズナルブレンドのみ
「100g〜 1,450円〜」(100g価格が最小サイズ)の表記で、100gの1,450円を採用する。
焙煎度は商品名に「ミディアム」「ミディアムダーク」「ダーク」と記載される。ミディアム→ミディアム
ロースト、ミディアムダーク→中深煎り、ダーク→深煎りとし、原文表記はroast_hintに保持する。
在庫表示は無いため全て販売中扱い(掲載中=販売中)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "DECO Specialty Coffee Roaster",
    "url": "https://decocoffee.com/",
    "platform": "Goope(店頭販売・メニュー掲載のみ)",
    "address": "千葉県東金市東金588",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

MENU_URL = "https://decocoffee.com/menu"
BASE_URL = "https://decocoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("水出し", "パック")

ROAST_WORDS = (
    ("ミディアムダーク", "中深煎り"),
    ("ミディアム～ミディアムダーク", "中煎り〜中深煎り"),
    ("ダーク", "深煎り"),
    ("ミディアム", "ミディアムロースト"),
)


def scrape_all_products() -> list[dict]:
    resp = requests.get(MENU_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    records = []
    for lst in soup.select("div.list"):
        cat_el = lst.select_one(".category_title")
        category_title = cat_el.get_text(strip=True) if cat_el else ""
        for art in lst.select("div.article"):
            a = art.select_one("h3.article_title a")
            if not a:
                continue
            name = re.sub(r"\s+", " ", a.get_text(strip=True)).strip()
            if any(k in name for k in EXCLUDE_KEYWORDS):
                continue
            price_el = art.select_one("div.price")
            pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
            wm = re.search(r"(\d+)\s*[gｇ]", name)
            if not pm:
                continue
            text_el = art.select_one("div.text")
            lines = [p.get_text(" ", strip=True) for p in text_el.find_all("p")] if text_el else []
            notes = None
            origin_line = None
            for ln in lines:
                if ln.startswith("生産国名"):
                    origin_line = ln.replace("生産国名", "").strip()
                elif ln.startswith("カップコメント"):
                    notes = ln.replace("カップコメント", "").strip()
            extra = [ln for ln in lines if not ln.startswith(("生産国名", "カップコメント"))]
            if extra:
                notes = (notes + " / " if notes else "") + " ".join(extra)

            parsed = parse_product(name)
            is_blend = "ブレンド" in name or category_title.startswith("ブレンド") or "ブレンド" in category_title
            if is_blend:
                parsed["category"] = "ブレンド"
                parsed["origin_country"] = None
                parsed["origin_source"] = None
            else:
                parsed["category"] = "ストレート"
                if not parsed["origin_country"]:
                    c = detect_country_name(name)
                    if c:
                        parsed["origin_country"] = c
                        parsed["origin_source"] = "raw_name"
                parsed = apply_category_hint_fallback(parsed, name)

            roast_level = None
            roast_hint = None
            for word, level in ROAST_WORDS:
                if word in name:
                    roast_level, roast_hint = level, word
                    break
            if "ミディアム～ミディアムダーク" in name:
                roast_level, roast_hint = "中煎り〜中深煎り", "ミディアム～ミディアムダーク"

            href = a.get("href", "")
            url = href if href.startswith("http") else BASE_URL + href
            weight = int(wm.group(1)) if wm else None
            clean_name = re.sub(r"[\s　]*\d+\s*[gｇ]\s*〜?\s*$", "", name).strip()

            records.append({
                "shop_name": SHOP_INFO["name"],
                "raw_name": clean_name,
                "category": parsed["category"],
                "origin_country": parsed["origin_country"],
                "origin_source": parsed["origin_source"],
                "designated_brand": parsed["designated_brand"],
                "processing_method": parsed["processing_method"],
                "grade": parsed["grade"],
                "roast_level": roast_level,
                "roast_hint": roast_hint,
                "flavor_notes": notes,
                "farm_note": f"生産国: {origin_line}" if origin_line else None,
                "post_processing_tags": parsed["post_processing_tags"],
                "blend_components": [],
                "price": int(pm.group(1).replace(",", "")),
                "weight_g": weight,
                "stock_status": "販売中",
                "out_of_stock": False,
                "product_url": url,
            })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_decocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_decocoffee.json に出力しました")


if __name__ == "__main__":
    main()
