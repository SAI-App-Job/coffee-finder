# -*- coding: utf-8 -*-
"""
scrape_belltimecoffee.py

北鎌倉ベルタイム珈琲(belltime-coffee.com、神奈川県鎌倉市山ノ内748。「低温焙煎蜂の巣珈琲」と
称する自家焙煎(ミクロロースト)のコーヒー豆専門店。通販はショップサーブ系の独自カート)の
商品情報を取得する。カテゴリ一覧(ストレート・ブレンド・エコ・エコブレンド)から商品ページ
(/SHOP/{番号}.html)を集め、各商品ページの「豆のまま」行のグラム数別価格表(100g/200g/500g)と
在庫表示・説明文を取得する。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。トップに「10月1日より送料を改定」の告知があり現行。

【対象商品について】
実データ確認済み(2026-10時点): ストレート8・ブレンド8・エコ(有機)5・エコブレンド9の
計30銘柄。ギフトセット(ニコニコセット)・500g卸/50杯用(同一豆の大容量)・ワンカップ珈琲・
魔法ロシ・どこでも珈琲(ティーバッグ式)は豆ではないため除外する。
代表重量は表示されている最小サイズ(100g)、価格はその「豆のまま」の税込価格。
エコ・グァテマラ・コロンビア等「エコ」は有機・環境配慮認証豆のシリーズ。
「モカ・シダモ」「モカフレンチ」は商品説明の産地表記(エチオピア・シダモ)による。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "北鎌倉ベルタイム珈琲",
    "url": "https://www.belltime-coffee.com/",
    "platform": "ショップサーブ(独自カート)",
    "address": "神奈川県鎌倉市山ノ内748",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.belltime-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 0.3

# (カテゴリページ, ブレンドカテゴリか)
CATEGORY_PAGES = [
    ("/SHOP/421701/list.html", False),  # ストレート豆
    ("/SHOP/402111/list.html", True),   # ブレンドコーヒー
    ("/SHOP/401888/list.html", False),  # エココーヒー豆(有機)
    ("/SHOP/426218/list.html", True),   # エコブレンド
]
EXCLUDE_KEYWORDS = ("ワンカップ", "魔法ロシ", "ティーバッグ", "ニコニコセット", "ギフト", "卸/50杯", "500g卸", "セット")
SIZE_PRICE = re.compile(r"(\d+)\s*[gｇ]\s*\n?\s*([\d,]+)\s*円")
ORIGIN_OVERRIDES = {
    "モカ ・ シダモ": "エチオピア",  # 説明文「エチオピアのシダモ地方」
    "モカフレンチ": "エチオピア",    # 説明文「モカシダモを…フレンチロースト」
}


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
    seen: dict[str, dict] = {}
    for path, is_blend_cat in CATEGORY_PAGES:
        soup = BeautifulSoup(get_html(BASE_URL + path), "html.parser")
        for a in soup.select("h2.goods a"):
            title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            if not title or any(k in title for k in EXCLUDE_KEYWORDS):
                continue
            href = a["href"]
            url = href if href.startswith("http") else BASE_URL + href
            item = seen.setdefault(url, {"url": url, "title": title, "blend": False})
            item["blend"] = item["blend"] or is_blend_cat
        time.sleep(REQUEST_INTERVAL)
    return list(seen.values())


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]

    # 説明文: 商品名行(2回目の出現)の直後から「拡大表示」まで
    desc_lines: list[str] = []
    if "拡大表示" in lines:
        end = lines.index("拡大表示")
        # 見出しの商品名行の次から説明が始まる。直前のパンくず(「>」「エココーヒー豆」等)は除くため、
        # 「>」行以降の2行目から取る
        k = end - 1
        while k >= 0 and lines[k] != ">":
            k -= 1
        desc_lines = lines[k + 2:end] if k >= 0 else []
    desc = re.sub(r"\s+", " ", " ".join(ln for ln in desc_lines if ln != "*")).strip() or None

    # 価格表: 「豆の挽き方 / グラム数 / 価格」表の「豆のまま」行以降
    sizes: dict[int, int] = {}
    if "価格" in lines:
        # 表本体は「在庫」「豆の挽き方」「グラム数」「価格」の見出し行の後ろに並ぶ
        try:
            hdr = max(i for i, ln in enumerate(lines) if ln == "価格")
        except ValueError:
            hdr = 0
        body = "\n".join(lines[hdr + 1:])
        m = re.search(r"豆のまま\n(.*?)(?:\nご利用案内|\Z)", body, re.S)
        if m:
            for w, p in SIZE_PRICE.findall(m.group(1)):
                sizes.setdefault(int(w), int(p.replace(",", "")))

    stock_text = ""
    for i, ln in enumerate(lines):
        if ln == "在庫" and i + 1 < len(lines):
            stock_text = lines[i + 1]
            break
    return {"desc": desc, "sizes": sizes, "stock_text": stock_text}


def build_record(item: dict) -> dict | None:
    detail = parse_detail(get_html(item["url"]))
    if not detail["sizes"]:
        return None
    weight_g = min(detail["sizes"])
    price = detail["sizes"][weight_g]
    name = item["title"]
    # 説明文の先頭は商品名の繰り返し(+「*」)なので除く。「一杯の基準量10gは￥n」はコスト目安のため除く
    desc = detail["desc"]
    if desc:
        desc = desc[len(name):] if desc.startswith(name) else desc
        desc = re.sub(r"[（(]?一杯の基準量\d*[gｇ]は[\\¥￥]\d+[）)]?", "", desc).replace("*", " ")
        desc = re.sub(r"\s+", " ", desc).strip() or None
    detail["desc"] = desc
    out_of_stock = not detail["stock_text"].startswith("在庫あり") if detail["stock_text"] else False

    parsed = parse_product(name)
    is_blend = item["blend"] or "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        override = ORIGIN_OVERRIDES.get(name)
        detected = override or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"] and detail["desc"]:
            c = detect_country_name(detail["desc"])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)

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
        "roast_hint": None,
        "flavor_notes": detail["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
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
    with open("data_belltimecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_belltimecoffee.json に出力しました")


if __name__ == "__main__":
    main()
