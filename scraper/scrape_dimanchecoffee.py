# -*- coding: utf-8 -*-
"""
scrape_dimanchecoffee.py

カフェ・ヴィヴモン・ディモンシュ(dimanche.shop-pro.jp、神奈川県鎌倉市小町2-1-5 櫻井ビル1F、
有限会社日曜日、鎌倉駅東口徒歩3分、店主 堀内隆志)の通販サイト「dimanche web shop」の
商品情報を取得する。カラーミーショップ(charset=euc-jp、新テーマ c-product-list__*)。

【自家焙煎の確認(2026-10)】
通販サイトのトップに「焙煎」の語は無いが、特定商取引法ページの販売業者は有限会社日曜日
(店舗運営会社)で、商品ページに「焙煎度合いは中深煎り」「この深煎りのゲイシャ…」等の焙煎者視点の
記述があり、第三者媒体(店主が夜明けまで焙煎する日々の取材記事、2010年から自家焙煎のコーヒーを
提供との紹介)でも自家焙煎店であることを確認した。一方、「コロンビア・ミックス」「ヴェラ・クルーズ」
「ソフト・ミックス」の3商品は商品説明に「札幌 斉藤珈琲のコーヒーです」とあり、他店の焙煎豆の
仕入れ販売のため自家焙煎ではないと判断して除外する(説明文の「斉藤珈琲」で機械的に除外)。

【対象商品について】
実データ確認済み(2026-10時点): コーヒー豆の以下カテゴリを巡回する(商品は「同一銘柄を
100g/200g/300g/500g/1kgの別商品ページとして登録」しており、同一銘柄は最小サイズのみ収録する)。
 コーヒー豆200gパック(cbid=1087531、全23件・2ページ) / オトクな300gパック(1137269) /
 かなりオトクな500gパック(2031058) / 大容量1Kバッグ(2781946) / 定番ブレンド(2578982) /
 季節限定(2811901) / マスターズセレクト(2975062) / カフェインレス(2836909)
除外: カップオンコーヒー(ドリップバッグ類)、ギフトセット、器具、雑貨、書籍、CD、Tシャツ等
(上記カテゴリ以外は巡回しない)、斉藤珈琲の仕入れ品3件、カップオンコーヒー。
「FINEST HOUR」は商品名に「ブレンド」を含まないが説明文で「ブレンドです」と明記のためブレンド扱い。
価格は税込(内税)。売り切れは一覧の「SOLD OUT」表示(売切れ時は価格が非表示のためprice=None)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "カフェ・ヴィヴモン・ディモンシュ",
    "url": "https://dimanche.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "神奈川県鎌倉市小町2-1-5 櫻井ビル1F",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://dimanche.shop-pro.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = ["1087531", "1137269", "2031058", "2781946", "2578982", "2811901", "2975062", "2836909"]
EXCLUDE_KEYWORDS = ("Cap on Cup", "カップオン", "ギフト", "セット", "ドリップバッグ", "ドリップパック")
RESALE_MARKERS = ("斉藤珈琲",)
FORCE_BLEND_NAMES = ("FINEST HOUR",)
MAX_PAGES = 5

WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|K)\b", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ー?ロースト")
FARM_LABELS = ("生産国", "地域", "農園名", "標高", "品種", "生産処理")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def weight_of(text: str) -> int | None:
    m = WEIGHT_PATTERN.search(text)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    return int(value * 1000) if unit in ("kg", "k") else int(value)


def strip_weight(text: str) -> str:
    text = WEIGHT_PATTERN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def list_items() -> list[dict]:
    items, seen = [], set()
    for cbid in CATEGORY_IDS:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0" + (f"&page={page}" if page > 1 else "")
            soup = BeautifulSoup(fetch(url), "html.parser")
            cards = soup.select("li.c-product-list__item")
            new = 0
            for card in cards:
                a = card.select_one("a.c-product-list__name")
                if not a:
                    continue
                pid_m = re.search(r"pid=(\d+)", a.get("href", ""))
                if not pid_m or pid_m.group(1) in seen:
                    continue
                seen.add(pid_m.group(1))
                new += 1
                price_el = card.select_one(".c-product-list__price")
                price_m = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
                items.append({
                    "pid": pid_m.group(1),
                    "title": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", a.get_text(strip=True))).strip(),
                    "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                    "sold_out": card.select_one(".c-product-list__soldout") is not None,
                })
            if new == 0 or not soup.find("a", href=re.compile(rf"cbid={cbid}.*page={page + 1}")):
                break
            time.sleep(0.3)
        time.sleep(0.3)
    return items


def fetch_detail(pid: str) -> dict:
    soup = BeautifulSoup(fetch(f"{BASE_URL}/?pid={pid}"), "html.parser")
    desc_el = soup.select_one(".p-product-body__description")
    lines = [ln.strip() for ln in desc_el.get_text("\n", strip=True).split("\n") if ln.strip()] if desc_el else []
    labels = {}
    story = []
    for ln in lines:
        norm = unicodedata.normalize("NFKC", ln)
        m = re.match(r"^(生産国|地域|農園名|標高|品種|生産処理|生産者名)[:：]\s*(.+)$", norm)
        if m:
            labels[m.group(1)] = m.group(2).strip()
        else:
            story.append(norm)
    return {"labels": labels, "story": " ".join(story)}


def build_record(item: dict, detail: dict) -> dict:
    name = strip_weight(item["title"])
    name = re.sub(r"^＜[^＞]*＞\s*", "", name)
    name = re.sub(r"^<[^>]*>\s*", "", name).strip()
    parsed = parse_product(name)
    story = detail["story"]
    if any(k in name for k in FORCE_BLEND_NAMES) or "ブレンド" in name:
        parsed["category"] = "ブレンド"
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and detail["labels"].get("生産国"):
            parsed["origin_country"] = detect_country_name(detail["labels"]["生産国"])
            parsed["origin_source"] = "country_name" if parsed["origin_country"] else None

    labels = detail["labels"]
    farm_bits = [f"{k}: {labels[k]}" for k in ("地域", "農園名", "標高", "品種", "生産処理") if labels.get(k)]
    roast_hint_m = ROAST_HINT_PATTERN.search(name)
    roast_m = ROAST_PATTERN.search(name + " " + story)
    processing = parsed["processing_method"]
    if not processing and labels.get("生産処理"):
        from coffee_parser import normalize_processing_method
        processing = normalize_processing_method(labels["生産処理"])
    if parsed["category"] == "ブレンド":
        processing = None

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
        "roast_hint": roast_hint_m.group(1) if roast_hint_m else None,
        "flavor_notes": story[:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_of(item["title"]),
        "stock_status": "完売" if item["sold_out"] else "販売中",
        "out_of_stock": item["sold_out"],
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    items = [it for it in list_items() if not any(k in it["title"] for k in EXCLUDE_KEYWORDS)]

    # 同一銘柄は最小サイズの1件のみ(重量不明の商品は除外せず、そのまま残す)
    best: dict[str, dict] = {}
    for it in items:
        key = re.sub(r"\s+|イディド", "", strip_weight(it["title"]))  # 「イディド」有無の表記ゆれを同一銘柄として扱う
        w = weight_of(it["title"])
        it["_w"] = w if w is not None else 10**9
        if key not in best or it["_w"] < best[key]["_w"]:
            best[key] = it

    records = []
    for it in best.values():
        try:
            detail = fetch_detail(it["pid"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={it['pid']} ({e})")
            continue
        if any(m in detail["story"] for m in RESALE_MARKERS):
            print(f"[skip] 他店焙煎の仕入れ品: {it['title']}")
            continue
        records.append(build_record(it, detail))
        time.sleep(0.3)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_dimanchecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_dimanchecoffee.json に出力しました")


if __name__ == "__main__":
    main()
