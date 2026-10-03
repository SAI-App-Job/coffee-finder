# -*- coding: utf-8 -*-
"""
scrape_kcoffeebeans.py

kamakuracoffeebeans(鎌倉コーヒー豆.com、kcoffeebeans.shop-pro.jp、神奈川県鎌倉市御成町10-8、
運営は株式会社中島珈琲・焙煎士 中島康雄、葉山で40年続いた「cafeもうひとつの風景」の珈琲豆店)の
通販サイトの商品情報を取得する。カラーミーショップ(charset=euc-jp、product-list__*テーマ)。

【自家焙煎・住所の確認(2026-10)】
公式サイト https://kamakuracoffee.secret.jp/ に「自家焙煎珈琲豆販売」「鎌倉市 御成町10-8」、
通販サイトのトップに「スペシャルティー珈琲豆を自家焙煎し最高の味になるようにブレンド…焙煎士 中島康雄」
とある。特定商取引法ページの住所は神奈川県鎌倉市御成町10-8。単独店舗。

【更新状況の注意】
商品ページの更新は2017〜2020年(商品画像のタイムスタンプ最終2020-10)、公式ブログの最終投稿は2018年と
古い。ただしショップのロゴ/ファビコンは2025-12-23付で更新されており(shop-pro管理画面の更新)、
運営は継続中と判断した。価格は税込(8%、100g 810円等)で、商品ページ自体は長期間変更されていない
可能性がある(価格が現行かどうかは店頭で未確認)。

【対象商品について】
実データ確認済み(2026-10時点): 「珈琲豆」カテゴリ(cbid=2254870、全17件)と
「押尾コータロー15thアニバーサリー…」カテゴリ(cbid=2415233)から巡回する。同一銘柄は100g/200gの別商品の
ため最小サイズ(100g)のみ収録する。除外: レターパック(400g送料無料の同一ブレンド)、名前入りブレンド
(受注生産のギフト・売切れで価格なし)、押尾コータロー15thアニバーサリーブレンドコーヒーセット(セット)。
銘柄名に「ブレンド」を含まない「鎌倉珈琲物語」「鎌倉人」「摩訶 深煎」は商品説明・レターパック名から
ブレンドと確認できるため(FORCE_BLEND_NAMES)ブレンド扱い。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "kamakuracoffeebeans",
    "url": "https://kcoffeebeans.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "神奈川県鎌倉市御成町10-8",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。User-agent: *は/secure/と/cart/のみ制限=shop-pro共通)",
}

BASE_URL = "https://kcoffeebeans.shop-pro.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = ["2254870", "2415233"]
EXCLUDE_KEYWORDS = ("レターパック", "名前入り", "セット", "グッズ", "ギフト")
FORCE_BLEND_NAMES = ("鎌倉珈琲物語", "鎌倉人", "摩訶")

WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り|深煎)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def weight_of(text: str) -> int | None:
    m = WEIGHT_PATTERN.search(text)
    if not m:
        return None
    value = float(m.group(1))
    return int(value * 1000) if m.group(2).lower() == "kg" else int(value)


def clean_name(title: str) -> str:
    name = WEIGHT_PATTERN.sub(" ", title)
    name = re.sub(r"ブレンド豆", "ブレンド", name)
    name = re.sub(r"珈琲豆|コーヒー豆|パック", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def list_items() -> list[dict]:
    items, seen = [], set()
    for cbid in CATEGORY_IDS:
        soup = BeautifulSoup(fetch(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0"), "html.parser")
        for card in soup.select("li.product-list__unit"):
            a = card.select_one("a.product-list__name")
            pid_m = re.search(r"pid=(\d+)", a.get("href", "")) if a else None
            if not pid_m or pid_m.group(1) in seen:
                continue
            seen.add(pid_m.group(1))
            price_el = card.select_one(".product-list__price")
            price_m = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
            items.append({
                "pid": pid_m.group(1),
                "title": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", a.get_text(strip=True))).strip(),
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "sold_out": "SOLD OUT" in card.get_text(),
            })
        time.sleep(0.3)
    return items


def fetch_explain(pid: str) -> str | None:
    soup = BeautifulSoup(fetch(f"{BASE_URL}/?pid={pid}"), "html.parser")
    ex = soup.select_one(".product__explain")
    text = re.sub(r"\s+", " ", ex.get_text(" ", strip=True)) if ex else ""
    return unicodedata.normalize("NFKC", text)[:300] or None


def build_record(item: dict, explain: str | None) -> dict:
    name = clean_name(item["title"])
    parsed = parse_product(name)
    if any(k in name for k in FORCE_BLEND_NAMES):
        parsed["category"] = "ブレンド"
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["processing_method"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    hint_m = ROAST_HINT_PATTERN.search(name + " " + (explain or ""))
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
        "roast_hint": ("深煎り" if hint_m and hint_m.group(1) == "深煎" else hint_m.group(1)) if hint_m else None,
        "flavor_notes": explain,
        "farm_note": None,
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
    best: dict[str, dict] = {}
    for it in items:
        key = re.sub(r"\s+", "", clean_name(it["title"]))
        it["_w"] = weight_of(it["title"]) or 10**9
        if key not in best or it["_w"] < best[key]["_w"]:
            best[key] = it
    records = []
    for it in best.values():
        try:
            explain = fetch_explain(it["pid"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={it['pid']} ({e})")
            continue
        records.append(build_record(it, explain))
        time.sleep(0.3)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kcoffeebeans.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kcoffeebeans.json に出力しました")


if __name__ == "__main__":
    main()
