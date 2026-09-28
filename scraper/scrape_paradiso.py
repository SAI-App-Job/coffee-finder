# -*- coding: utf-8 -*-
"""
scrape_paradiso.py

PARADISO COFFEE(パラディーゾ コーヒー、paradiso.shop-pro.jp、山形県鶴岡市
本町一丁目6-11、SCAJコーヒーマイスターの店主が営むスペシャルティコーヒー
専門店)の商品情報を取得する。カラーミーショップ(shop-pro.jp)。

【店舗発見の経緯】
全国再調査(山形県)でcoffee-labo.co.jp記事から発見。

【対象商品について】
実データ確認済み(2026-09時点): 「コーヒー豆」カテゴリ(cbid=2141135)全9件を
対象とする。「ブレンド」カテゴリ(cbid=2066234)は現在該当商品0件。
「コーヒー豆のセット」「水出しコーヒーパック」「ドリップバッグ」
「コーヒーギフト」「コーヒー器具、道具」「KeepCup」は対象外。
カテゴリ一覧ページの商品はli.productlist_listで囲まれている(サイドバーの
「おすすめ商品」にも同じpid形式のリンクがあるため、この専用クラスで
本文の商品一覧のみに絞り込む必要がある)。

【重量・価格について】
実データ確認済み: var Colorme JSON内のvariantsが100g/200g/300g/400g/500gの
5段階で、挽き方(豆/粉)は変動要素として構造化されていない(サイト側の説明文
には「豆 or 粉」選択に触れる商品もあるが、価格に影響する構造化データでは
ない)。最小の100gバリアントのoption_price_including_taxを代表価格として
採用する。

【商品説明の構造について】
実データ確認済み: div.product_explain内に「【Tasting Note】」「【Story】」の
自由記述ブロックと、末尾に<TABLE summery="Beans Data">で生産地・生産者・
標高・品種・精製方法をラベル付きで構造化した表がある。表をBeautifulSoupで
個別に抽出したうえで本文から除去し、残りの自由記述をflavor_notesとして使う。

【在庫状態について】
実データ確認済み: このショップはinventory_control="product"で商品レベルの
stock_num(在庫数)が機能しており、stock_num<=0を構造的な完売判定として使う
(バリアント単位のstock_numは常にnullで共有在庫のため、商品レベルの値を見る)。

robots.txt確認済み(2026-09): shop-pro.jp標準の記述で、User-agent: *は
/secure/と/cart/のみDisallow。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "パラディーゾ コーヒーロースターズ",
    "url": "https://paradiso.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "山形県鶴岡市本町一丁目6-11",
    "prefecture": "山形県",
    "robots_txt_status": "許可(2026-09確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://paradiso.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
BEAN_CATEGORY_URL = "https://paradiso.shop-pro.jp/?mode=cate&cbid=2141135&csid=0"

LABEL_MAP = {"生産地": "生産地", "生産者": "生産者", "標高": "標高", "品種": "品種", "精製方法": "精選方法"}


def fetch_euc(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return resp.text


def collect_product_ids() -> list[str]:
    html = fetch_euc(BEAN_CATEGORY_URL)
    soup = BeautifulSoup(html, "html.parser")
    ids = []
    for li in soup.select("li.productlist_list"):
        a = li.select_one("a[href*=pid]")
        if a:
            m = re.search(r"pid=(\d+)", a["href"])
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
    explain = soup.select_one("div.product_explain")
    labels = {}
    flavor_notes = None
    if explain:
        table = explain.find("table")
        if table:
            for tr in table.select("tr"):
                tds = tr.select("td")
                if len(tds) == 2:
                    label = tds[0].get_text(strip=True)
                    value = tds[1].get_text(strip=True)
                    key = LABEL_MAP.get(label)
                    if key and value:
                        labels[key] = value
            table.decompose()
        for br in explain.find_all("br"):
            br.replace_with("\n")
        text = explain.get_text()
        text = re.sub(r"※豆のままでの販売となります。?", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        flavor_notes = text or None

    parsed = parse_product(title)
    variants = product.get("variants") or []
    price = variants[0].get("option_price_including_tax") if variants else product.get("sales_price_including_tax")
    stock_num = product.get("stock_num")
    sold_out = isinstance(stock_num, int) and stock_num <= 0
    stock_status = "完売" if sold_out else "販売中"

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
    with open("data_paradiso.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_paradiso.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
