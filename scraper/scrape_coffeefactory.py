# -*- coding: utf-8 -*-
"""
scrape_coffeefactory.py

COFFEE FACTORY(coffeefactory.jp、茨城県つくば市千現2-13-1、約30年営業の
自家焙煎スペシャルティコーヒー専門店。守谷市の姉妹店COFFEE&CACAO FACTORYと
合わせて2店舗のみでチェーンには該当しない)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。

【店舗発見の経緯】
全国再調査(茨城県)でmamenavi.info「茨城の自家焙煎珈琲店ガイド」から発見。

【対象商品について】
実データ確認済み(2026-09時点): 「コーヒー豆」カテゴリ(cbid=1684052)全20件
(ブレンド6・ストレート14)を対象とする。「コーヒー豆大量注文のお客様
[割引価格]」カテゴリ(cbid=2820114)は同一銘柄の1kg/2kg割引版で重複の
ため対象外。

【一覧ページの構造について】
実データ確認済み: 他店とも異なる新テーマ(`li.productlist-unit`)を使用し、
画像用と商品名用の2つの`<a href="?pid=...">`が並ぶため、2番目のリンクの
テキストを商品名として取得する必要がある。

【商品説明の構造について】
実データ確認済み: `div#itemExUniqueBox`内に「＜HIGH ROAST＞」等の焙煎度
表記、「カップの特徴」の見出しに続くテイスティングノート、そして
`<table><tr><th>生産地</th><td>...</td></tr>...`という構造化テーブル
(生産地・生産者・標　高・品　種・プロセス、ラベルの2文字間に全角スペースが
入る場合がある)が続く。「＜配送方法について＞」以降は梱包・送料の定型文
のため除外する。

【価格・重量について】
実データ確認済み: 全銘柄が「豆のまま（おすすめ）」×「おまかせ(+0円)」の
組み合わせを基準価格として持ち、100g単位を選ぶと+40円の追加送料が
かかる仕組みのため、基準価格(おまかせ)をそのまま採用し、weight_gは
100gとして記録する(店側の説明文に「コーヒー豆 … 100g」という表記が
複数箇所にあり100g基準であることを確認済み)。

【在庫状態について】
実データ確認済み: stock_numが常にnull、かつHTML内に構造化された完売表示も
見当たらないため、商品名のテキストのみで判定する(detect_stock_status)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method, detect_stock_status

SHOP_INFO = {
    "name": "COFFEE FACTORY",
    "url": "https://coffeefactory.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "茨城県つくば市千現2-13-1",
    "prefecture": "茨城県",
    "tel": "029-851-2039",
    "robots_txt_status": "許可(2026-09確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://coffeefactory.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
CATEGORY_ID = "1684052"

LABEL_MAP = {"生産地": "生産地", "生産者": "生産者", "標高": "標高", "品種": "品種", "プロセス": "精選方法"}
ROAST_HINT_PATTERN = re.compile(r"＜([^＞]+)＞")


def fetch_euc(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return resp.text


def collect_product_ids() -> list[str]:
    ids = []
    for page in (1, 2, 3):
        url = f"{BASE_URL}?mode=cate&cbid={CATEGORY_ID}&csid=0" + (f"&page={page}" if page > 1 else "")
        html = fetch_euc(url)
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("li.productlist-unit")
        if not items:
            break
        for li in items:
            links = li.select("a[href*=pid]")
            if len(links) < 2:
                continue
            m = re.search(r"pid=(\d+)", links[0]["href"])
            if m:
                ids.append(m.group(1))
    return ids


def build_record(pid: str) -> dict | None:
    html = fetch_euc(f"{BASE_URL}?pid={pid}")
    m = re.search(r"var\s+Colorme\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return None
    colorme = json.loads(m.group(1))
    product = colorme.get("product") or {}
    title = (product.get("name") or "").strip()
    if not title:
        return None

    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one("div#itemExUniqueBox")
    labels = {}
    flavor_notes = None
    roast_hint = None
    if box:
        table = box.find("table")
        if table:
            for tr in table.select("tr"):
                cells = tr.find_all(["th", "td"])
                if len(cells) == 2:
                    raw_label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    key = LABEL_MAP.get(re.sub(r"\s", "", raw_label))
                    if key and value:
                        labels[key] = value
            table.decompose()
        text = box.get_text("\n", strip=True)
        text = text.split("＜配送方法について＞")[0]
        rm = ROAST_HINT_PATTERN.search(text)
        roast_hint = rm.group(1) if rm else None
        cup_idx = text.find("カップの特徴")
        if cup_idx != -1:
            flavor_notes = text[cup_idx + len("カップの特徴"):].strip() or None
        else:
            flavor_notes = re.sub(r"＜[^＞]*＞", "", text).strip() or None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax")
    stock_status = detect_stock_status(title)
    sold_out = stock_status != "販売中"

    url = f"{BASE_URL}?pid={pid}"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    region = labels.get("生産地")
    if parsed["category"] != "ブレンド":
        detected = (region and detect_country_name(region)) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description" if region else "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精選方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])

    farm_parts = [f"{k}: {labels[k]}" for k in ("生産地", "生産者", "標高", "品種") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in collect_product_ids():
        try:
            detail = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_coffeefactory.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeefactory.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
