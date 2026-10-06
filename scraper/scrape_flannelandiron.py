# -*- coding: utf-8 -*-
"""
scrape_flannelandiron.py

flannel&IRON coffee roaster(https://shop.coffee-flannel.com/、広島県福山市本庄町中3-25-21)の商品情報を取得する。BASE(独自ドメイン shop.coffee-flannel.com)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【住所について】
特定商取引法ページ(/law)で確認済み(〒720-0076 広島県福山市本庄町中3-25-21、本庄町中焙煎所)。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの商品ページから、自家焙煎の焙煎豆(シングルオリジン・ブレンド・デカフェ)のみを対象とする。
商品名の【中煎り・100g】から焙煎度と重量を取る焙煎豆11商品(sitemap全12商品のうちインフューズド・コーヒー(1,500円)を除外)。
同一銘柄で焙煎度違いの別商品(ウガンダ ルウェンゾリ・ドンキーの中煎り/深煎り)は別商品として扱う。
ドリップバッグ・セット/ギフト・定期便・生豆・器具・飲料・雑貨・菓子・インフューズド等は除外し、
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
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "flannel&IRON coffee roaster",
    "url": "https://shop.coffee-flannel.com/",
    "platform": "BASE",
    "address": "広島県福山市本庄町中3-25-21",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.coffee-flannel.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"(極深煎り|極深煎|中浅煎り|中浅煎|中深煎り|中深煎|浅煎り|浅煎|中煎り|中煎|深煎り|深煎)")
ROAST_LABEL_PATTERN = re.compile(r"(?:焙煎度合い?|焙煎度|ローストレベル|ロースト)\s*[】:：]*\s*(.{0,14})")
PROCESS_LABEL_PATTERN = re.compile(r"(?:精製方法|精製処理|精選方法|精製|プロセス|生産処理)\s*[】:：]*\s*(.{0,30})")
ORIGIN_LABEL_PATTERN = re.compile(r"(?:原産国|生産国|生産地|産地|国)\s*[】:：]*\s*(.{0,20})")


def tidy(s: str) -> str:
    """全角スペース等を半角1つに畳む。"""
    return re.sub(r"\s+", " ", s.replace("\u3000", " ")).strip()


def find_weight(s: str) -> int | None:
    """文字列中の最初の「<数字>g」(全角可)の重量を返す。"""
    m = re.search(r"([0-9０-９]+)\s*[gｇ]", s)
    return int(unicodedata.normalize("NFKC", m.group(1))) if m else None


def coarse_roast(text: str | None) -> str | None:
    """「深煎り」「中浅煎」等の表記を「〜煎り」に統一して返す(極深煎りは深煎りに寄せる)。"""
    if not text:
        return None
    m = ROAST_PATTERN.search(unicodedata.normalize("NFKC", text))
    if not m:
        return None
    r = m.group(1)
    r = r if r.endswith("り") else r + "り"
    return "深煎り" if r == "極深煎り" else r


def roast_from_desc(desc: str) -> str | None:
    """説明文中の「焙煎度合:〜」等のラベル直後だけから焙煎度を取る(説明文全体の誤検出を避ける)。"""
    for m in ROAST_LABEL_PATTERN.finditer(desc or ""):
        r = coarse_roast(m.group(1))
        if r:
            return r
    return None


def process_from_desc(desc: str) -> str | None:
    for m in PROCESS_LABEL_PATTERN.finditer(desc or ""):
        p = detect_processing_method(m.group(1))
        if p:
            return p
    return None


def origin_from_desc(desc: str) -> str | None:
    for m in ORIGIN_LABEL_PATTERN.finditer(desc or ""):
        c = detect_country_name(m.group(1))
        if c:
            return c
    return None


def page_description(page: str) -> str:
    """og:descriptionを返す。空の場合は商品説明(カスタム説明ブロック)のテキストで補う。"""
    m = DESC_PATTERN.search(page)
    desc = html.unescape(m.group(1)) if m else ""
    if desc.strip():
        return desc
    soup = BeautifulSoup(page, "html.parser")
    parts = [p.get_text(" ", strip=True) for p in soup.find_all("p", class_=re.compile("appsItemDetailCustomTag_"))]
    return " ".join(x for x in parts if x)


EXCLUDE_KEYWORDS = ("インフューズド", "ドリップ", "セット", "ギフト")


def classify(item_id: str, title: str, desc: str, page: str) -> dict | None:
    t = tidy(unicodedata.normalize("NFKC", title))
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return None
    m = re.search(r"【([^】]*?)[・･]\s*([0-9]+)\s*g】", t)
    if not m:
        return None
    roast = coarse_roast(m.group(1))
    weight = int(m.group(2))
    # 「【中煎り・100g】」は焙煎度違いの同銘柄を区別するため「【中煎り】」として名称に残す
    name = tidy(t[:m.start()] + f"【{m.group(1).strip()}】")
    return {"name": name, "weight": weight, "roast": roast}



def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    urls = re.findall(r"<loc>([^<]+/items/\d+)</loc>", resp.text)
    return list(dict.fromkeys(urls))


def build_record(url: str, info: dict) -> dict:
    page = info["page"]
    desc_full = info["desc"]
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
        if not parsed["origin_country"]:
            from_desc = origin_from_desc(desc_full)
            if from_desc:
                parsed["origin_country"] = from_desc
                parsed["origin_source"] = "description"
        if not parsed["processing_method"]:
            # 「ウォシュド」(促音なし)等の表記ゆれを正規化してから商品名→説明文の順で精製方法を探す
            parsed["processing_method"] = (
                detect_processing_method(name.replace("ウォシュド", "ウォッシュド"))
                or process_from_desc(desc_full.replace("ウォシュド", "ウォッシュド"))
            )

    roast = info.get("roast") or roast_from_desc(desc_full) or parsed["roast_level"]

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
        desc = page_description(resp.text)
        info = classify(url.rsplit("/", 1)[-1], title, desc, resp.text)
        if info is None:
            continue
        info["page"] = resp.text
        info["desc"] = info.get("desc") or desc
        key = info.get("key") or info["name"]
        w = info["weight"] if info["weight"] is not None else 10**9
        if key not in picked or w < picked[key][0]:
            picked[key] = (w, url, info)

    return [build_record(url, info) for _, url, info in picked.values()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_flannelandiron.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_flannelandiron.json に出力しました")


if __name__ == "__main__":
    main()
