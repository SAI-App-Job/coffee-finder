# -*- coding: utf-8 -*-
"""
scrape_ishikawacoffee.py

ISHIKAWA COFFEE(石かわ珈琲、ishikawa-coffee.com、神奈川県鎌倉市山ノ内197-52、運営 合同会社MARKS.、
北鎌倉のコーヒー豆専門ロースタリー・カフェ)のオンラインストアの商品情報を取得する。
カラーミーショップ(charset=euc-jp、product-list__*テーマ)。

【自家焙煎・住所の確認(2026-10)】
特定商取引法ページの住所は神奈川県鎌倉市山ノ内197-52。トップ/フッターに「世界各地の厳選された高品質な
スペシャルティコーヒーのニュークロップ(当年度産の生豆)のみを焙煎し、新鮮なうちにご提供しています」、
「石かわ珈琲での焙煎度の基準と呼称を整理しました(2024.5.22)」とあり自家焙煎を確認。単独店舗。
商品更新は2026年(ブレンドの画像が2026-02、シングルオリジンの新着が2026-03・2026-06)と最新。

【対象商品について】
実データ確認済み(2026-10時点): 「ブレンド」(cbid=1407286、3件)と「シングルオリジン」
(cbid=1407287、11件)の全14件。全て200g1サイズのみ(同一銘柄の複数サイズ展開は無い)。
除外(巡回しない): 飲み比べセット・お試しセット・リキッドコーヒー・ドリップバッグ・器具類・グッズ・
Tabisuke Tabizo・ギフト。
価格は一覧の「1,850円(税込1,998円)」のうち税込側(1,998円)を採用する。売り切れは「SOLD OUT」表示
(売切れ時は価格が非表示のためprice=None)。
商品名の「グァテマラ」等の産地・「フレンチロースト」等の焙煎度は商品名から取る。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "ISHIKAWA COFFEE(石かわ珈琲)",
    "url": "https://ishikawa-coffee.com/",
    "platform": "カラーミーショップ",
    "address": "神奈川県鎌倉市山ノ内197-52",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://ishikawa-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = ["1407286", "1407287"]
EXCLUDE_KEYWORDS = ("セット", "ドリップバッグ", "リキッド", "ギフト")

WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.IGNORECASE)
TAX_PRICE_PATTERN = re.compile(r"税込\s*([\d,]+)\s*円")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ー?ロースト")
LABEL_PATTERN = re.compile(r"^(生産者|地域|標高|品種|精製|乾燥|農園|生産国)[:：]\s*(.+)$")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[dict]:
    items, seen = [], set()
    for cbid in CATEGORY_IDS:
        soup = BeautifulSoup(fetch(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0"), "html.parser")
        for card in soup.select(".product-list__unit"):
            a = card.select_one("a.product-list__name")
            pid_m = re.search(r"pid=(\d+)", a.get("href", "")) if a else None
            if not pid_m or pid_m.group(1) in seen:
                continue
            seen.add(pid_m.group(1))
            price_text = card.select_one(".product-list__price")
            price_text = price_text.get_text(" ", strip=True) if price_text else ""
            price_m = TAX_PRICE_PATTERN.search(price_text) or PRICE_PATTERN.search(price_text)
            items.append({
                "pid": pid_m.group(1),
                "title": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", a.get_text(strip=True))).strip(),
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "sold_out": "SOLD OUT" in card.get_text().upper(),
            })
        time.sleep(0.3)
    return items


def fetch_detail(pid: str) -> dict:
    soup = BeautifulSoup(fetch(f"{BASE_URL}/?pid={pid}"), "html.parser")
    info = soup.select_one(".product__info")
    body = unicodedata.normalize("NFKC", info.get_text("\n", strip=True)) if info else ""
    # 売り切れ時は一覧に価格が出ないが、詳細ページには価格が残っている
    price = None
    price_node = soup.find(string=re.compile(r"[\d,]+円\s*[(（]税込"))
    if price_node:
        pm = TAX_PRICE_PATTERN.search(unicodedata.normalize("NFKC", price_node))
        price = int(pm.group(1).replace(",", "")) if pm else None
    labels, story = {}, []
    for ln in (x.strip() for x in body.split("\n")):
        if not ln:
            continue
        m = LABEL_PATTERN.match(ln)
        if m:
            labels[m.group(1)] = m.group(2).strip()
        else:
            story.append(ln)
    return {"labels": labels, "story": " ".join(story), "price": price}


def build_record(item: dict, detail: dict) -> dict:
    name = re.sub(r"\s+", " ", WEIGHT_PATTERN.sub(" ", item["title"])).strip()
    w_m = WEIGHT_PATTERN.search(item["title"])
    weight_g = None
    if w_m:
        weight_g = int(float(w_m.group(1)) * (1000 if w_m.group(2).lower() == "kg" else 1))
    parsed = parse_product(name)
    labels = detail["labels"]
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        processing = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        processing = parsed["processing_method"]
        if not processing and labels.get("精製"):
            processing = normalize_processing_method(labels["精製"])
    roast_m = ROAST_PATTERN.search(name) or ROAST_PATTERN.search(detail["story"][:40])
    farm_bits = [f"{k}: {labels[k]}" for k in ("地域", "農園", "標高", "品種") if labels.get(k)]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": (roast_m.group(1) + "ロースト") if roast_m else None,
        "roast_hint": None,
        "flavor_notes": detail["story"][:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"] if item["price"] is not None else detail.get("price"),
        "weight_g": weight_g,
        "stock_status": "完売" if item["sold_out"] else "販売中",
        "out_of_stock": item["sold_out"],
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        if any(k in it["title"] for k in EXCLUDE_KEYWORDS):
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
    with open("data_ishikawacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ishikawacoffee.json に出力しました")


if __name__ == "__main__":
    main()
