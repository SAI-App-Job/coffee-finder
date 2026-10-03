# -*- coding: utf-8 -*-
"""
scrape_tajimayacoffee.py

但馬屋珈琲店(shop.tajimaya-coffeeten.com、昭和20年創業の新宿の老舗。本店:東京都新宿区
西新宿1-2-6。吉祥寺・池袋東武・京橋(mini)の各店と立川の「東京立飛焙煎所」(有機JAS認証)で
自家焙煎、計5拠点+姉妹店1)の商品情報を取得する。カラーミーショップ(charset=euc-jp、
`resp.encoding = "euc-jp"`を明示)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆」(グループgid=2998171、全24商品・1ページ)
のうち、「通販限定！初回限定・珈琲豆お試しセット」(複数銘柄のセット)を除く23件
(ブレンド・ストレート・デカフェ。最近の新商品(2026年登録)を含む)を収録する。
コーヒーギフト・ドリップバッグ&水出しコーヒー・コーヒーカップ&器具は別グループのため対象外。
「アイスコーヒー」「アメリカン(ライトロースト)」「特撰オリジナルブレンド」は配合の記載が
無い焙煎豆のブレンド扱い(産地None)。

【重量・価格・在庫】
詳細ページの「グラム」選択肢(「100g(±0)」「200g(+￥1050)」)から最小サイズ=100gと、
表示価格(100gの価格。税込)を採用する。在庫は一覧の「SOLD OUT」表示
(p.itemList__soldOut)で判定する。産地は商品詳細の「【生産国】」から取得し、
焙煎度は「【当店基準焙煎度】」をroast_hintとして保持する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "但馬屋珈琲店",
    "url": "https://shop.tajimaya-coffeeten.com/",
    "platform": "カラーミーショップ",
    "address": "東京都新宿区西新宿1-2-6",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://shop.tajimaya-coffeeten.com"
LIST_URL = f"{BASE_URL}/?mode=grp&gid=2998171"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("お試しセット", "セット", "ギフト", "ドリップバッグ", "水出し")
BLEND_NAMES = ("アイスコーヒー", "アメリカン", "特撰オリジナルブレンド")
MAX_PAGES = 5


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        soup = BeautifulSoup(fetch(url), "html.parser")
        new = 0
        for li in soup.select("li.itemList__unit"):
            a = li.select_one("p.itemList__name a")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a["href"])
            if not m or m.group(1) in items:
                continue
            new += 1
            price_el = li.select_one("p.itemList__price")
            pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
            items[m.group(1)] = {
                "pid": m.group(1),
                "name": re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip(),
                "price": int(pm.group(1).replace(",", "")) if pm else None,
                "sold_out": li.select_one("p.itemList__soldOut") is not None,
            }
        if new == 0:
            break
    return list(items.values())


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    # サイズ選択肢: 「100g(±0)」「200g(＋￥1050)」
    options = []
    for ln in lines:
        norm = unicodedata.normalize("NFKC", ln).replace("￥", "¥")
        m = re.match(r"^(\d+)\s*g\s*[（(]\s*(±\s*¥?\s*0|\+\s*¥?\s*[\d,]+)\s*[）)]$", norm)
        if m:
            delta = 0 if m.group(2).startswith("±") else int(re.sub(r"[^\d]", "", m.group(2)))
            options.append((int(m.group(1)), delta))
    desc_lines: list[str] = []
    fields: dict[str, str] = {}
    if "Detail" in lines:
        start = lines.index("Detail") + 1
        end = next((i for i in range(start, len(lines)) if lines[i] in ("Detail", "RECOMMEND")), len(lines))
        sect = lines[start:end]
        i = 0
        while i < len(sect):
            m = re.match(r"^【(.+?)】\s*(.*)$", sect[i])
            if m:
                val = m.group(2)
                if not val and i + 1 < len(sect) and not sect[i + 1].startswith("【"):
                    val = sect[i + 1]
                    i += 1
                fields[m.group(1)] = val
            elif not fields:
                desc_lines.append(sect[i])
            i += 1
    return {"options": options, "fields": fields, "desc": " ".join(desc_lines)}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", name)
    parsed = parse_product(norm)
    is_blend = "ブレンド" in norm or any(norm.startswith(b) for b in BLEND_NAMES)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, norm)
        origin_text = detail["fields"].get("生産国", "")
        if origin_text:
            c = detect_country_name(origin_text)
            if c:
                if parsed["origin_country"] != c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "country_name"
            elif not parsed["origin_country"]:
                parsed["origin_country"] = re.sub(r"(連邦民主共和国|連合共和国|民主共和国|共和国)$", "", origin_text).strip() or None
                parsed["origin_source"] = "country_name"
    if parsed["origin_country"] == "マラウィ":
        parsed["origin_country"] = "マラウイ"
    # サイズ: 最小サイズ。価格は「±0」の基準価格に差額を足す
    weight_g = None
    price = item["price"]
    if detail["options"] and price is not None:
        w, delta = min(detail["options"], key=lambda x: x[0])
        weight_g = w
        price = item["price"] + delta
    desc = detail["desc"]
    out = item["sold_out"]
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
        "roast_hint": detail["fields"].get("当店基準焙煎度") or None,
        "flavor_notes": desc[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            detail = parse_detail(fetch(f"{BASE_URL}/?pid={item['pid']}"))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        rec = build_record(item, detail)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tajimayacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tajimayacoffee.json に出力しました")


if __name__ == "__main__":
    main()
