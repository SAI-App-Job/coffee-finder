# -*- coding: utf-8 -*-
"""
scrape_frigoles.py

フリゴレス(FRIGOLES、宮城県柴田郡柴田町船岡新栄2-3-3〈船岡本店〉、公式 frigoles.com、
Yahoo!ショッピング store.shopping.yahoo.co.jp/frigoles「フリゴレス Coffee」)の商品情報を取得する。
自家焙煎のコーヒー豆(発送当日焙煎)を扱うYahoo!ショッピングストア。

【プラットフォームについて】
他のYahoo!ショッピング店舗(scrape_mameyanetshop.py)と同様、店舗の商品一覧(/search.html、
2ページ目は ?page=1)は Next.js の `__NEXT_DATA__` JSON に商品名・価格・URLが埋め込まれている。
ページにより商品リストの格納キーが異なる(1ページ目は items["1"]、2ページ目は items["2"])ため、
items 配下の全リストから `content.items` を持つ RESULT 要素を集める。
実データ確認済み(2026-10): 全43件(30件+13件)。

【対象商品について】
自家焙煎の焙煎豆(ブレンド、シングルオリジン、デカフェ)のみ。カレーパウダー、紙袋、ギフトセット、
ドリップバッグ、水出しコーヒーパック、アイスコーヒー1L(飲料)は除外。
「ありがとうブレンド」(fg-ob41 / fg-w41)と「キリマンジャロ ブレンド」(fg-ob36 / fg-w36)は
同名・同価格・同重量の重複ページのため、先に出現した方のみを採用する。

【重量・価格について】
全て200g単位の1種類のみ販売(100g設定なし)。デカフェ2種(グアテマラ、エチオピア)等でタイトルに
重量が無い場合は説明文の「生豆200g」から取得。説明文に「表記の価格は生豆200gの価格で、焙煎後は約170g
前後」とある(焙煎の度合いで変動)。価格は一覧JSONの `price`(税込、ポイント還元前)。
焙煎度は購入時に選択式(「豆の焙煎度」オプション、A中浅〜D中深等)の商品が多く、roast_selectable=True。
在庫は商品ページの `item.stock.isAvailable` で判定する。
"""

import html
import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "フリゴレス",
    "url": "https://store.shopping.yahoo.co.jp/frigoles/",
    "platform": "Yahoo!ショッピング",
    "address": "宮城県柴田郡柴田町船岡新栄2-3-3",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(Yahoo!ショッピングストアのrobots.txtは404。/search.htmlのクエリなし・page指定のみ使用)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/frigoles"
LIST_URLS = [f"{BASE_URL}/search.html", f"{BASE_URL}/search.html?page=1"]
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

EXCLUDE_KEYWORDS = ("カレー", "紙袋", "ギフト", "ドリップバッグ", "水出し", "ネルドリップ", "1L")
NOISE_WORDS = ["コーヒー豆", "自家焙煎", "発送当日焙煎", "珈琲ブレンド", "珈琲豆", "コーヒーブレンド",
               "クロロゲン酸", "健康", "カフェインレス", "オリジナルブレンド"]

# 国名がタイトルから自動判定できない銘柄の補完
ORIGIN_OVERRIDES = {
    "エルサルバトル": "エルサルバドル",
    "ブルーマウンテン": "ジャマイカ",
    "エメラルドマウンテン": "コロンビア",
    "トロピカルマウンテン": "パプアニューギニア",
    "モカクイーン": "エチオピア",
    "アマレロPN": "ブラジル",
}


def fetch_list_items() -> list[dict]:
    items: list[dict] = []
    for url in LIST_URLS:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
        if not m:
            continue
        data = json.loads(m.group(1))
        groups = data["props"]["initialState"]["bff"]["searchResults"]["items"]
        for entries in groups.values():
            for entry in entries:
                content = entry.get("content") or {}
                if isinstance(content.get("items"), list):
                    items.extend(i for i in content["items"] if "name" in i)
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def fetch_detail(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("utf-8")
    soup = BeautifulSoup(text, "html.parser")
    og = soup.select_one('meta[property="og:description"]')
    desc = None
    if og and og.get("content"):
        raw = html.unescape(og["content"])
        desc = BeautifulSoup(raw.replace("<br>", "\n"), "html.parser").get_text("\n", strip=True)
    available, roast_selectable = True, False
    m = NEXT_DATA_PATTERN.search(text)
    if m:
        item = json.loads(m.group(1))["props"]["pageProps"].get("item") or {}
        available = bool((item.get("stock") or {}).get("isAvailable", True))
        roast_selectable = any("焙煎" in (o.get("name") or "") for o in item.get("selectOptionList") or [])
    return {"desc": desc, "available": available, "roast_selectable": roast_selectable}


def clean_name(title: str) -> str:
    name = unicodedata.normalize("NFKC", title)
    name = re.sub(r"\s*(\d+)\s*[gG].*$", "", name)  # 重量以降(「発送当日焙煎…」等の宣伝文)を落とす
    for w in NOISE_WORDS:
        name = name.replace(w, " ")
    name = re.sub(r"(?<!アイス)コーヒー", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace("アイスコーヒー アイスコーヒー用", "アイスコーヒー用")
    return name


def build_record(item: dict) -> dict | None:
    title = (item.get("name") or "").strip()
    if not title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    url = (item.get("url") or "").split("?")[0]
    time.sleep(CRAWL_DELAY_SECONDS)
    detail = fetch_detail(url)

    norm_title = unicodedata.normalize("NFKC", title)
    wm = re.search(r"(\d+)\s*[gG]", norm_title)
    weight = int(wm.group(1)) if wm else None
    if weight is None and detail["desc"]:
        dm = re.search(r"生豆\s*(\d+)\s*[gｇ]", unicodedata.normalize("NFKC", detail["desc"]))
        weight = int(dm.group(1)) if dm else None

    name = clean_name(title)
    # デカフェ表記が名称から落ちた場合に備え、元タイトルにあれば付ける
    if "デカフェ" in title and "デカフェ" not in name:
        name += " デカフェ"
    if "カフェインレス" in title and "デカフェ" not in name and "カフェインレス" not in name:
        name += " カフェインレス"

    parsed = parse_product(name)
    is_blend = "ブレンド" in name or "アイスコーヒー用" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        override = next((c for k, c in ORIGIN_OVERRIDES.items() if k in name), None)
        detected = override or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and detail["desc"]:
            om = re.search(r"原産国\s*[:：]\s*(\S+)", detail["desc"])
            d = detect_country_name(om.group(1)) if om else None
            if d:
                parsed["origin_country"] = d
                parsed["origin_source"] = "description"

    desc = detail["desc"]
    if desc:
        desc = re.sub(r"\s+", " ", desc)[:400]

    out = not detail["available"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_selectable": detail["roast_selectable"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records, seen_names = [], set()
    for item in fetch_list_items():
        rec = build_record(item)
        if not rec:
            continue
        key = (rec["raw_name"].replace(" ", ""), rec["price"], rec["weight_g"])
        if key in seen_names:
            continue
        seen_names.add(key)
        records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_frigoles.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_frigoles.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_selectable"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
