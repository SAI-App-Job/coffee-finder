# -*- coding: utf-8 -*-
"""
scrape_adachicoffeeokawa.py

あだち珈琲(www.adachicoffee.com、福岡県大川市榎津325-28のスペシャルティコーヒー専門店・自家焙煎)の
商品情報を取得する。おちゃのこネット(Ocnk)。千葉県の「アダチコーヒー」(adachicoffee.jp、
scrape_adachi.py)とは別の店舗なので、スクリプト名・出力ファイル名を分けている。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧 /product-list/1(全商品(コーヒー豆))・4(COE入賞豆)・
5(シングルオリジン)・10(ブレンド)・23(カフェインレス)の商品を重複を除いて集める(約86件)。
同一銘柄が「50g/100g/200g/400g/500g」の重量違いの別商品(別 /product/N)として並ぶため、
銘柄ごとに最小重量の商品を代表にする(COE入賞豆・ゲイシャは50g)。
次は対象外: お試し/グルメセット、ネコポスセット、ギフトBOX付き、水出しコーヒー、ギフトボックス、
コーヒーバッグ、リキッド、器具、雑貨。

【価格・重量・在庫】
重量は商品名の「100g」等から取得(ページ内の選択肢は挽き方のみ)。価格は商品ページのJS設定
pConf.price(税込)。在庫は商品ページに「カートに入れる」ボタンがあるかで判定する。
産地(商品名)・地域/生産処理/焙煎度(「商品詳細」欄の「生産処理 :」「焙煎:」)を取得する。
ブレンドは商品名の「ブレンド」で判定する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "あだち珈琲",
    "url": "https://www.adachicoffee.com/",
    "platform": "Ocnk",
    "address": "福岡県大川市榎津325-28",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認(GPTBot等のAI系クローラのみ全面Disallow)",
}

BASE_URL = "https://www.adachicoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
LIST_IDS = [1, 4, 5, 10, 23]
MAX_PAGES = 6
EXCLUDE_KEYWORDS = (
    "セット", "ネコポス", "ギフト", "水出し", "コーヒーバッグ", "ドリップバッグ", "リキッド", "ベース", "生豆",
)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
COARSE_ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
NAME_TRAIL_PATTERN = re.compile(r"\s*\d+\s*(?:kg|g)\s*$", re.I)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_ids() -> list[str]:
    ids: list[str] = []
    for lid in LIST_IDS:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/product-list/{lid}" + ("" if page == 1 else f"?page={page}")
            soup = BeautifulSoup(fetch_html(url), "html.parser")
            new = []
            for a in soup.select("a[href*='/product/']"):
                m = re.search(r"/product/(\d+)$", a["href"])
                if m and m.group(1) not in ids:
                    ids.append(m.group(1))
                    new.append(m.group(1))
            if not new:
                break
    return ids


def parse_item(pid: str) -> dict | None:
    url = f"{BASE_URL}/product/{pid}"
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:title")
    raw = og["content"] if og and og.get("content") else (soup.title.get_text() if soup.title else "")
    raw = re.split(r"\s+-\s+スペシャルティコーヒー", raw)[0]
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip()
    if not title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None

    wm = WEIGHT_PATTERN.search(title)
    if not wm:
        return None
    weight = int(wm.group(1)) * (1000 if wm.group(2).lower() == "kg" else 1)

    pm = re.search(r"pConf\.price\s*=\s*(\d+)", html)
    if not pm:
        return None
    price = int(pm.group(1))

    for s in soup(["script", "style"]):
        s.decompose()
    lines = [l.strip() for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]
    out_of_stock = "カートに入れる" not in lines

    detail = ""
    if "商品詳細" in lines:
        i = lines.index("商品詳細")
        rest = []
        for l in lines[i + 1:]:
            if l.startswith("※バースデー") or l.startswith("ログイン"):
                break
            rest.append(l)
        detail = "\n".join(rest)
    fields = {}
    for l in detail.split("\n"):
        fm = re.match(r"(地域|生産者|標高|品種|生産処理|精製方法|焙煎)\s*[:：]\s*(.+)", l)
        if fm:
            fields[fm.group(1)] = fm.group(2).strip()
    md = soup.find("meta", attrs={"name": "description"})
    flavor_notes = None
    # 商品詳細欄の先頭(商品名の次の風味説明の行群)をテイスティングノートとする
    dl = detail.split("\n")
    note_lines = []
    for l in dl[1:]:
        if re.match(r"(地域|生産者|標高|品種|生産処理|精製方法|焙煎)\s*[:：]", l):
            break
        note_lines.append(l)
    if note_lines:
        flavor_notes = re.sub(r"\s+", " ", " ".join(note_lines))[:400] or None

    parsed = parse_product(title)
    if "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
    if not parsed["processing_method"] and fields.get("生産処理"):
        parsed["processing_method"] = extract_from_description("精製方法：" + fields["生産処理"])["processing_method"]

    rm = COARSE_ROAST_PATTERN.search(fields.get("焙煎", "")) or COARSE_ROAST_PATTERN.search(title)
    roast_level = rm.group(1) if rm else parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_level,
        "flavor_notes": flavor_notes,
        "farm_note": fields.get("生産者") or fields.get("地域"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    items = []
    for pid in collect_ids():
        rec = parse_item(pid)
        if rec:
            items.append(rec)
    best: dict[str, dict] = {}
    for rec in items:
        key = NAME_TRAIL_PATTERN.sub("", rec["raw_name"]).strip()
        if key not in best or rec["weight_g"] < best[key]["weight_g"]:
            best[key] = rec
    return list(best.values())


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_adachicoffeeokawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_adachicoffeeokawa.json に出力しました")


if __name__ == "__main__":
    main()
