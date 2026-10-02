# -*- coding: utf-8 -*-
"""
scrape_hiranocoffee.py

平野珈琲(千葉県市川市市川2-30-25、hirano-coffee.com。大門通りの自家焙煎珈琲豆店、地方発送あり、
店舗は1店のみ。「取り扱い店舗」は卸先)の商品情報を取得する。静的HTML1ページ構成。

【対象商品について】
実データ確認済み(2026-10時点、お知らせの最新は2026-09-19の9月新着豆): トップページの
「お品書き」(#menu)に、ブレンド珈琲3種(ミディアム・フレンチ・こく深)とストレート珈琲12銘柄が
100g・税込価格で並ぶ(PDF「詳しいお品書き」はフォント埋め込みの都合でテキスト抽出できないが、
HTML側に価格付きで同内容が掲載されているためHTMLを採用)。HTMLコメントアウトされている銘柄
(取り扱い終了)は除外し、「スリランカ有機ルフナ紅茶ティーバッグ」は紅茶のため除外。
焙煎度はブレンドのみ表記(ミディアム=中深煎り、フレンチ=深煎り、こく深=表記なし)で、ストレートは
「ミディアムタイプと深煎りの2タイプ」を選べる旨が新着豆のお知らせにあるだけで価格・銘柄は共通のため
roast_levelはNone。お知らせ(新着珈琲豆)に同名の銘柄があれば、その説明文を flavor_notes に付与する。
在庫表示は無いため全て販売中扱い。商品個別URLが無いためトップページURL+銘柄名のフラグメントで一意にする。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "平野珈琲",
    "url": "https://hirano-coffee.com/",
    "platform": "独自サイト(静的HTML)",
    "address": "千葉県市川市市川2-30-25",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "https://hirano-coffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("紅茶", "ティーバッグ", "ドリップ")
BLEND_ROAST = {
    "ミディアムタイプ": ("中深煎り", "中深煎り：酸味と苦みの調和"),
    "フレンチタイプ": ("深煎り", "深煎り：柔らかな苦み"),
}


def norm(s: str) -> str:
    return re.sub(r"[\s　・]+", "", unicodedata.normalize("NFKC", s))


def news_notes(soup: BeautifulSoup) -> dict[str, str]:
    news = soup.select_one("#news")
    text = news.get_text("\n", strip=True) if news else ""
    notes: dict[str, str] = {}
    for seg in text.split("【")[1:]:
        if "】" not in seg:
            continue
        name, body = seg.split("】", 1)
        body = body.split("※")[0]
        body = " ".join(ln.strip() for ln in body.split("\n") if ln.strip())
        notes[norm(name)] = body
    return notes


def scrape_all_products() -> list[dict]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    notes = news_notes(soup)

    records = []
    for li in soup.select("#menu li.menu_list__item"):
        h4 = li.select_one("h4.menu_list__ttl")
        section = h4.get_text(strip=True) if h4 else ""
        if section not in ("ブレンド珈琲", "ストレート珈琲"):
            continue
        for dt in li.select("dt.menu_data__ttl"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            span = dt.select_one("span.menu_data__type")
            sub = span.get_text(strip=True) if span else ""
            if span:
                span.extract()
            head = dt.get_text(strip=True)
            full = f"{head} {sub}".strip()
            if any(k in full for k in EXCLUDE_KEYWORDS):
                continue
            pm = re.search(r"(\d+)\s*g\s+([\d,]+)\s*円", dd.get_text(" ", strip=True))
            if not pm:
                continue

            is_blend = section == "ブレンド珈琲"
            roast_level = roast_hint = None
            if is_blend:
                name = f"ブレンド {head}"
                if head in BLEND_ROAST:
                    roast_level, roast_hint = BLEND_ROAST[head]
                parsed = parse_product(name)
                parsed["category"] = "ブレンド"
                parsed["origin_country"] = None
                parsed["origin_source"] = None
                parsed["designated_brand"] = None
                parsed["roast_level"] = None
                flavor = sub.strip("（）()") or None
                if head in BLEND_ROAST:
                    flavor = None
            else:
                name = full
                parsed = parse_product(name)
                parsed["category"] = "ストレート"
                if not parsed["origin_country"]:
                    c = detect_country_name(head)
                    if c:
                        parsed["origin_country"] = c
                        parsed["origin_source"] = "raw_name"
                parsed = apply_category_hint_fallback(parsed, name)
                flavor = None
                key = norm(full)
                for nk, nv in notes.items():
                    if nk and (nk in key or key in nk):
                        flavor = nv
                        break

            records.append({
                "shop_name": SHOP_INFO["name"],
                "raw_name": name,
                "category": parsed["category"],
                "origin_country": parsed["origin_country"],
                "origin_source": parsed["origin_source"],
                "designated_brand": parsed["designated_brand"],
                "processing_method": parsed["processing_method"],
                "grade": parsed["grade"],
                "roast_level": roast_level,
                "roast_hint": roast_hint,
                "flavor_notes": flavor,
                "farm_note": None,
                "post_processing_tags": parsed["post_processing_tags"],
                "blend_components": [],
                "price": int(pm.group(2).replace(",", "")),
                "weight_g": int(pm.group(1)),
                "stock_status": "販売中",
                "out_of_stock": False,
                "product_url": f"{PAGE_URL}#{quote(name)}",  # 商品個別URLが無いため、商品IDを一意にするフラグメントを付ける
            })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hiranocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hiranocoffee.json に出力しました")


if __name__ == "__main__":
    main()
