# -*- coding: utf-8 -*-
"""
scrape_redpoison.py

REDPOISON(red-poison.com、神奈川県座間市さがみ野2-2-20の「REDPOISON Roastery」。
独自設計の焙煎機SOLIDで自家焙煎するスペシャルティコーヒー専門店。実店舗は座間市さがみ野と
横浜市西区浅間町の2店、通販は座間市の本店から発送)の商品情報を取得する。
WordPress+Welcart。商品一覧(/category/item/、約11ページ)から商品ID(/item/{ID}/)を
集め、各商品ページの「Name/Country/Area/Variety/Process/Grade」欄と、サイズ別
(100g袋・200g袋・400g…)の在庫状況・税込価格を取得する。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。所在地は特定商取引表記の「座間市さがみ野2-2-20」を採用した。

【対象商品について】
商品一覧には2021年以降の限定ロット・グッズ(Tシャツ・傘・ノベルティ・福袋・ドリップバッグ・
器具)が計約250件残っており、大半は売り切れの過去ロットである。現行の品揃えを示すため、
「コーヒー豆(100g/200g袋等のグラム表記のあるサイズ)で在庫有りまたは入荷待ちのサイズが
1つでもある商品」のみを対象とする(全サイズ売り切れの過去ロット、グッズ、ドリップバッグ、
器具、セット、福袋は除外)。実データ確認済み(2026-10時点): 15銘柄。
代表重量は在庫のある最小サイズ(通常100g袋。競技会ロット等の希少ゲイシャは16g×2=32g、
50g、一部は200gのみ)。価格はそのサイズの税込販売価格(2つ並ぶ価格の後者=割引後価格)。
全サイズ入荷待ちの商品は完売扱い。DRIP BAG行は豆ではないため無視する。
ブレンドは「Country」欄がなく商品名にも国名がないもの(ミルクビバレッジベース含む)をブレンドとする。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    detect_processing_method, normalize_processing_method,
)

SHOP_INFO = {
    "name": "REDPOISON",
    "url": "https://red-poison.com/",
    "platform": "WordPress(Welcart)",
    "address": "神奈川県座間市さがみ野2-2-20",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://red-poison.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 0.2
LIST_PAGE_LIMIT = 15

SIZE_NOISE = {"豆 or 粉", "選択してください", "豆のまま", "粉に挽く"}
IN_STOCK_STATUS = "在庫有り"
WAITING_STATUS = "入荷待ち"
FIELD_NAMES = ("Name", "Country", "Area", "Plantation", "Altitude", "Variety", "Process", "Grade")
ROAST_TITLE_PATTERN = re.compile(r"(ライト|ミドル|ミディアム|ダーク)ロースト")
ROAST_DESC_PATTERN = re.compile(r"(Light|Middle|Medium|Dark)\s*Roast\s*([^\s]*)", re.I)
ROAST_EN_JA = {"light": "ライトロースト", "middle": "ミドルロースト", "medium": "ミディアムロースト", "dark": "ダークロースト"}
ROAST_TITLE_JA = {"ライト": "ライトロースト", "ミドル": "ミドルロースト", "ミディアム": "ミディアムロースト", "ダーク": "ダークロースト"}


def get_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return resp.text


def list_item_ids() -> list[str]:
    ids: list[str] = []
    for page in range(1, LIST_PAGE_LIMIT + 1):
        url = f"{BASE_URL}/category/item/" + (f"page/{page}/" if page > 1 else "")
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code != 200:
            break
        found = re.findall(r'href="https://red-poison\.com/item/(\d+)/"', resp.text)
        new = [i for i in dict.fromkeys(found) if i not in ids]
        if not new:
            break
        ids.extend(new)
        time.sleep(REQUEST_INTERVAL)
    return ids


def weight_from_label(label: str) -> int | None:
    """「100g 袋」「BEANS 200g 袋」「400g ( 200g 袋×2 )」「( 16g 袋 × 2 ) 32g」から総重量(g)を返す。"""
    tail = re.search(r"\)\s*(\d+)\s*g\s*$", label)
    if tail:
        return int(tail.group(1))
    head = re.search(r"(\d+)\s*g", label)
    return int(head.group(1)) if head else None


def parse_sizes(lines: list[str]) -> list[dict]:
    sizes = []
    for k, ln in enumerate(lines):
        m = re.match(r"在庫状況\s*:\s*(\S+)", ln)
        if not m:
            continue
        # サイズ表記は在庫状況行の直前(「豆 or 粉」等の選択肢行を除く)
        j = k - 1
        while j >= 0 and (lines[j] in SIZE_NOISE or lines[j].startswith("豆のままのみ")):
            j -= 1
        label = lines[j] if j >= 0 else ""
        prices = []
        for nxt in lines[k + 1:k + 4]:
            pm = re.fullmatch(r"¥([\d,]+)", nxt)
            if pm:
                prices.append(int(pm.group(1).replace(",", "")))
        if not prices or "DRIP" in label.upper() or "ドリップ" in label:
            continue
        weight = weight_from_label(label)
        if weight is None:
            continue
        sizes.append({"label": label, "weight": weight, "stock": m.group(1), "price": prices[-1]})
    return sizes


def parse_fields(lines: list[str]) -> dict[str, str]:
    fields = {}
    for k, ln in enumerate(lines):
        m = re.fullmatch(r"(\w+)\s*:", ln)
        if m and m.group(1) in FIELD_NAMES and k + 1 < len(lines):
            fields[m.group(1)] = lines[k + 1]
    return fields


def build_record(item_id: str) -> dict | None:
    url = f"{BASE_URL}/item/{item_id}/"
    soup = BeautifulSoup(get_html(url), "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    if "商品詳細説明" not in lines:
        return None
    k = lines.index("商品詳細説明")
    # 商品名(日本語)の直後に英語名の行が続く構成。英語名が無い商品は直前行が商品名
    prev = lines[k - 1]
    ascii_ratio = sum(ch.isascii() for ch in prev) / max(len(prev), 1)
    name = lines[k - 2] if ascii_ratio > 0.9 else prev
    name = re.sub(r"\s+", " ", name.replace("　", " ")).strip()

    sizes = parse_sizes(lines)
    available = [s for s in sizes if s["stock"] in (IN_STOCK_STATUS, WAITING_STATUS)]
    if not available:
        return None  # 全サイズ売り切れの過去ロット・グッズ・ドリップバッグ等は対象外
    in_stock = [s for s in available if s["stock"] == IN_STOCK_STATUS]
    rep = min(in_stock or available, key=lambda s: s["weight"])
    out_of_stock = rep["stock"] != IN_STOCK_STATUS

    fields = parse_fields(lines)
    # 説明文: 商品詳細説明〜「Name :」または最初のサイズ見出し/ドリップバッグ注記の前まで
    desc_end = next((i for i in range(k + 1, len(lines))
                     if lines[i].startswith(("Name", "DRIP BAG もシステム")) or re.match(r"在庫状況", lines[i])), len(lines))
    desc_lines = [ln for ln in lines[k + 1:desc_end] if not re.fullmatch(r"\d+g.*袋.*|豆のままのみ.*", ln)]
    desc = re.sub(r"\s+", " ", " ".join(desc_lines)).strip()[:600] or None

    parsed = parse_product(name)
    country_field = fields.get("Country")
    is_blend = "ブレンド" in name or (not country_field and not detect_country_name(name))
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name) or (detect_country_name(country_field) if country_field else None)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name" if detect_country_name(name) else "description"
        parsed = apply_category_hint_fallback(parsed, name)

    process = fields.get("Process")
    processing = parsed["processing_method"] or (detect_processing_method(process) if process else None)
    if not processing and "ウエットハル" in name:  # 「ウェット」の表記ゆれ(辞書は「ウェットハル」)
        processing = "ウェットハルド"
    # Grade欄の「Top Specialty」等は店独自のランク表記でありG1・AA等の等級ではないため、商品名から取れる等級のみ採用する
    grade = parsed["grade"]

    roast_level = roast_hint = None
    rm = ROAST_TITLE_PATTERN.search(name)
    if rm:
        roast_level = ROAST_TITLE_JA[rm.group(1)]
    else:
        dm = ROAST_DESC_PATTERN.search(" ".join(desc_lines))
        if dm:
            roast_level = ROAST_EN_JA[dm.group(1).lower()]
            roast_hint = dm.group(2) or None

    farm_parts = [fields.get(key) for key in ("Plantation", "Area", "Altitude", "Variety")]
    farm_note = " / ".join(p for p in farm_parts if p) or None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": grade,
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": rep["price"],
        "weight_g": rep["weight"],
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in list_item_ids():
        try:
            record = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {item_id} ({e})")
            continue
        time.sleep(REQUEST_INTERVAL)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_redpoison.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_redpoison.json に出力しました")


if __name__ == "__main__":
    main()
