# -*- coding: utf-8 -*-
"""
scrape_tamaplazabeans.py

横浜たまプラーザビーンズ(tamaplaza-beans.com、神奈川県横浜市青葉区美しが丘4-19-19、
1987年創業。ご注文後に焙煎する自家焙煎コーヒー豆専門店。店舗は1店)の商品情報を取得する。
ショップサーブ系の独自カート。カテゴリ一覧(ストレート/ブレンド/限定品/オーガニック/
カフェインレス/アイスコーヒー)から商品ページ(/SHOP/{コード}.html)を集め、各商品ページの
「原産国」「精選方法」欄・説明文・在庫表示を取得する。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。お知らせに2026年7月の価格改定、9月の臨時休業告知があり現行。

【対象商品について】
実データ確認済み(2026-10時点): ストレート26・ブレンド7・限定品4・オーガニック2・
カフェインレス2・アイスコーヒー2(重複あり)の延べ商品から重複を除いたコーヒー豆
(ドリップパック・ギフト・グッズ・その他商品は除外)。
全商品が「生豆200g」単位の価格表記(ご注文後に焙煎、焙煎度・挽き方は注文時に選択)で、
代表重量は200g(焙煎後は目減りする)。価格は税込の販売価格(10月限定SALE等の割引中はその価格)。
焙煎度は注文時選択式のため roast_level はNone。名称先頭の「（限定販売）」と末尾の
「生豆200g」は名称から除く。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "横浜たまプラーザビーンズ",
    "url": "https://tamaplaza-beans.com/",
    "platform": "ショップサーブ(独自カート)",
    "address": "神奈川県横浜市青葉区美しが丘4-19-19",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://tamaplaza-beans.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 0.3

# (カテゴリページ, ブレンド扱いか)
CATEGORY_PAGES = [
    ("/SHOP/5856/5857/list.html", False),   # ストレート
    ("/SHOP/5856/5858/list.html", True),    # ブレンド
    ("/SHOP/5856/250350/list.html", False), # 限定品
    ("/SHOP/5856/5859/list.html", False),   # オーガニック
    ("/SHOP/5856/54733/list.html", False),  # カフェインレス
    ("/SHOP/5856/55754/list.html", False),  # アイスコーヒー
]
WEIGHT_SUFFIX = re.compile(r"\s*生豆\s*(\d+)\s*[gｇ]\s*$")
TAX_IN_PRICE = re.compile(r"税込\s*[¥￥]\s*([\d,]+)")
SOLDOUT_PATTERN = re.compile(r"在庫なし|在庫切れ|売り切れ|SOLD\s*OUT|品切れ|入荷待ち", re.I)


def get_html(url: str) -> str:
    last_err = None
    for _ in range(3):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as e:
            last_err = e
            time.sleep(2)
    raise last_err


def list_items() -> list[dict]:
    """カテゴリページから商品(URL・一覧上の名称・税込価格・ブレンドカテゴリか)を重複なく集める。"""
    seen: dict[str, dict] = {}
    for path, is_blend_cat in CATEGORY_PAGES:
        soup = BeautifulSoup(get_html(BASE_URL + path), "html.parser")
        for sec in soup.select("section.column4"):
            a = sec.select_one("h2 a")
            if not a:
                continue
            href = a["href"]
            url = href if href.startswith("http") else BASE_URL + href
            text = sec.get_text(" ", strip=True)
            taxes = TAX_IN_PRICE.findall(text)
            if taxes:
                price = int(taxes[-1].replace(",", ""))
            else:
                fixed = sec.select_one(".fixed_price, .selling_price")
                price = int(re.sub(r"\D", "", fixed.get_text())) if fixed else None
            item = seen.setdefault(url, {"url": url, "title": a.get_text(strip=True), "price": price, "blend": False})
            item["blend"] = item["blend"] or is_blend_cat
        time.sleep(REQUEST_INTERVAL)
    return list(seen.values())


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]

    stock_text = ""
    for i, ln in enumerate(lines):
        if ln.startswith("在庫") and i + 1 < len(lines) and ln.replace(":", "").replace("：", "") == "在庫":
            stock_text = lines[i + 1]
            break

    fields: dict[str, str] = {}
    desc_lines: list[str] = []
    start = next((i for i, ln in enumerate(lines) if ln.startswith("不良品の返品")), None)
    if start is not None:
        i = start + 1
        # レビュー表示(「レビューはありません」または「4.7」「(3件)」)を飛ばす
        while i < len(lines) and (lines[i] == "レビューはありません" or re.fullmatch(r"[\d.]+|\(\d+件\)", lines[i])):
            i += 1
        while i < len(lines) and lines[i] != "お気に入り":
            ln = lines[i]
            if ln in ("原産国", "精選方法", "品種") and i + 1 < len(lines):
                fields[ln] = lines[i + 1]
                i += 2
                continue
            if ln == "POINT":
                break
            desc_lines.append(ln)
            i += 1
    return {
        "stock_text": stock_text,
        "fields": fields,
        "desc": re.sub(r"\s+", " ", " ".join(desc_lines)).strip()[:500] or None,
    }


def build_record(item: dict) -> dict | None:
    detail = parse_detail(get_html(item["url"]))
    title = item["title"]
    wm = WEIGHT_SUFFIX.search(title)
    weight_g = int(wm.group(1)) if wm else None
    name = WEIGHT_SUFFIX.sub("", title)
    name = re.sub(r"^[（(]限定販売[）)]\s*", "", name).strip()
    name = re.sub(r"\s+", " ", name.replace("　", " "))
    if item["price"] is None:
        return None

    out_of_stock = bool(SOLDOUT_PATTERN.search(detail["stock_text"]))
    fields = detail["fields"]

    parsed = parse_product(name)
    is_blend = item["blend"] or "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"] and fields.get("原産国"):
            # 「タイ」はパーサーが部分文字列の誤爆を避けて辞書化していないため、原産国欄が完全一致の場合のみ採用する
            c = detect_country_name(fields["原産国"]) or ("タイ" if fields["原産国"].strip() == "タイ" else None)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)
    processing = parsed["processing_method"] or (normalize_processing_method(fields["精選方法"]) if fields.get("精選方法") else None)
    variety = fields.get("品種")

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": None,  # 焙煎度はご注文時に選択する方式
        "roast_hint": None,
        "flavor_notes": detail["desc"],
        "farm_note": f"品種: {variety}" if variety else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": item["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {item['url']} ({e})")
            continue
        time.sleep(REQUEST_INTERVAL)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tamaplazabeans.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tamaplazabeans.json に出力しました")


if __name__ == "__main__":
    main()
