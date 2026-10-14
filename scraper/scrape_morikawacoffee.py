# -*- coding: utf-8 -*-
"""
scrape_morikawacoffee.py

株式会社モリカワ(MORIKAWA COFFEE／お茶とコーヒーの店 もりかわ、morikawa-coffee.jp、
和歌山県田辺市城山台2-10。昭和2年創業・紀州備長炭炭火焙煎が特徴)の商品情報を取得する。独自カート。

【店舗発見の経緯】
全国再調査(和歌山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧 `/category/regular/32`(コーヒー豆の全商品一覧、
ストレート24点+ブレンド26点)と、アイスコーヒー一覧 `/category/ice/32` のうち豆商品
(「アイスコーヒー専用【ブルーマウンテンNO.1ブレンド】 100g」)を対象とする。商品一覧・詳細は
サーバーレンダリングの静的HTMLで、価格は `<span class="h3">793</span> 円(税込み)`。
同じ商品でもカテゴリごとに別の商品ID(/products/detail/N)が付くため、商品名で重複を除く。
除外: ドリップバッグ、アイス瓶・パック・リキッド、ギフト・セット、「曜日珈琲(28日分)」(7種の詰め合わせ)、
紅茶・茶・雑貨。
重量は商品名の「100g」から取る(名前に重量表記がないブレンド3点は不明のためNone)。
産地(ストレート)・焙煎度は詳細ページの「原産国」「ロースト」から取る。在庫表示はサイトに無いため販売中として扱う。

【robots.txtについて】
`User-agent: *` / `Disallow:` (全許可)。識別可能な独自User-Agentで間隔を空けて取得する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "モリカワ",
    "url": "https://morikawa-coffee.jp/",
    "platform": "独自カート",
    "address": "和歌山県田辺市城山台2-10",
    "prefecture": "和歌山県",
    "robots_txt_status": "許可(User-agent: * / Disallow: 空)",
}

BASE_URL = "https://morikawa-coffee.jp"
LIST_URLS = [
    f"{BASE_URL}/category/regular/32",
    f"{BASE_URL}/category/ice/32",
]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

CARD_PATTERN = re.compile(
    r'detail/(\d+)"><img.*?<div class="text-center bpl4 bpr4">(.*?)</div>.*?<span class="h3">([\d,]+)</span>',
    re.S,
)
EXCLUDE_PATTERN = re.compile(r"(ドリップバッグ|ギフト|セット|曜日珈琲|飲みくらべ|瓶|水出し|パック|ℓ|ml|紅茶|茶葉|ティーバッグ|煎茶|ほうじ茶|焙じ茶|化粧袋)")
BEAN_WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\b", re.IGNORECASE)
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")

# 詳細ページの原産国表記から日本語国名への補正(辞書で検出できないもの)
ORIGIN_NORMALIZE = {"ジャマイカ": "ジャマイカ"}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return resp.text


def clean_name(raw: str) -> str:
    name = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    name = name.replace("　", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def strip_weight(name: str) -> str:
    return re.sub(r"\s*\d+\s*g\s*$", "", name, flags=re.IGNORECASE).strip()


def collect_cards() -> list[dict]:
    """一覧ページから (id, 名前, 価格, 区分) を集め、商品名で重複を除く。"""
    cards: list[dict] = []
    seen_names: set[str] = set()
    for list_url in LIST_URLS:
        html_text = fetch(list_url)
        # 「ブレンド」見出し以降をブレンド区分とする(regular/32: ストレート→ブレンド、ice/32: ブレンドのみ)
        blend_pos = None
        for m in re.finditer(r'<div class="h3"[^>]*>\s*([^<]+?)\s*</div>', html_text):
            if m.group(1) == "ブレンド":
                blend_pos = m.start()
                break
        for m in CARD_PATTERN.finditer(html_text):
            name = clean_name(m.group(2))
            if EXCLUDE_PATTERN.search(name):
                continue
            key = re.sub(r"\s+", "", name)
            if key in seen_names:
                continue
            seen_names.add(key)
            is_blend = (blend_pos is not None and m.start() > blend_pos) or "ice" in list_url
            cards.append({
                "id": m.group(1),
                "name": name,
                "price": int(m.group(3).replace(",", "")),
                "is_blend": is_blend,
            })
        time.sleep(1)
    return cards


def parse_detail(html_text: str) -> dict:
    main = html_text[html_text.find("<main"):]
    soup = BeautifulSoup(main, "html.parser")
    lines = [re.sub(r"\s+", " ", l).strip() for l in soup.get_text("\n").split("\n")]
    lines = [l for l in lines if l]
    info = {"origin": None, "roast": None, "selling": None, "desc": None, "taste": None}

    def after(label: str) -> str | None:
        for i, l in enumerate(lines):
            if l == label and i + 1 < len(lines):
                return lines[i + 1]
        return None

    info["origin"] = after("原産国：")
    info["roast"] = after("ロースト：")
    info["selling"] = after("セールスポイント：")
    # ロースト行の次から「金額：」までが説明文
    try:
        start = lines.index("ロースト：") + 2
        end = lines.index("金額：")
        info["desc"] = " ".join(lines[start:end]).strip() or None
    except ValueError:
        pass
    return info


def normalize_roast(label: str | None) -> str | None:
    if not label:
        return None
    m = ROAST_PATTERN.search(label)
    return m.group(1) if m else None


def build_record(card: dict) -> dict | None:
    url = f"{BASE_URL}/products/detail/{card['id']}"
    info = parse_detail(fetch(url))
    time.sleep(1)

    name = card["name"]
    weight_m = BEAN_WEIGHT_PATTERN.search(name)
    weight_g = int(weight_m.group(1)) if weight_m else None
    raw_name = strip_weight(name)

    parsed = parse_product(raw_name)
    if parsed["is_flavored"]:
        return None
    if card["is_blend"]:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        origin = info["origin"]
        if origin:
            country = detect_country_name(origin) or origin
            parsed["origin_country"] = country
            parsed["origin_source"] = "description"
        elif not parsed["origin_country"]:
            detected = detect_country_name(raw_name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, raw_name)

    notes = " ".join(x for x in [info["selling"], info["desc"]] if x)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": normalize_roast(info["roast"]) or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": notes[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": card["price"],
        "weight_g": weight_g,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for card in collect_cards():
        try:
            record = build_record(card)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: id={card['id']} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_morikawacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_morikawacoffee.json に出力しました")


if __name__ == "__main__":
    main()
