# -*- coding: utf-8 -*-
"""
scrape_supplecoffee.py

Supple Coffee Roasters(https://supplecoffee.thebase.in、岐阜県郡上市八幡町本町865-1)の商品情報を取得する。BASE(thebase.in)。

【店舗発見の経緯】
全国再調査(岐阜県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xml全28商品のうち、自家焙煎の焙煎豆6商品のみを対象とする
(エチオピア コチャレ ナチュラル/ウォッシュド、コスタリカ ラ・カンデリージャ、エスプレッソ・カフェオレ用ブレンド、
ブラジル グアリロバ「FRUITY」、コスタリカ エル・ディアマンテ100g)。
Tシャツ・パーカー・手ぬぐい・ステッカー・カッティングシート・マグ・雑誌、コールドブリューバッグ、ドリップバッグギフト、
レターパックライト発送の「おまかせ3種」「100g×3パック」(セット)は除外。
商品名先頭の「（通常配送）」は発送方法の注記なので銘柄名から除く。
ブラジル グアリロバ「FRUITY」は商品名・説明に重量表記がないため重量はnull(品切れ中)。
焙煎度は商品ページに記載がないためnull。
価格(product:price:amount)・在庫(item_purchasability)・説明(og:description)は商品ページから取得し、
説明先頭の「※2023/10/15 価格改定致しました。」は除く。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re
import unicodedata

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "Supple Coffee Roasters",
    "url": "https://supplecoffee.thebase.in/",
    "platform": "BASE",
    "address": "岐阜県郡上市八幡町本町865-1",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://supplecoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_WORD = re.compile(r"(極深煎り|極深煎|中浅煎り|中浅煎|中深煎り|中深煎|浅煎り|浅煎|中煎り|中煎|深煎り|深煎)")
ROAST_TERM = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティー?|シティー?|フレンチ|イタリアン)\s*ロースト")
WEIGHT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(kg|g)", re.I)


def tidy(s: str) -> str:
    """全角スペース等を半角1つに畳む(NFKC正規化はしない)。"""
    return re.sub(r"\s+", " ", s.replace("\u3000", " ")).strip()


def find_weight(s: str) -> int | None:
    """文字列中の最初の「<数字>g/kg」(全角可)の重量(g)を返す。"""
    m = WEIGHT_RE.search(unicodedata.normalize("NFKC", s))
    if not m:
        return None
    v = float(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
    return int(v)


def coarse_roast(text: str | None) -> str | None:
    """「深煎り」「中浅煎」等の表記を「〜煎り」に統一して返す。"""
    if not text:
        return None
    m = ROAST_WORD.search(unicodedata.normalize("NFKC", text))
    if not m:
        return None
    r = m.group(1)
    return r if r.endswith("り") else r + "り"


def term_roast(text: str | None) -> str | None:
    """「ハイロースト」「フルシティーロースト」等の表記を「〜ロースト」に統一して返す。"""
    if not text:
        return None
    m = ROAST_TERM.search(unicodedata.normalize("NFKC", text))
    if not m:
        return None
    return m.group(1).rstrip("ー") + "ロースト"

BEAN_HINTS = ("ethiopia", "costa rica", "brazil", "espresso")
EXCLUDE_KEYWORDS = ("Tee", "TEE", "手ぬぐい", "シート", "sticker", "MAG", "Cold Brew", "ドリップバッグ", "ギフト",
                    "レターパック", "Zip", "summerT", "Long sleeve")


def clean_desc(desc_full: str) -> str | None:
    d = re.sub(r"^※\d{4}/\d{1,2}/\d{1,2}\s*価格改定致しました。", "", desc_full)
    d = re.split(r"※豆挽き|※100g瓶詰め", d)[0]
    return re.sub(r"\s+", " ", d).strip()[:400] or None


def roast_from_desc(desc_full: str) -> str | None:
    return None


def classify(item_id: str, title: str, desc_full: str) -> dict | None:
    t = tidy(title)
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return None
    if not any(h in t.lower() for h in BEAN_HINTS):
        return None
    weight = find_weight(t)
    # 「（通常配送）」は発送方法の注記。「200g入」等の重量表記は銘柄名から落とす
    name = tidy(re.sub(r"^[（(]通常配送[）)]\s*", "", t))
    name = tidy(re.sub(r"\s*[0-9]+\s*g入?\s*$", "", name))
    info = {"name": name, "weight": weight}
    if "ESPRESSO" in name.upper():
        info["category"] = "ブレンド"
    return info


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    urls = re.findall(r"<loc>([^<]+/items/\d+)</loc>", resp.text)
    return list(dict.fromkeys(urls))


def build_record(url: str, info: dict) -> dict:
    page = info["page"]
    desc_full = info["desc"]
    desc = clean_desc(desc_full)
    price_m = PRICE_PATTERN.search(page)
    pm = PURCHASABILITY_PATTERN.search(page)
    sold_out = bool(pm) and pm.group(1) == "unpurchasable"

    name = info["name"]
    parsed = parse_product(name)
    if info.get("category"):
        parsed["category"] = info["category"]
    if parsed["category"] == "ブレンド":
        # ブレンドの商品名中の等級・銘柄名は単一産地の属性ではないため落とす
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["grade"] = None
        parsed["designated_brand"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if info.get("origin"):
            parsed["origin_country"] = info["origin"]
            parsed["origin_source"] = "raw_name"
        if not parsed["processing_method"]:
            parsed["processing_method"] = extract_from_description(desc_full.replace("　", "\n"))["processing_method"]

    roast = info.get("roast") or parsed["roast_level"] or roast_from_desc(desc_full)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": info["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    picked: dict[str, tuple[int, str, dict]] = {}
    for url in fetch_item_urls():
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        resp.encoding = "utf-8"
        title_m = TITLE_PATTERN.search(resp.text)
        if not title_m:
            continue
        title = html.unescape(title_m.group(1)).rsplit(" | ", 1)[0].strip()
        desc_m = DESC_PATTERN.search(resp.text)
        desc_full = html.unescape(desc_m.group(1)) if desc_m else ""
        info = classify(url.rsplit("/", 1)[-1], title, desc_full)
        if info is None:
            continue
        info["page"] = resp.text
        info["desc"] = desc_full
        key = info.get("key") or info["name"]
        w = info["weight"] if info["weight"] is not None else 10**9
        if key not in picked or w < picked[key][0]:
            picked[key] = (w, url, info)

    return [build_record(url, info) for _, url, info in picked.values()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_supplecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_supplecoffee.json に出力しました")
    for r in records:
        print(r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], "|", (r["flavor_notes"] or "")[:30])


if __name__ == "__main__":
    main()
