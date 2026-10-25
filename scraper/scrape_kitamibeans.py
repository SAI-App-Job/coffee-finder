# -*- coding: utf-8 -*-
"""
scrape_kitamibeans.py

ビーンズ喜多見(自家焙煎珈琲豆屋ビーンズ、kitami-beanscoffee.com、東京都世田谷区喜多見8-15-32)の
商品情報を取得する。WordPress + Welcart(テーマ ego_welcart_tcd079)。
「ご注文ごとに生豆から焙煎」。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧 /category/item/category-all-item/ (30件、カルーセル重複あり)
の商品ページを読み、180gのコーヒー豆(ストレート・ブレンド・デカフェ)を対象とする。
除外: 水出しコーヒーパック、アイスコーヒー紙パック、お試し2種セット、ドリップバッグ、
550g大容量セール(同じ「ビーンズブレンド」の180gが別にあるため最小重量の180gを代表)。
【価格】サイト表記は税別(食品8%)。他店との整合のため税込(切り上げ)に換算する
(商品ページの「まとめ買い割引」欄の税込表記と一致することを実データで確認済み)。
【焙煎度】注文時に焙煎度合(ミディアム〜イタリアン、生豆のまま)を選ぶ方式のため roast_level=None、
roast_selectable=True。商品ページに「おすすめはミディアムロースト」等があれば roast_hint に保持する。
【robots.txt】User-agent: * で /store/wp-admin/ のみDisallow(admin-ajax.phpはAllow)。
"""

import json
import math
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
)

