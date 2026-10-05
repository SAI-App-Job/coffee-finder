# -*- coding: utf-8 -*-
"""
scrape_kuronekoyacoffee.py

黒猫屋珈琲店(https://www.kuronekoya-coffee.com/、福岡県福岡市中央区大名1-5-5 月光ビル1F)の商品情報を取得する。BASE(独自ドメイン)。

【店舗発見の経緯】
全国再調査(福岡県)の新規発掘で発見。

【住所について】
特定商取引法ページ(/law)で確認済み(〒810-0041 福岡県福岡市中央区大名1-5-5 月光ビル1F)。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xml全13商品のうち、自家焙煎の焙煎豆(シングルオリジン・ブレンド・デカフェ)のみを対象とする。
全13商品(100g表記)を対象とする。「〜<産地>ベース〜」と付く5商品はオリジナルブレンド、他はストレート(ブラジルショコラは名称のみで産地ブレンドか不明のため商品名から判定)。
商品ページに焙煎度の記載がないため roast_level は null。
ドリップバッグ・セット/ギフト・定期便・生豆・器具・飲料・雑貨・菓子等は除外し、
同一銘柄が重量違いの別ページで並ぶ場合は最小重量のページを代表とする。
価格(product:price:amount)・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
在庫は item_purchasability が unpurchasable の場合のみ完売とし、partially_purchasable(一部バリエーションのみ在庫あり)は販売中とする。

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
    "name": "黒猫屋珈琲店",
    "url": "https://www.kuronekoya-coffee.com/",
    "platform": "BASE",
    "address": "福岡県福岡市中央区大名1-5-5 月光ビル1F",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.kuronekoya-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"(極深煎り|極深煎|中浅煎り|中浅煎|中深煎り|中深煎|浅煎り|浅煎|中煎り|中煎|深煎り|深煎)")


def tidy(s: str) -> str:
    """全角スペース等を半角1つに畳む(NFKC正規化はしない。「～」等の表記は原文のまま残す)。"""
    return re.sub(r"\s+", " ", s.replace("\u3000", " ")).strip()


def find_weight(s: str) -> int | None:
    """文字列中の最初の「<数字>g」(全角可)の重量を返す。"""
    m = re.search(r"([0-9０-９]+)\s*[gｇ]", s)
    return int(unicodedata.normalize("NFKC", m.group(1))) if m else None


def coarse_roast(text: str | None) -> str | None:
    """「深煎り」「中浅煎」等の表記を「〜煎り」に統一して返す。"""
    if not text:
        return None
    m = ROAST_PATTERN.search(unicodedata.normalize("NFKC", text))
    if not m:
        return None
    r = m.group(1)
    return r if r.endswith("り") else r + "り"


def classify(item_id: str, title: str, page: str) -> dict | None:
    t = tidy(title)
    weight = find_weight(t)
    if weight is None:
        return None
    name = tidy(re.sub(r"\s*[0-9０-９]+\s*[gｇ]\s*$", "", t))
    info = {"name": name, "weight": weight}
    if "ベース" in name:
        info["category"] = "ブレンド"
    return info


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    return re.findall(r"<loc>([^<]+/items/\d+)</loc>", resp.text)


def build_record(url: str, info: dict) -> dict:
    page = info["page"]
    desc_m = DESC_PATTERN.search(page)
    desc_full = html.unescape(desc_m.group(1)) if desc_m else ""
    desc = re.sub(r"\s+", " ", desc_full).strip()[:400] or None
    price_m = PRICE_PATTERN.search(page)
    pm = PURCHASABILITY_PATTERN.search(page)
    sold_out = bool(pm) and pm.group(1) == "unpurchasable"

    name = info["name"]
    parsed = parse_product(name)
    if info.get("category"):
        parsed["category"] = info["category"]
    if parsed["category"] == "ブレンド":
        # ブレンドの商品名中の等級(No.2等)・銘柄名(マンデリンベース等)は単一産地の属性ではないため落とす
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

    roast = info.get("roast") or coarse_roast(desc_full_roast_text(desc_full)) or parsed["roast_level"]

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


def desc_full_roast_text(desc_full: str) -> str | None:
    """説明文中の「焙煎度:〜」「[中煎り]」「ロースト:〜」等の焙煎度表記の周辺だけを返す(説明文全体の誤検出を避ける)。"""
    m = re.search(r"(?:焙煎度|ロースト|焙煎)\s*[:：]+\s*([^\s　]{0,20})", desc_full)
    if m:
        return m.group(1)
    m = re.search(r"[\[［【]\s*(極深煎り|中浅煎り?|中深煎り?|浅煎り?|中煎り?|深煎り?)", desc_full)
    if m:
        return m.group(1)
    return None


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
        info = classify(url.rsplit("/", 1)[-1], title, resp.text)
        if info is None:
            continue
        info["page"] = resp.text
        key = info.get("key") or info["name"]
        w = info["weight"] if info["weight"] is not None else 10**9
        if key not in picked or w < picked[key][0]:
            picked[key] = (w, url, info)

    records = []
    for _, url, info in picked.values():
        records.append(build_record(url, info))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kuronekoyacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kuronekoyacoffee.json に出力しました")


if __name__ == "__main__":
    main()
