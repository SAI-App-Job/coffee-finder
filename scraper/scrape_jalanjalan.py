# -*- coding: utf-8 -*-
"""
scrape_jalanjalan.py

じゃらんじゃらん(JalanJalan Coffee&More、shop.jalanjalan.jp、山形県山形市
七日町2丁目7-10 ナナビーンズ1F、2002年開業のフェアトレード自家焙煎珈琲豆・
オーガニック食品セレクトショップ)の商品情報を取得する。カラーミーショップ
(shop-pro.jp、独自ドメイン)。

【店舗発見の経緯】
全国再調査(山形県)でmamenavi.info「山形の自家焙煎珈琲店ガイド」から発見。

【対象商品について】
実データ確認済み(2026-09時点): 「珈琲豆☆プレミアム豆」(カテゴリID1019656)
「珈琲豆☆グルメ豆＆スペシャルティ豆」(カテゴリID1018972)の2カテゴリに
コーヒー豆商品が分かれて掲載されている(両カテゴリに重複掲載される商品も
あり)。「じゃらんオリジナル 珈琲ビスコッティ」(pid=168202363)はコーヒー豆
ではなく焼き菓子のため除外。ドリップバッグ・グロサリー(食品雑貨)は別
カテゴリのため対象外。

【価格・重量について】
実データ確認済み: 「購入数単位について:100g単位です」との明記があり、
挽き方バリアント(豆のまま/中挽き/中細挽き/細挽き/荒挽き)は全て同価格。
var Colorme JSON内のsales_price_including_taxをそのまま100gあたりの
価格として採用する。

【商品説明の構造について】
div.expl_block内の自由記述。「国・地域：」「品種：」「規格（グレード）：」
「焙煎度：」の構造化ラベル行を持つ商品と、「□使用豆:」という1行だけの
簡易記述(ブレンドの配合豆内訳、または単一銘柄の品種メモ)のみの商品が
混在する(実データ確認済み、店の運用が銘柄により異なるため)。両方を
farm_noteの構成要素として拾う。

【在庫状態について】
実データ確認済み: 商品詳細ページの購入ボタン付近に売り切れ時のみ
`<div style="...">SOLD OUT</div>`が表示される。カテゴリ一覧ページにも
同じ表示があるが、詳細ページ単体で判定できるためそちらのみを使う。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html; charset=EUC-JP)。

robots.txt確認済み(2026-09): shop-pro.jp標準の記述で、User-agent: *は
/secure/と/cart/のみDisallow。本スクレイパーが使う商品ページ・カテゴリ
ページは制限対象外。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "じゃらんじゃらん",
    "url": "https://jalanjalan.jp/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "山形県山形市七日町2丁目7-10 ナナビーンズ1F",
    "prefecture": "山形県",
    "tel": "023-622-6883",
    "robots_txt_status": "許可(2026-09確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://shop.jalanjalan.jp/"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
CATEGORY_URLS = [
    "https://shop.jalanjalan.jp/?mode=cate&cbid=1019656&csid=0",  # プレミアム豆
    "https://shop.jalanjalan.jp/?mode=cate&cbid=1018972&csid=0",  # グルメ豆＆スペシャルティ豆
]
NON_BEAN_PIDS = {"168202363"}  # じゃらんオリジナル 珈琲ビスコッティ(焼き菓子)

LABEL_PATTERN = re.compile(r"(国・地域|品種|規格（グレード）|焙煎度|使用豆)[:：]\s*(.+)")


def fetch_euc(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return resp.text


def collect_product_ids() -> list[str]:
    ids = []
    seen = set()
    for cat_url in CATEGORY_URLS:
        html = fetch_euc(cat_url)
        for pid in re.findall(r"\?pid=(\d+)", html):
            if pid not in seen and pid not in NON_BEAN_PIDS:
                seen.add(pid)
                ids.append(pid)
    return ids


def build_record(pid: str) -> dict | None:
    html = fetch_euc(f"{BASE_URL}?pid={pid}")
    m = re.search(r"var\s+Colorme\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return None
    colorme = json.loads(m.group(1))
    product = colorme.get("product") or {}
    title = re.sub(r"^■", "", (product.get("name") or "").strip()).strip()
    if not title:
        return None

    soup = BeautifulSoup(html, "html.parser")
    expl = soup.select_one("div.expl_block")
    flavor_notes = None
    labels = {}
    if expl:
        for br in expl.find_all("br"):
            br.replace_with("\n")
        text = expl.get_text()
        text = text.split("購入数単位について")[0].strip()
        intro_lines = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 実データ確認済み: 最初のラベル行のみ先頭に"□"が付くことがある
            # (例:「□国・地域：インドネシア...」)ため、行頭一致ではなく検索で拾う
            lm = LABEL_PATTERN.search(line)
            if lm:
                labels[lm.group(1)] = lm.group(2).strip()
            else:
                intro_lines.append(line)
        # 冒頭の商品名の単純な繰り返し行(タイトルと完全一致)は除外する
        intro_lines = [l for l in intro_lines if l != title]
        flavor_notes = "\n".join(intro_lines) or None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax")
    sold_out = bool(re.search(r">SOLD OUT<", html))
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

    region = labels.get("国・地域")
    detected = (region and detect_country_name(region)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if region else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    farm_parts = [f"{k}: {labels[k]}" for k in ("国・地域", "品種", "規格（グレード）", "使用豆") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None
    roast_hint = labels.get("焙煎度")

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
        time.sleep(1)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_jalanjalan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_jalanjalan.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
