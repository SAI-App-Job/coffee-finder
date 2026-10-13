# -*- coding: utf-8 -*-
"""
scrape_mamepolepole.py

豆ポレポレ(www.mamepolepole.okinawa、公式 www.mamepolepole.com、沖縄県沖縄市高原6-2-8。
2024-12に旧住所(中央2-7-46)から移転)の商品情報を取得する。MakeShop(新形式 /view/item/)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「シングルオリジン」(ct70)・「オリジナルブレンド」(ct71)・
「カフェインレス」(ct72)の一覧(各1ページ完結)のうち、焙煎豆(150g、一部【※100g】)を対象とする。
- 除外: コーヒーバッグ(ドリップバッグ)、【ギフト】・セット・飲み比べ、カフェオレベース、器具・グッズ。
- 同じ豆の浅煎り/深煎りが別ページ(インドネシア マンデリン ブルーリントン)で並ぶものは別商品として収録。
- 価格は一覧の税込価格、在庫は一覧の「SOLD OUT」表示(span.itemSoldout)で判定する
  (詳細ページのカートボタンはJSで切り替わるためHTML上は常に購入可能に見える)。
- 説明・農園情報・精製・焙煎度は詳細ページの「商品説明」欄から取得する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "豆ポレポレ",
    "url": "https://www.mamepolepole.okinawa/",
    "platform": "MakeShop",
    "address": "沖縄県沖縄市高原6-2-8",
    "prefecture": "沖縄県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.mamepolepole.okinawa"
CATEGORIES = [("ct70", "ストレート"), ("ct71", "ブレンド"), ("ct72", "ストレート")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ("ギフト", "セット", "コーヒーバッグ", "バッグ", "カフェオレ", "オーレ", "ドリップ", "Tシャツ")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ITEM_ID = re.compile(r"/view/item/(\d+)")
PRICE = re.compile(r"([\d,]+)\s*円")
FARM_LABEL = r"生産地域|農園|生産者|標高|品種|精製方法|精製|proces+"
FARM_PATTERN = re.compile(
    r"(" + FARM_LABEL + r")\s*(?:region|farmer|farm|elevation|variety|process)?\s*[:：]\s*(.+?)(?=\s(?:" + FARM_LABEL + r"|焙煎度合い)\s*(?:region|farmer|farm|elevation|variety|process)?\s*[:：]|$)",
    re.IGNORECASE,
)
FARM_LABELS = ("生産地域", "農園", "生産者", "標高", "品種", "精製方法", "精製", "産地", "原産国")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def parse_list() -> list[dict]:
    items: dict[str, dict] = {}
    for cat, default_category in CATEGORIES:
        soup = fetch(f"{BASE_URL}/view/category/{cat}")
        for li in soup.select("li.itemList__unit"):
            a = li.find("a", href=ITEM_ID)
            name_el = li.select_one(".itemName")
            price_el = li.select_one(".itemPrice")
            if not (a and name_el and price_el):
                continue
            item_id = ITEM_ID.search(a["href"]).group(1)
            name = unicodedata.normalize("NFKC", name_el.get_text(strip=True))
            if any(k in name for k in NON_BEAN_KEYWORDS):
                continue
            pm = PRICE.search(price_el.get_text())
            wm = WEIGHT_PATTERN.search(name)
            if not (pm and wm):
                continue
            if item_id in items:
                continue
            items[item_id] = {
                "id": item_id,
                "name": name,
                "category": "ブレンド" if cat == "ct71" else default_category,
                "price": int(pm.group(1).replace(",", "")),
                "weight_g": int(wm.group(1)),
                "out_of_stock": li.select_one(".itemSoldout") is not None,
            }
    return list(items.values())


def fetch_detail(item_id: str) -> list[str]:
    soup = fetch(f"{BASE_URL}/view/item/{item_id}")
    lines = [unicodedata.normalize("NFKC", ln.strip()) for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    if "商品説明" in lines:
        a = lines.index("商品説明")
        b = lines.index("内容", a) if "内容" in lines[a:] else min(len(lines), a + 40)
        return lines[a + 1:b]
    return []


LABEL_ONLY = re.compile(r"^(?:" + FARM_LABEL + r")\s*(?:region|farmer|farm|elevation|variety|process)?\s*[:：]?$", re.IGNORECASE)


def merge_label_lines(lines: list[str]) -> list[str]:
    """「生産地域 region:」と値が別の行に分かれている表記を1行にまとめる。"""
    merged: list[str] = []
    pending = ""
    for ln in lines:
        cur = f"{pending} {ln}".strip() if pending else ln
        if LABEL_ONLY.match(cur):
            pending = cur
            continue
        pending = ""
        merged.append(cur)
    if pending:
        merged.append(pending)
    return merged


def clean_name(name: str) -> str:
    name = re.sub(r"【※?\s*\d+\s*g】", "", name)
    name = re.sub(r"\s*\d+\s*g\s*$", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()


def build_record(item: dict, paragraphs: list[str]) -> dict:
    display = clean_name(item["name"])
    parsed = parse_product(display)
    if item["category"] == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(display)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, display)

    farm_bits, desc_lines, flavor = [], [], None
    processing = parsed["processing_method"]
    for ln in merge_label_lines(paragraphs):
        if ln.startswith(("※", "あらかじめ")):
            continue
        pairs = FARM_PATTERN.findall(ln)
        if pairs:
            for label, val in pairs:
                val = val.strip(" /")
                farm_bits.append(f"{label}:{val}")
                if label in ("精製方法", "精製") or label.lower().startswith("proces"):
                    if not processing:
                        processing = detect_processing_method(val)
            continue
        if ln.startswith("焙煎度合い"):
            continue
        desc_lines.append(ln)
    text = " ".join(paragraphs)
    roast_level = parsed["roast_level"]
    rm = ROAST_PATTERN.search(display) or ROAST_PATTERN.search(text)
    if rm:
        roast_level = rm.group(1)
    hint = None
    sm = re.search(r"焙煎度合い[:：]\s*浅\s*(.*?)\s*深", text)
    if sm:
        cur = re.search(r"[❶-❿①-⑩]", sm.group(1))
        if cur:
            hint = f"焙煎度合い {cur.group(0)} (0=浅〜10=深)"
    desc = " ".join(desc_lines)[:400] or None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": hint,
        "flavor_notes": desc,
        "farm_note": " / ".join(farm_bits) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": "完売" if item["out_of_stock"] else "販売中",
        "out_of_stock": item["out_of_stock"],
        "product_url": f"{BASE_URL}/view/item/{item['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in parse_list():
        try:
            paragraphs = fetch_detail(item["id"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            paragraphs = []
        records.append(build_record(item, paragraphs))
        time.sleep(1)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamepolepole.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamepolepole.json に出力しました")


if __name__ == "__main__":
    main()
