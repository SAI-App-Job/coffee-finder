# -*- coding: utf-8 -*-
"""
scrape_cafedetoyo.py

カフェ・ド・トーヨー(toyo-coffee.com、株式会社カフェ・ド・トーヨー、〒664-0832
兵庫県伊丹市下河原1丁目3番16号、自家焙煎コーヒー豆専門店)の商品情報を取得する。
emono1カート(smart.emono1.jp、自社ドメイン上の/cathand/配下。Shift_JIS)。

【住所・自家焙煎の確認(2026-10)】
company.html(店舗案内)に所在地「兵庫県伊丹市下河原1丁目3番16号」、業務内容「自家焙煎コーヒー豆の
製造販売」と記載。サイト全体に「自家焙煎コーヒー豆専門店」の表記。

【対象商品について】
実データ確認済み(2026-10時点): 全商品一覧(/cathand/list.php、2ページ・総数40件)のうち、
「<銘柄> 100g」の形式の焙煎豆(ブレンド・シングルオリジン・スペシャルティ・カフェインレス)28件が対象。
5パック入り/MIXBAG(コーヒーバッグ)、ドリップパック、お得セット、カフェオレベース、あまねの雫、
ポップコーン、COFFEE BAG は除外。全商品が100g単位で、容量違いのバリエーションは無い。
一覧に「販売休止中」と表示された商品は完売扱い(stock_status=完売)とする。
価格は一覧の税込表示(¥)。詳細ページの「焙煎度」「使用豆」「【生産高度】【エリア】【品種】
【精製方法】」等を取り出す(詳細ページは同内容が2回出力されるため前半のみ使う)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    normalize_processing_method, ROAST_KEYWORDS,
)

SHOP_INFO = {
    "name": "カフェ・ド・トーヨー",
    "url": "https://toyo-coffee.com/",
    "platform": "emono1カート(独自ドメイン)",
    "address": "兵庫県伊丹市下河原1-3-16",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://toyo-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_SUFFIX = re.compile(r"\s*(\d+)\s*g\s*$", re.IGNORECASE)
EXCLUDE_KEYWORDS = ["パック", "MIXBAG", "セット", "ドリップ", "CAFE AU LAIT", "あまねの雫", "ポップコーン", "COFFEE BAG"]
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ENGLISH_ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)")
DETAIL_LABEL = re.compile(r"^【(生産高度|エリア|農園|品種|精製方法|乾燥方法)】\s*(.+)$")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "shift_jis"
    return BeautifulSoup(resp.text, "html.parser")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 10):
        url = f"{BASE_URL}/cathand/list.php" if page == 1 else f"{BASE_URL}/cathand/list-0-0-{page}-0.html"
        soup = fetch(url)
        products = soup.select("#contents .product")
        if not products:
            break
        for p in products:
            a = p.select_one("h3 a")
            if not a or a["href"] in seen:
                continue
            seen.add(a["href"])
            title = norm(a.get_text(strip=True))
            m = WEIGHT_SUFFIX.search(title)
            if not m or any(k in title for k in EXCLUDE_KEYWORDS):
                continue
            price_el = p.select_one(".price")
            pm = re.search(r"[\d,]+", price_el.get_text()) if price_el else None
            tagline = p.select_one(".inside > p:not(.price):not(.detail)")
            items.append({
                "name": WEIGHT_SUFFIX.sub("", title).strip(),
                "weight": int(m.group(1)),
                "href": a["href"],
                "price": int(pm.group().replace(",", "")) if pm else None,
                "sold_out": "販売休止" in p.get_text() or "売り切れ" in p.get_text() or "SOLD" in p.get_text().upper(),
                "tagline": norm(tagline.get_text()) if tagline else None,
            })
        time.sleep(0.5)
    return items


def parse_detail(href: str) -> tuple[dict, str]:
    soup = fetch(BASE_URL + href)
    lines = [norm(l) for l in soup.get_text("\n", strip=True).split("\n")]
    lines = [l for l in lines if l]
    if "▼詳細" not in lines:
        return {}, ""
    start = lines.index("▼詳細") + 1
    end = next((i for i in range(start, len(lines)) if lines[i] == "関連商品"), len(lines))
    body = lines[start:end]
    # 同じ内容が2回繰り返される(2回目はラベルと値が改行で分かれる)ため、先頭行が再登場した位置で切る
    if body and body[0] in body[1:]:
        body = body[: body.index(body[0], 1)]
    labels, desc = {}, []
    for ln in body:
        m = re.match(r"^(焙煎度|使用豆)\s*[：:]\s*(.*)$", ln)
        if m:
            labels[m.group(1)] = m.group(2).strip()
            continue
        m = DETAIL_LABEL.match(ln)
        if m:
            labels[m.group(1)] = m.group(2).strip()
        elif ln != "特徴":
            desc.append(ln.lstrip("・"))
    return labels, " ".join(desc)


def build_record(it: dict) -> dict:
    labels, desc = parse_detail(it["href"])
    name = it["name"]
    beans = labels.get("使用豆", "")
    parsed = parse_product(name)
    is_blend = parsed["category"] == "ブレンド" or "・" in beans or "他" in beans or "ブレンド" in beans
    processing = None
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and beans:
            c = detect_country_name(beans)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"
        processing = parsed["processing_method"]
        if not processing and labels.get("精製方法"):
            processing = normalize_processing_method(labels["精製方法"])
    roast_text = labels.get("焙煎度", "")
    hint = ROAST_HINT_PATTERN.search(roast_text)
    # 「中煎り」等の日本語表記は8段階と粒度が異なるためroast_hintに保持し、
    # 「ハイロースト」等の8段階表記が明示されている場合のみroast_levelに入れる
    roast_level = None
    if "ロースト" in roast_text:
        for kw, rl in ROAST_KEYWORDS.items():
            if kw in roast_text:
                roast_level = rl
                break
    farm_bits = [f"{k}: {labels[k]}" for k in ("農園", "エリア", "生産高度", "品種") if labels.get(k)]
    notes = " ".join(x for x in [it["tagline"], desc] if x)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": hint.group(1) if hint else None,  # スペシャルブレンドは原文が「焙煎度:煎り」(程度の記載欠落)のためNone
        "flavor_notes": notes[:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": BASE_URL + it["href"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        try:
            records.append(build_record(it))
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {it['href']} ({e})")
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafedetoyo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafedetoyo.json に出力しました")


if __name__ == "__main__":
    main()
