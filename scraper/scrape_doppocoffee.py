# -*- coding: utf-8 -*-
"""
scrape_doppocoffee.py

DOPPO どっぽ 自家焙煎珈琲豆(doppo-coffee.com、東京都武蔵野市中町1-10-7 武蔵野Kビル1階、
三鷹駅北口徒歩3分。生豆をご注文ごとに焙煎する自家焙煎店、単独1店舗)の商品情報を
取得する。Jimdo Shop。

【ページ構造について】
実データ確認済み(2026-10時点): 「ブレンド」「ストレート」「アイス用」の3カテゴリページに
商品ごとの見出し(h3)・焙煎度【中深煎り】・説明・産地/標高/精選/品種・価格表
(生豆時100g/200g/500g)・「ご購入はこちら」リンク(個別商品ページ)が並ぶ。
完売品はリンクが無く「完売」と表示される。他店舗と同様に最小の100gの価格を代表とする
(重量は「生豆時」のグラム数で、焙煎後は減少する)。
価格表の数字はJimdoの編集で<span>分割されているため、セル内テキストを連結して取得する。
イタリアンロースト【マサイブレンド】はブレンドページ上の100g価格が「￥8420」と明らかな
誤記(200gが1,520円)のため、100g価格が200g価格以上になる場合は個別商品ページの価格を採用する。
同じ商品がブレンド・アイス用の両ページに載る場合は個別URLで重複排除する。
個別URLが無い(完売)商品の product_url はカテゴリページURL + '#' + 商品名とする。
"""

import json
import re
import unicodedata
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "DOPPO どっぽ",
    "url": "https://www.doppo-coffee.com/",
    "platform": "Jimdo Shop",
    "address": "東京都武蔵野市中町1-10-7 武蔵野Kビル1階",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.doppo-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

CATEGORY_PAGES = ["/ブレンド-1/", "/ストレート/", "/アイス用/"]
HEADER_SPLIT = re.compile(r'(?=<div id="cc-m-\d+" class="j-module n j-header)')
SPEC_PATTERN = re.compile(r"^(産地|標高|精選|品種)\s*[：:]\s*(.*)$")
ROAST_PATTERN = re.compile(r"【([^】]*煎り)】")
SPEC_SPLIT = re.compile(r"(産地|標高|精選|品種)\s*[：:]\s*")
LINE_PATTERN = re.compile(r"[\r\n]+")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return resp.text


def parse_prices(seg: BeautifulSoup) -> dict[int, int]:
    prices = {}
    for tr in seg.select("table tr"):
        cells = [re.sub(r"\s+", "", unicodedata.normalize("NFKC", td.get_text(""))) for td in tr.find_all("td")]
        if len(cells) >= 2:
            wm = re.fullmatch(r"(\d+)g", cells[0])
            pm = re.fullmatch(r"[¥￥]([\d,]+)", cells[1])
            if wm and pm:
                prices[int(wm.group(1))] = int(pm.group(1).replace(",", ""))
    return prices


def detail_price_100g(url: str) -> int | None:
    text = unicodedata.normalize("NFKC", BeautifulSoup(fetch(url), "html.parser").get_text(" ", strip=True))
    m = re.search(r"生豆時100g\)(.*?)カートに入れる", text)
    if not m:
        return None
    nums = re.findall(r"[¥￥]\s*([\d,]+)", m.group(1))
    return int(nums[-1].replace(",", "")) if nums else None


def parse_category(path: str) -> list[dict]:
    page_url = BASE_URL + quote(path)
    html_text = fetch(page_url)
    items = []
    for part in HEADER_SPLIT.split(html_text)[1:]:
        seg = BeautifulSoup(part, "html.parser")
        h3 = seg.find("h3")
        prices = parse_prices(seg)
        if not h3 or 100 not in prices:
            continue
        name = norm(h3.get_text(" ", strip=True))
        seg_text = seg.get_text("\n", strip=True)
        roast_m = ROAST_PATTERN.search(seg_text)
        link = seg.select_one('a[data-title="ご購入はこちら"]')
        paras = []
        for p in seg.find_all("p"):
            for br in p.find_all("br"):
                br.replace_with("\n")
            for line in LINE_PATTERN.split(p.get_text("")):
                t = norm(line)
                if t and t not in paras:
                    paras.append(t)
        specs, desc_parts = {}, []
        for t in paras:
            t = ROAST_PATTERN.sub("", t).replace("ニュークロップ", "").strip()
            if not t or t.startswith(("お店からの", "生豆時")):
                continue
            # 「産地:… 標高:… 精選:…」が同一行に並ぶ場合も項目ごとに分解する
            pieces = SPEC_SPLIT.split(t)
            if pieces[0].strip():
                desc_parts.append(pieces[0].strip())
            for key, val in zip(pieces[1::2], pieces[2::2]):
                specs.setdefault(key, val.strip())
        items.append({
            "name": name,
            "roast": norm(roast_m.group(1)) if roast_m else None,
            "prices": prices,
            "sold_out": link is None and "完売" in seg_text,
            "url": urljoin(BASE_URL, link["href"]) if link else None,
            "page_url": page_url,
            "desc": " ".join(desc_parts)[:500] or None,
            "specs": specs,
        })
    return items


def build_record(item: dict) -> dict:
    name = item["name"]
    prices = item["prices"]
    price = prices[100]
    if 200 in prices and price >= prices[200] and item["url"]:
        price = detail_price_100g(item["url"]) or price  # 価格表の誤記対策

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name)

    specs = item["specs"]
    processing = parsed["processing_method"]
    if not processing and specs.get("精選"):
        processing = normalize_processing_method(specs["精選"])
    farm_bits = [f"{k}: {specs[k]}" for k in ("産地", "標高", "品種") if specs.get(k)]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": item["roast"] or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": item["desc"],
        "farm_note": " / ".join(farm_bits) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if item["sold_out"] else "販売中",
        "out_of_stock": item["sold_out"],
        "product_url": item["url"] or (item["page_url"] + "#" + quote(name)),
    }


def scrape_all_products() -> list[dict]:
    records = []
    seen = set()
    for path in CATEGORY_PAGES:
        try:
            items = parse_category(path)
        except requests.RequestException as e:
            print(f"[warn] カテゴリページ取得失敗: {path} ({e})")
            continue
        for item in items:
            rec = build_record(item)
            if rec["product_url"] in seen:
                continue
            seen.add(rec["product_url"])
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_doppocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_doppocoffee.json に出力しました")


if __name__ == "__main__":
    main()
