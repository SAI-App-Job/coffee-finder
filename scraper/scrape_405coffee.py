# -*- coding: utf-8 -*-
"""
scrape_405coffee.py

405 COFFEE ROASTERS(405coffee.shop-pro.jp、カラーミーショップ)の商品情報を
取得する。神奈川県横浜市西区(西前市場・藤棚商店街周辺)の単独店舗。

scrape_philocoffea.pyをテンプレートに実装しているが、同じshop-pro.jpでも
このテーマはRhizomagと同一系統(prd_lst_*クラス)で、PHILOCOFFEA/TSUKIKOYAとは
異なる(実データ確認済み、2026-08時点)。

【文字コード】EUC-JP(実データ確認済み)。

【一覧ページ】一覧の時点で商品名がクリーンな1行テキスト(例:「※NEW
ルワンダフムレ　【100g/200g】 中煎り」)で、Rhizomagのような<br>詰め込みは
無い。span.prd_lst_expに簡潔な説明文もあり、そのままflavor_notesの
フォールバックとして使える。

【焙煎度について】TSUKIKOYAと異なり、焙煎度(浅煎り/中煎り/中深煎り/中浅煎り/
深煎り)は商品名に固定で埋め込まれており、注文時に選べる変動要素ではない
(実データ確認済み: variantsのoption1_valueは「豆のまま/ドリップ用粉」という
挽き方のみ)。ROAST_LEVELSの8段階とは粒度が異なるためroast_levelには入れず
roast_hintとして保持し、roast_selectable=Falseとする。

【価格・重量の扱い】variantsのoption2_valueが「100g 1100円」のように重量と
価格を1つの文字列に含む特殊な形式(実データ確認済み)。価格自体は
variant.option_price_including_taxに構造化されて別途あるためそちらを使い、
option2_valueからは正規表現で重量のみを取り出す(全角「ｇ」表記の商品も
実データで確認済みのため半角/全角両方にマッチさせる)。豆のまま×最小重量を
代表バリアントとして選ぶ(珈琲丸等と同じ考え方)。

【商品説明の構造】
div.product_exp内に「生産地(TAB)ルワンダ　東部州　ガツィボ郡」のように、
ラベルと値をタブ文字で区切った自由記述がある(コロンではなくタブである点に
注意。PHILOCOFFEA系のコロン区切りとも、TSUKIKOYAの全角/半角コロン混在とも
違う独自形式)。精選方法欄はnormalize_processing_methodで正規化する。

【非コーヒー豆の除外】実データ確認済み: ドリップバッグ(11g/12g×10個セットの
詰め合わせ)のみがコーヒー豆と異なる形態の商品として存在する。他は全て
ストレート/ブレンドの通常商品(器具・グッズ等の混在は確認できず)。
キーワード除外に加え、他店舗と同じ構造的チェック(産地国も産地情報も
ブレンド判定も無ければ除外)も保険として適用する。

【在庫について】var Colorme のinventory_controlが"none"で、stock_numは
常にnull(実データ確認済み。Rhizomagと同じ運用)。構造化された在庫フラグが
機能していないため、商品名のテキストのみで在庫状態を判定する。

robots.txt確認済み(2026年8月時点): PHILOCOFFEA等と同一の記述(User-agent: *
は/secure/と/cart/のみ制限)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "405 COFFEE ROASTERS",
    "url": "https://405coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県横浜市西区中央2-24-6 西前市場1階",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA等と同一の記述)",
}

CRAWL_DELAY_SECONDS = 1  # robots.txt確認済み(2026-08時点): Crawl-delay指定なし。個人開発の反復スピード
# 優先だが、小規模個人店が多いためcourtesy設定(間隔を空けること自体)は維持する
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://405coffee.shop-pro.jp/"
LIST_BASE_URL = "https://405coffee.shop-pro.jp/?mode=srh&keyword=&sort=n"

# 実データ確認済み(2026-08時点): ドリップバッグ(詰め合わせパック)のみがコーヒー豆と
# 異なる形態の商品として存在する
NON_BEAN_KEYWORDS = ["ドリップバッグ"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
# 単一重量のみの商品はvariantのoption2_valueが空文字列で、重量は商品名にしか
# 出てこない(実データ確認済み: 「タンザニア スノートップ 200g 中深煎り」)ため、
# バリアントからの抽出に失敗した場合は商品名からも試す。
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
DESC_LABEL_PATTERN = re.compile(r"(生産地|標高|収穫時期|品種|精選方法|乾燥方法|土壌)\t([^\n]+)")
ROAST_HINT_KEYWORDS = ["中深煎り", "中浅煎り", "深煎り", "浅煎り", "中煎り"]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def weight_from_variant(variant: dict | None, fallback_text: str = "") -> int | None:
    if variant:
        m = WEIGHT_PATTERN.search(variant.get("option2_value") or "")
        if m:
            return int(m.group(1))
    # 単一重量のみの商品はoption2_valueが空文字列なので、商品名から拾う
    m = WEIGHT_PATTERN.search(fallback_text or "")
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """挽き方×重量の組み合わせバリアントから代表の1件を選ぶ。挽かない「豆のまま」を
    優先し、その中で最小重量のものを採用する(珈琲丸のpick_canonical_variant()と
    同じ考え方)。"""
    if not variants:
        return None

    def weight_key(v):
        w = weight_from_variant(v)
        return w if w is not None else float("inf")

    whole_bean = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")]
    pool = whole_bean or variants
    return min(pool, key=weight_key)


def detect_roast_hint(text: str) -> str | None:
    for kw in ROAST_HINT_KEYWORDS:
        if kw in text:
            return kw
    return None


def parse_description(description_html: str) -> dict:
    soup = BeautifulSoup(description_html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text()

    labels = {label: value.strip() for label, value in DESC_LABEL_PATTERN.findall(text) if value.strip()}
    # ラベル行より前にある冒頭の紹介文をflavor_notesの候補として拾う(タブ区切りの
    # ラベル行が始まる前までのテキスト)
    intro = text.split("生産地\t")[0].strip() if "生産地\t" in text else None

    return {"labels": labels, "intro": intro or None}


def build_record(product_url: str, colorme_product: dict, description_html: str, list_exp: str | None) -> dict:
    # var Colorme のproduct.nameは末尾に\r\nが付いていることがある(実データ確認済み:
    # 「405 バリューブレンドA」500g/300g)ため、明示的にstripする
    title = (colorme_product.get("name") or "").strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        variant = pick_canonical_variant(colorme_product.get("variants", []))
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": variant.get("option_price_including_tax") if variant else None,
            "product_url": product_url,
        }

    desc = parse_description(description_html)
    labels = desc["labels"]

    if labels.get("生産地"):
        country = detect_country_name(labels["生産地"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    if labels.get("精選方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])

    if (
        not labels
        and not parsed.get("origin_country")
        and parsed.get("category") != "ブレンド"
    ):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    farm_note_parts = []
    if labels.get("生産地"):
        farm_note_parts.append(f"生産地: {labels['生産地']}")
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    if labels.get("収穫時期"):
        farm_note_parts.append(f"収穫時期: {labels['収穫時期']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    variant = pick_canonical_variant(colorme_product.get("variants", []))
    stock_num = colorme_product.get("stock_num")
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 5段階の簡易表記でROAST_LEVELSの8段階と粒度が異なるため未設定
        "roast_hint": detect_roast_hint(title),
        "roast_selectable": False,  # 挽き方は選べるが焙煎度自体は商品名に固定(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": desc["intro"] or list_exp,
        "blend_components": [],  # ブレンド商品の産地別内訳は実データで見つからず未対応
        "price": variant.get("option_price_including_tax") if variant else None,
        "weight_g": weight_from_variant(variant, title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, list_exp: str | None = None) -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }

    body_el = soup.select_one("div.product_exp")
    description_html = body_el.decode_contents() if body_el else ""

    return build_record(url, colorme_product, description_html, list_exp)


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.prd_lst_unit")

    results = []
    for item in items:
        name_link_el = item.select_one("span.prd_lst_name a")
        exp_el = item.select_one("span.prd_lst_exp")
        price_el = item.select_one("span.prd_lst_price")
        if not name_link_el:
            continue

        raw_name = name_link_el.get_text(strip=True)
        if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
            continue

        href = name_link_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        if price_el:
            price_match = re.search(r"([\d,]+)円", price_el.get_text())
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        stock_status = detect_stock_status(raw_name)

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "stock_status": stock_status,
            "exp": exp_el.get_text(strip=True) if exp_el else None,
        })
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_list_items = []
    page = 1
    while True:
        items = scrape_product_list_page(page)
        if not items:
            break
        all_list_items.extend(items)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(
            prev,
            raw_name=item["raw_name"],
            price=item.get("price"),
            stock_status=item["stock_status"],
        ):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"], item.get("exp"))
            detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_405coffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_405coffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