SHOP_INFO = {
    "name": "ビーンズ喜多見",
    "url": "https://kitami-beanscoffee.com/",
    "platform": "WordPress + Welcart",
    "address": "東京都世田谷区喜多見8-15-32",
    "prefecture": "東京都",
    "robots_txt_status": "許可(User-agent: * は /store/wp-admin/ のみDisallow)",
    "source_note": "公式 https://kitami-beanscoffee.com/ (2026-10-20確認)の店舗情報に所在地・焙煎L.O.16:00、"
                   "サイトタイトルに「ご注文ごとに生豆から焙煎」。商品一覧(category-all-item)の180g豆を収録し、"
                   "価格は税別表記を税込(8%・切り上げ)に換算。「38周年ブレンド」等2026年の新商品が掲載され更新は現役。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://kitami-beanscoffee.com"
LIST_URL = f"{BASE_URL}/category/item/category-all-item/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
SLEEP = 2.0
EXCLUDE = ["水出し", "アイスコーヒー", "セット", "ドリップバッグ", "550g", "まんじゅう", "ギフト"]
TAG_PATTERN = re.compile(r"【[^】]*】")


def get(url):
    time.sleep(SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def list_items():
    soup = BeautifulSoup(get(LIST_URL), "html.parser")
    items = {}
    for a in soup.select("article.p-archive03__item"):
        href = a.select_one("a")["href"]
        title = a.select_one("h3").get_text(strip=True)
        cat = a.select_one(".p-archive03__item-category")
        items.setdefault(href, {"url": href, "title": title, "genre": cat.get_text(strip=True) if cat else ""})
    return list(items.values())


def countries_of(text):
    """「ブラジル・コロンビア」「コロンビア/ロス・パティオス」等の文字列から国名を出現順に抽出する"""
    out = []
    for tok in re.split(r"[・/／、,\s　（）()【】]+", text):
        c = detect_country_name(tok.replace("マラウィ", "マラウイ")) if tok else None
        if c and c not in out:
            out.append(c)
    return out


def section(lines, start, stops):
    """lines中のstart行の次から、stops行の手前までを返す"""
    if start not in lines:
        return []
    i = lines.index(start) + 1
    out = []
    while i < len(lines) and lines[i] not in stops:
        out.append(lines[i])
        i += 1
    return out


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        title = it["title"]
        if any(k in title for k in EXCLUDE):
            continue
        wm = re.search(r"(\d+)\s*g", title)
        if not wm:
            continue
        weight = int(wm.group(1))
        html_text = get(it["url"])
        soup = BeautifulSoup(html_text, "html.parser")
        for t in soup(["script", "style", "header", "footer", "nav"]):
            t.decompose()
        main = soup.find("main") or soup.body
        lines = [l.strip() for l in main.get_text("\n", strip=True).split("\n") if l.strip()]

        # 価格(販売価格の次の行)
        if "販売価格" not in lines:
            continue
        pm = re.search(r"([\d,]+)", lines[lines.index("販売価格") + 1])
        if not pm:
            continue
        price_ex = int(pm.group(1).replace(",", ""))
        price = math.ceil(price_ex * 1.08)

        stock_lines = section(lines, "在庫", {"カテゴリー：", "産地情報"})
        in_stock = any("在庫あり" in l for l in stock_lines) and not any("SOLD" in l.upper() or "切れ" in l for l in stock_lines)

        # 説明(h1の次から「販売価格」の前まで)
        h1 = main.find("h1")
        h1_text = h1.get_text(strip=True) if h1 else title
        desc_lines = []
        if h1_text in lines:
            desc_lines = lines[lines.index(h1_text) + 1: lines.index("販売価格")]
        desc = re.sub(r"\s+", " ", " ".join(desc_lines)).strip()[:400] or None
        roast_hint = None
        hint_line = None
        for l in desc_lines:
            if re.match(r"^(おすすめ|オススメ)", l) or "ロースト" in l and len(l) < 40:
                roast_hint = l
                hint_line = l
                break
        desc_lines = [l for l in desc_lines if l != hint_line and l.upper() != "SOLD OUT"]
        desc = re.sub(r"\s+", " ", " ".join(desc_lines)).strip()
        desc = re.sub(r"^焙煎(度合)?は\s*", "", desc)[:400] or None
        roast_level, roast_selectable = None, True
        fixed = re.match(r"^(?:焙煎は?\s*)?(ミディアム|シティ|イタリアン|ライト)ロースト(?:のみ)?$", (roast_hint or "").replace("焙煎度合は ", ""))
        if roast_hint and "のみ" in roast_hint and "＋" not in roast_hint and fixed:
            roast_level = {"ライト": "浅煎り", "ミディアム": "中煎り", "シティ": "中深煎り", "イタリアン": "深煎り"}[fixed.group(1)]
            roast_selectable = False

        countries = section(lines, "生産国", {"生産地域", "標高", "品種", "精製方法"})
        processing_lines = section(lines, "精製方法", {"産地特長", "挽き方", "焙煎度合"} )
        is_blend = it["genre"] == "ブレンド" or "ブレンド" in title or "べっぴん" in title
        decaf = "カフェインレス" in title or "デカフェ" in title

        clean = TAG_PATTERN.sub("", title)
        clean = re.sub(r"\s*\d+\s*g.*$", "", clean).strip()
        clean = re.sub(r"\s+", " ", clean)
        if decaf and "デカフェ" not in clean:
            clean += "(デカフェ)"

        parsed = parse_product(clean)
        components = []
        processing = parsed["processing_method"]
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
            components = [{"origin_country": c} for c in dict.fromkeys(countries_of(" ".join(countries)))]
            processing = None
        else:
            parsed["category"] = "ストレート"
            cs = countries_of(countries[0]) if countries else []
            if countries and not cs and countries[0].startswith("マラウ"):
                cs = ["マラウィ"]  # coffee_parserが未対応の国名(サイト表記のまま)
            if cs:
                parsed["origin_country"] = cs[0]
                parsed["origin_source"] = "description"
            elif not parsed["origin_country"]:
                c = detect_country_name(clean)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, clean)
            if not processing and processing_lines:
                processing = normalize_processing_method(processing_lines[0])

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": clean,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_selectable": roast_selectable,
            "roast_hint": roast_hint,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": components,
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": it["url"],
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kitamibeans.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kitamibeans.json に出力しました")


if __name__ == "__main__":
    main()
