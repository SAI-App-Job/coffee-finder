# -*- coding: utf-8 -*-
"""
scrape_zenisawa.py

珈琲豆専門店ぜにさわ(zenisawa.ocnk.net、神奈川県大和市中央林間6-1-17、店主 銭澤廣治、水曜定休、
「Zeroハゼロースト」の自家焙煎)の商品情報を取得する。おちゃのこネット(UTF-8)。

【自家焙煎・住所の確認(2026-10)】
特定商取引法ページの販売主は「珈琲豆専門店ぜにさわ(銭澤廣治)」、所在地は神奈川県大和市中央林間6-1-17。
トップに「当店はスペシャルティーコーヒー豆の焙煎専門店です」「ぜにさわの焙煎『Zeroハゼロースト』」
「ぜにさわの豆はすべてZeroハゼローストでお届けします」とあり自家焙煎を確認。単独店舗(店頭販売も行う)。
お知らせの最新は2026-10-03で現行運営(価格も現行)。

【対象商品について】
実データ確認済み(2026-10時点): 「取扱い商品一覧」(product-group/1)の38件のうち、「Zeroハゼロースト」の
コーヒー豆21件(全て100g単位のシングルオリジン、ブレンドは無し)を収録する。除外: 2点/3点セット(6件)、
紅茶・茶葉(9件)、ギフトBOX、石けん(コーヒータブレットは一覧に無い)。同一銘柄の複数サイズ展開は無く、
商品名の「(100g)」が販売単位(商品ページにも「販売単位:100g」)。価格は税込の一覧表示。
在庫は、詳細ページに「カートに入れる」が無ければ完売とする(2026-10時点で完売は0件)。
商品名は「(100g)」「Zeroハゼロースト」を除き、「◯◯産◆」の区切りは空白に直す。「カナリア諸島」「セントヘレナ」は
国名辞書に無いためそのまま産地名として保持する。ZeroハゼローストはROAST_LEVELSの段階に無いためroast_hintにする。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲豆専門店ぜにさわ",
    "url": "https://zenisawa.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "神奈川県大和市中央林間6-1-17",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://zenisawa.ocnk.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
LIST_URL = f"{BASE_URL}/product-group/1"
EXCLUDE_KEYWORDS = ("セット", "ギフト", "BOX", "石けん", "タブレット")
ORIGIN_OVERRIDES = {"カナリア諸島": "カナリア諸島", "セントヘレナ": "セントヘレナ"}

WEIGHT_PATTERN = re.compile(r"[(（]\s*(\d+)\s*g\s*[)）]+")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")
    items, seen = [], set()
    for card in soup.select("li.list_item_cell"):
        a = card.select_one("a[href*='/product/']")
        pid_m = re.search(r"/product/(\d+)", a.get("href", "")) if a else None
        if not pid_m or pid_m.group(1) in seen:
            continue
        seen.add(pid_m.group(1))
        title = unicodedata.normalize("NFKC", card.select_one(".goods_name").get_text(strip=True))
        price_el = card.select_one(".selling_price")
        price_m = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
        items.append({
            "pid": pid_m.group(1),
            "title": title,
            "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        })
    return items


def fetch_detail(pid: str) -> dict:
    soup = BeautifulSoup(fetch(f"{BASE_URL}/product/{pid}"), "html.parser")
    text = soup.get_text("\n", strip=True)
    head = text.split("関連商品")[0]
    desc_el = soup.select_one(".detail_desc .item_desc_text")
    lines = [unicodedata.normalize("NFKC", ln.strip()) for ln in desc_el.get_text("\n", strip=True).split("\n")] if desc_el else []
    labels = {}
    for ln in lines:
        m = re.match(r"^(生産国|品種|生産者|農園|地域)[:：\t]\s*(.+)$", ln)
        if m:
            labels[m.group(1)] = m.group(2).strip()
    # 説明冒頭(テイスティングの短文)をflavor_notesにする。生産情報行・販売単位行以降は含めない。
    story = []
    for ln in lines:
        if re.match(r"^(生産国|販売単位|ぜにさわの豆はすべて)", ln):
            break
        if ln:
            story.append(ln)
    return {
        "in_stock": "カートに入れる" in head,
        "labels": labels,
        "story": " ".join(story),
    }


def build_record(item: dict, detail: dict) -> dict:
    title = item["title"]
    w_m = WEIGHT_PATTERN.search(title)
    weight_g = int(w_m.group(1)) if w_m else None
    name = WEIGHT_PATTERN.sub(" ", title)
    name = re.sub(r"Zeroハゼロースト", " ", name)
    name = re.sub(r"産◆|◆", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        override = next((c for k, c in ORIGIN_OVERRIDES.items() if k in name), None)
        detected = override or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and detail["labels"].get("生産国"):
            c = detect_country_name(detail["labels"]["生産国"])
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"

    farm_bits = [f"{k}: {detail['labels'][k]}" for k in ("生産国", "農園", "品種") if detail["labels"].get(k)]
    sold_out = not detail["in_stock"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": "Zeroハゼロースト",
        "flavor_notes": detail["story"][:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/product/{item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        if "Zeroハゼロースト" not in it["title"] or any(k in it["title"] for k in EXCLUDE_KEYWORDS):
            continue
        try:
            detail = fetch_detail(it["pid"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={it['pid']} ({e})")
            continue
        records.append(build_record(it, detail))
        time.sleep(0.3)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_zenisawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_zenisawa.json に出力しました")


if __name__ == "__main__":
    main()
