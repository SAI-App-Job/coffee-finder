# -*- coding: utf-8 -*-
"""
scrape_coffeelabo.py

珈琲実験室(株式会社珈琲実験室、東京都八王子市大和田町2-19-11、直営店 COFFEA 国立2店、
公式 https://www.coffee-labo-co.com/、通販「珈琲実験室 通信販売」https://coffee-labo.raku-uru.jp/)の
自社焙煎コーヒー豆の商品情報を取得する。楽売(Raku-Uru)。scrape_maroncoffee.py と同一プラットフォーム。

【実店舗・自家焙煎の根拠】(2026-10-25確認)
公式 https://www.coffee-labo-co.com/company.html で本社・自社焙煎工場の所在地(八王子市大和田町2-19-11)と
沿革「自社焙煎工場新設」「焙煎釜30K・15K・10K・5Kの4基設置」、直営店 COFFEA 大学通り店(国立市中1-16-33 1F)・
COFFEA さくら通り店(国立市富士見台3-5-1 1F)を確認。登録住所は本社・焙煎工場。店舗数は3拠点以内。

【robots.txt】/robots.txt はトップページのHTMLが返り制限記述なし(2026-10-25確認)。カテゴリ一覧・詳細のみ取得する。

【対象商品】
カテゴリ: 有機ストレート(34755)・有機ブレンド(34756)・有機ブレンド焙煎度別(34757)・
スペシャルティ ストレート(34760)・ブラジルスペシャルティ(34762)・お徳用400g工場ブレンド(34754)の豆。
1商品1規格(150〜200g、お徳用は400g)のため、その重量・価格(「豆・粉」選択時も同額)を採用する。
除外: ドリップバッグ・リキッド・紅茶・ココア・ゼリー・菓子・フィルター・紙袋(いずれもカテゴリ外)。
お徳用の工場ブレンド(400g)は1kg未満のため含める。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_stock_status

SHOP_INFO = {
    "name": "珈琲実験室",
    "url": "https://coffee-labo.raku-uru.jp/",
    "platform": "楽売(Raku-Uru)",
    "address": "東京都八王子市大和田町2-19-11",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-10-25確認。robots.txtに制限記述なし)",
    "source_note": "通販サイト(https://coffee-labo.raku-uru.jp/)のレギュラーコーヒー各カテゴリと各商品ページを2026-10-25に確認。公式 https://www.coffee-labo-co.com/company.html で本社・自社焙煎工場(八王子市大和田町2-19-11)と直営店(国立2店)を確認。お知らせ「商品ラインナップ変更のお知らせ(2026.09.18)」",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://coffee-labo.raku-uru.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 2

# (カテゴリID, 店側の分類。実際の分類は原材料の生産国数で判定する)
CATEGORIES = [
    (34755, "ストレート"),
    (34756, "ブレンド"),
    (34757, "ブレンド"),
    (34760, "ストレート"),
    (34762, "ブレンド"),   # ブラジルスペシャルティ: 商品名がブレンド名(アフタヌーンブレイク等)だが原料は単一国の可能性があるため詳細で判定
    (34754, "ブレンド"),
]
NON_BEAN_KEYWORDS = ["ドリップ", "リキッド", "セット", "ギフト", "DB"]
WEIGHT_IN_NAME = re.compile(r"[（(]\s*([\d０-９]+)\s*[gｇ](?:\s*/\s*([^）)]+))?[）)]")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り?|中浅煎り?|深煎り|中煎り|浅煎り)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[tuple[str, str, str]]:
    items, seen = [], set()
    for cid, cat in CATEGORIES:
        soup = fetch_page(f"{BASE_URL}/item-list?categoryId={cid}")
        for a in soup.select('p.item-name a[href^="/item-detail/"]'):
            item_id = a["href"].rsplit("/", 1)[-1]
            name = a.get_text(strip=True)
            if item_id in seen or any(k in name for k in NON_BEAN_KEYWORDS):
                continue
            seen.add(item_id)
            items.append((item_id, name, cat))
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def zen2han(s: str) -> str:
    return s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def build_record(item_id: str, list_name: str, cat: str) -> dict | None:
    url = f"{BASE_URL}/item-detail/{item_id}"
    soup = fetch_page(url)
    price_el = soup.select_one("b.raku-item-vari-price-num")
    price = None
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))
    sold_out = soup.select_one("div.item-dtail-orderinvalid") is not None and soup.select_one("a.raku-add-cart") is None
    txt = soup.select_one("div.item-detail-txt1")
    lines = [l.strip() for l in (txt.get_text("\n", strip=True).split("\n") if txt else []) if l.strip()]

    wm = WEIGHT_IN_NAME.search(list_name)
    weight = int(zen2han(wm.group(1))) if wm else None
    name = re.sub(r"\s+", " ", WEIGHT_IN_NAME.sub("", list_name)).strip()

    # 原材料「生豆生産国名○○」(複数国はブレンド)
    material = next((lines[i + 1] for i, l in enumerate(lines) if l == "原材料" and i + 1 < len(lines)), "")
    origins = []
    cm = re.search(r"生産国名\s*([^）)]+)", material)
    if cm:
        origins = [o.strip() for o in re.split(r"[、,，・/／]", cm.group(1)) if o.strip()]
    # 説明文: ラベル行(商品詳細/原材料/内容量)とその値、焙煎度のみの行、評価スコア行を除く
    desc_lines, skip_next = [], False
    for l in lines:
        if skip_next:
            skip_next = False
            continue
        if l in ("原材料", "内容量"):
            skip_next = True
            continue
        if l == "商品詳細" or l.startswith("内容量") or re.match(r"^(香り|コク|酸味|苦味)：", l):
            continue
        if ROAST_PATTERN.fullmatch(l):
            continue
        desc_lines.append(l)
    desc = " ".join(desc_lines)[:400] or None
    roast_line = next((l for l in lines if ROAST_PATTERN.fullmatch(l)), None)
    rm = ROAST_PATTERN.search(wm.group(2)) if wm and wm.group(2) else None
    rm = rm or ROAST_PATTERN.search(name) or (ROAST_PATTERN.fullmatch(roast_line) if roast_line else None)         or re.search(r"(極深煎り|中深煎り|中浅煎り|深煎り|中煎り|浅煎り)", desc or "")
    roast = rm.group(1) if rm else None
    if roast and not roast.endswith("り"):
        roast += "り"

    is_decaf = "カフェインレス" in name
    parsed = parse_product(name)
    if "ブレンド" not in name and len(origins) == 1:
        parsed["category"] = "ストレート"
        c = detect_country_name(origins[0]) if origins else None
        c = c or detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "product_page"
        parsed = apply_category_hint_fallback(parsed, name)
    else:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    stock_status = detect_stock_status(list_name, sold_out)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": origins if parsed["category"] == "ブレンド" and len(origins) > 1 else [],
        "decaf_process": ("超臨界二酸化炭素抽出法によりカフェインを97%除去" if "超臨界二酸化炭素" in (desc or "") else "デカフェ(除去方法の詳細記載なし)") if is_decaf else None,
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, cat in list_items():
        try:
            rec = build_record(item_id, name, cat)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_id} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeelabo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeelabo.json に出力しました")


if __name__ == "__main__":
    main()
