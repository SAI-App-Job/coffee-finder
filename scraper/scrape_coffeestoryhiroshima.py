# -*- coding: utf-8 -*-
"""
scrape_coffeestoryhiroshima.py

Coffee Story(珈琲物語 〜コーヒーストーリー〜)(https://coffee-story.jp/、広島県広島市中区立町1-12 イナリビル2階)の
商品情報を取得する。カラーミーショップ(coffee-story.shop-pro.jp)の独自ドメイン版。

岐阜県の「珈琲物語」(coffeestory.base.shop、scrape_coffeestory.py)とは別の店舗(slugを分けている)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-26): 「コーヒー豆」カテゴリ(cbid=2964235)の全29商品。ギフト(6商品)・
ドリップバッグ/コーヒーバッグ(6商品)カテゴリは対象外。
各商品は「量」バリアント(100g/200g/300g/400g/500g)で、表示価格は100gの価格(ページに明記)。
最小重量の100gを代表とし、100gバリアントの在庫(var Colorme の variants[].stock_num)が0なら
ページ表示の「売り切れ」に合わせて「一時的に品切れ」とする。
ゲイシャ(パナマ エスメラルダ)・ハワイコナ・ジャマイカBM・ワイルドコピルアック等の高額豆も
通常の焙煎豆なので採用(コピルアックはジャコウネコ由来の豆を洗浄・焙煎した通常のコーヒー豆)。
アイス用の深煎り豆(トラジャアイス・アイス珈琲 香り・ケニアでアイス)もコーヒー豆なので採用。
焙煎度は商品説明冒頭の「おすすめのロースト」表記(例: ☆ハイロースト(４))から取得する。
記載のない商品(ブレンド3種・ブレンド珈琲物語・夕べの珈琲)はnull。

【オンライン注文休止について】
2026/10/25〜28は焙煎機設置のためオンラインストアでの注文を休止中(トップのお知らせ)。
商品ページは閲覧可能で、価格・在庫は商品ページの表示どおりに反映している。

【文字コード】EUC-JP。

【robots.txtについて】
User-agent: * は /secure/ と /cart/ のみ禁止(2026-10-26確認)。商品ページ(?pid=)は許可。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
)

SHOP_INFO = {
    "name": "Coffee Story(珈琲物語)",
    "url": "https://coffee-story.jp/",
    "platform": "カラーミーショップ(coffee-story.shop-pro.jp、独自ドメイン coffee-story.jp)",
    "address": "広島県広島市中区立町1-12 イナリビル2階",
    "prefecture": "広島県",
    "robots_txt_status": "許可(2026-10-26確認。User-agent: * は /secure/ と /cart/ のみ禁止)",
    "source_note": "公式ショップ(https://coffee-story.jp/)の「コーヒー豆」カテゴリ全29商品の商品ページを2026-10-26に確認。"
                   "表示価格は100gの価格。2026/10/25〜28は焙煎機設置のためオンライン注文を休止中(商品ページは閲覧可)。"
                   "住所は特定商取引法に基づく表記(?mode=sk)と食べログで確認",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://coffee-story.jp/"
CATEGORY_URL = "https://coffee-story.jp/?mode=cate&cbid=2964235&csid=0&sort=p"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティー?|フレンチ|イタリアン)ロースト")
ROAST_NUM_PATTERN = re.compile(r"ロースト\s*([1-8１-８])")
ROAST_BY_NUM = {1: "ライトロースト", 2: "シナモンロースト", 3: "ミディアムロースト", 4: "ハイロースト",
                5: "シティロースト", 6: "フルシティロースト", 7: "フレンチロースト", 8: "イタリアンロースト"}

# pid -> 上書き。ブレンドは産地を持たない。商品名に国名が無い商品の産地は説明文の記述から補う。
BLEND_PIDS = {"188733951", "188733963", "188733970", "188733976", "189795191"}
DECAF_PIDS = {"191722996"}
ORIGIN_OVERRIDES = {
    "188910146": "アメリカ(ハワイ)",
    "189822799": "インドネシア",   # 説明「インドネシア・スマトラ島のガヨハイランドで採取したコピルアック」
}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_product_ids() -> list[str]:
    html_text = fetch(CATEGORY_URL)
    ids = []
    for pid in re.findall(r"\?pid=(\d+)", html_text):
        if pid not in ids:
            ids.append(pid)
    return ids


def extract_product(html_text: str) -> dict | None:
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("product")
    except json.JSONDecodeError:
        return None


def weight_of(variant: dict) -> int | None:
    m = WEIGHT_PATTERN.search(variant.get("option1_value") or variant.get("title") or "")
    return int(m.group(1)) if m else None


def description_text(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    txt = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))
    a = txt.find("商品説明")
    if a < 0:
        return ""
    b = txt.find("レビュー", a)
    return txt[a + len("商品説明"):b if b > 0 else None].strip()


def detect_roast(desc: str) -> str | None:
    head = desc[:80]
    m = ROAST_PATTERN.search(head)
    if m:
        kind = m.group(1).replace("シティー", "シティ")
        return kind + "ロースト"
    m = ROAST_NUM_PATTERN.search(head)
    if m:
        n = int(m.group(1).translate(str.maketrans("１２３４５６７８", "12345678")))
        return ROAST_BY_NUM.get(n)
    return None


def clean_notes(desc: str) -> str | None:
    text = desc.split("重量（ｇ）")[0]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 先頭の「おすすめのロースト」行・「会員価格あり」等の定型文は除く
    lines = [ln for ln in lines if "おすすめのロースト" not in ln and "おすすめロースト" not in ln
             and "会員価格あり" not in ln and not re.fullmatch(r"[\d,]+円/100g", ln)]
    out = re.sub(r"\s+", " ", " ".join(lines)).strip()
    return out[:400] or None


def build_record(pid: str, product: dict, html_text: str) -> dict | None:
    name = re.sub(r"[\s　]+", " ", (product.get("name") or "").strip())
    variants = product.get("variants") or []
    variants = [v for v in variants if weight_of(v)]
    if not variants:
        return None
    variant = min(variants, key=weight_of)

    desc = description_text(html_text)
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None

    if pid in BLEND_PIDS:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if pid in DECAF_PIDS:
            parsed["category"] = "デカフェ"
        detected = ORIGIN_OVERRIDES.get(pid) or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        if pid in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
            parsed["origin_source"] = "raw_name" if pid == "188910146" else "product_description"
        if pid not in DECAF_PIDS:
            parsed = apply_category_hint_fallback(parsed, name)

    stock_num = variant.get("stock_num")
    sold_out = isinstance(stock_num, int) and stock_num <= 0
    status = "一時的に品切れ" if sold_out else "販売中"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": detect_roast(desc),
        "roast_hint": None,
        "flavor_notes": clean_notes(desc),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": variant.get("option_price_including_tax"),
        "weight_g": weight_of(variant),
        "stock_status": status,
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    ids = list_product_ids()
    print(f"[info] コーヒー豆カテゴリ: {len(ids)}商品")
    records = []
    for pid in ids:
        time.sleep(CRAWL_DELAY_SECONDS)
        try:
            html_text = fetch(f"{BASE_URL}?pid={pid}")
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        product = extract_product(html_text)
        if not product:
            print(f"[warn] 商品JSONなし: pid={pid}")
            continue
        rec = build_record(pid, product, html_text)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeestoryhiroshima.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeestoryhiroshima.json に出力しました")


if __name__ == "__main__":
    main()
