# -*- coding: utf-8 -*-
"""
scrape_keyakicoffee.py

KEYAKI COFFEE(https://keyakicoffee.base.shop/、宮城県仙台市若林区卸町1-3-1 2F)の商品情報を取得する。BASE(base.shop)。

【店舗発見の経緯】
全国再調査(宮城県)の新規発掘で発見。

【住所について】
特定商取引法ページ(/law)の所在地(〒984-0015 宮城県仙台市若林区卸町1-3-1 2階)を採用する(店舗は【本店】と【卸町店】の2店。依頼元の注記では本店は若林区なないろの里2-27-15)。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの全商品のうち、自家焙煎の焙煎豆(シングルオリジン・ブレンド・デカフェ)のみを対象とする。
【焙煎度/産地】形式の商品名の焙煎豆(100g/150g)を対象。同一銘柄の500g・1kgは最小重量(150g)を代表とするため採用しない。定期便・ドリップバッグ・各種セット・焼き菓子・フィルター・ラッピングは除外。トップページはJS描画のためsitemap.xmlから商品URLを取得する。
ドリップバッグ・セット/ギフト・定期便・生豆・器具・飲料・雑貨・菓子等は除外し、
同一銘柄が重量違いの別ページで並ぶ場合は最小重量のページを代表とする。
重量は商品名の「<数字>g」表記、無ければ商品ページのバリエーション名から取得する。
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
    detect_processing_method,
)

SHOP_INFO = {
    "name": "KEYAKI COFFEE",
    "url": "https://keyakicoffee.base.shop/",
    "platform": "BASE",
    "address": "宮城県仙台市若林区卸町1-3-1 2F",
    "prefecture": "宮城県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://keyakicoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
VARIATION_PATTERN = re.compile(r'class="[^"]*variationName[^"]*"[^>]*>([^<]*)<')
ROAST_PATTERN = re.compile(r"(極深煎り|極深煎|中浅煎り|中浅煎|中深煎り|中深煎|浅煎り|浅煎|中煎り|中煎|深煎り|深煎)")
ROAST_ENGLISH_PATTERN = re.compile(r"(フルシティ|シティ|フレンチ|イタリアン|ハイ|ミディアム|ライト|シナモン|ジャーマン)ロースト")
WEIGHT_PATTERN = re.compile(r"([0-9０-９]+(?:\.[0-9]+)?)\s*(kg|ｋｇ|KG|g|ｇ|G)(?![a-zA-Z])")

# タイトル末尾の「| ショップ名 powered by BASE」を落とす
TITLE_SUFFIX_PATTERN = re.compile(r"\s*\|\s*[^|]*powered by BASE\s*$")
# 非対象商品(ドリップバッグ・セット・菓子等)のキーワード
EXCLUDE_KEYWORDS = ("定期", "セット", "ドリップバッグ", "ギフト", "サブレ", "クッキー", "Kalita", "FILTER", "ラッピング")
# 商品名に焙煎度が無い場合に、説明文(og:description)の先頭何文字から焙煎度を探すか(0なら探さない)
DESC_ROAST_CHARS = 0
DESC_PROCESS_PATTERNS = (
    re.compile(r"(?:製法|精製|精選)[：:]\s*([^\s、。]+)"),
    re.compile(r"Process\s*\|\s*([A-Za-z]+?)(?:Profile|\s|$)"),
)
# 商品ID -> 上書き(category / origin / roast / name)。商品名だけでは判定できないもの
ITEM_OVERRIDES = {}


def tidy(s: str) -> str:
    """全角スペース等を半角1つに畳む(NFKC正規化はしない)。"""
    s = re.sub(r"\s+", " ", s.replace("　", " ")).strip()
    return re.sub(r"【\s+", "【", re.sub(r"\s+】", "】", s))


def find_weights(s: str) -> list[int]:
    out = []
    for m in WEIGHT_PATTERN.finditer(s):
        num = float(unicodedata.normalize("NFKC", m.group(1)))
        unit = unicodedata.normalize("NFKC", m.group(2)).lower()
        out.append(int(num * 1000) if unit == "kg" else int(num))
    return out


def coarse_roast(text: str | None) -> str | None:
    """「深煎」「中深煎」「浅め焙煎」等の表記を「〜煎り」に統一して返す。"""
    if not text:
        return None
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("中煎りやや浅め", "中浅煎り").replace("やや浅め焙煎", "中浅煎り").replace("浅め焙煎", "浅煎り")
    m = ROAST_PATTERN.search(t)
    if not m:
        return None
    r = m.group(1)
    return r if r.endswith("り") else r + "り"


def classify(item_id: str, title: str, page: str) -> dict | None:
    t = tidy(title)
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return None
    weights = find_weights(t)
    if not weights:
        for v in VARIATION_PATTERN.findall(page):
            weights += find_weights(unicodedata.normalize("NFKC", v))
    ov = ITEM_OVERRIDES.get(item_id, {})
    if not weights and "weight" not in ov:
        return None
    weight = ov.get("weight") or min(weights)
    name = tidy(WEIGHT_PATTERN.sub("", t))

    info = {"name": name, "weight": weight}
    info.update(ov)
    return info


def name_key(name: str) -> str:
    """重量違いの別ページを同一銘柄とみなすためのキー。"""
    return name


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
        if not parsed["processing_method"]:
            for pat in DESC_PROCESS_PATTERNS:
                pm_m = pat.search(desc_full)
                if pm_m and detect_processing_method(pm_m.group(1)):
                    parsed["processing_method"] = detect_processing_method(pm_m.group(1))
                    break

    roast = info.get("roast") or coarse_roast(name) or parsed["roast_level"]
    if not roast and DESC_ROAST_CHARS:
        roast = coarse_roast(desc_full[:DESC_ROAST_CHARS])
    if not roast:
        m = ROAST_ENGLISH_PATTERN.search(desc_full)
        roast = m.group(0) if m else None

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
        title = TITLE_SUFFIX_PATTERN.sub("", html.unescape(title_m.group(1))).strip()
        info = classify(url.rsplit("/", 1)[-1], title, resp.text)
        if info is None:
            continue
        info["page"] = resp.text
        key = name_key(info["name"])
        if key not in picked or info["weight"] < picked[key][0]:
            picked[key] = (info["weight"], url, info)

    return [build_record(url, info) for _, url, info in picked.values()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_keyakicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_keyakicoffee.json に出力しました")


if __name__ == "__main__":
    main()
