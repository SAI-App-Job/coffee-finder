# -*- coding: utf-8 -*-
"""
scrape_coffeesoldier.py

珈琲ソルジャー(Coffee Soldier、coffeesoldier.shop-pro.jp、カラーミーショップ。鹿児島市東千石町17-9 松清ビル1-B の天文館本店と
姶良市宮島町32-8 の姶良ロースタリーの2店舗)の商品情報を取得する。公式サイト https://coffeesoldier.com/home/ 。

【文字コード】EUC-JP(実データ確認済み)。robots.txt は User-agent: * で /cart/ のみDisallow。間隔は2秒。

【対象商品】カテゴリ「コーヒー豆」(cbid=2178457)の一覧から、エコバック・アルミ袋(小分け用)を除いた豆10銘柄
(単一産地6[ペルー COE入賞・ブラジル・インドネシア アチェ・グアテマラ・エチオピア・ケニア]、ブレンド4[秋霞・ハウス・モカジャバ・ソルジャー])。
ギフト・ドリップバッグ・水出し・器具・セットは別カテゴリのため対象外。
variantsは「豆のまま/粗挽き/中粗挽き…」×「重量」で、豆のまま×最小重量(250g。ペルーのみ150g)を代表にする。
焙煎度は説明文に明記されているもの(「中浅焙り」「深焙り」)のみ採用し、他は null。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "珈琲ソルジャー",
    "url": "https://coffeesoldier.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "鹿児島県鹿児島市東千石町17-9 松清ビル1-B",
    "prefecture": "鹿児島県",
    "robots_txt_status": "許可(2026-11確認。User-agent: * は /cart/ のみDisallow)",
    "source_note": "公式 https://coffeesoldier.com/home/ ・SHOP INFO /shop-info/ ・販売 https://coffeesoldier.shop-pro.jp/ のカテゴリ「コーヒー豆」を2026-11-02に確認。季節限定の秋霞ブレンドを掲載中。",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://coffeesoldier.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=cate&cbid=2178457&csid=0"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
INTERVAL = 2.0
EXCLUDE_WORDS = ("エコバ", "アルミ袋", "ギフト", "ドリップ", "セット", "水出し")
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)")
BLEND_NAMES = ("ブレンド", "モカジャバ")
LABEL_PATTERN = re.compile(r"【(生産プロセス|生産処理方法|精製方法)】\s*([^\s【]+)")


def get(url: str) -> BeautifulSoup:
    time.sleep(INTERVAL)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def collect_items() -> list[tuple[str, str]]:
    soup, _ = get(LIST_URL)
    out = []
    for a in soup.select('a[href*="pid="]'):
        name = a.get_text(" ", strip=True)
        if not name or any(w in name for w in EXCLUDE_WORDS):
            continue
        url = BASE_URL + a["href"].lstrip("/") if a["href"].startswith("?") else a["href"]
        if all(url != u for _, u in out):
            out.append((name, url))
    return out


def weight_of(v: dict) -> int | None:
    m = WEIGHT_PATTERN.search(v.get("option2_value") or "")
    if not m:
        return None
    return int(m.group(1)) * (1000 if m.group(2) == "kg" else 1)


def pick_variant(variants: list[dict]) -> dict | None:
    whole = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")]
    pool = whole or variants
    pool = [v for v in pool if weight_of(v)]
    return min(pool, key=weight_of) if pool else None


def roast_from_text(text: str) -> str | None:
    for pat, val in (("中浅焙り", "中浅煎り"), ("中浅煎り", "中浅煎り"), ("中深焙り", "中深煎り"), ("中深煎り", "中深煎り"),
                     ("深焙り", "深煎り"), ("深煎り", "深煎り"), ("浅焙り", "浅煎り"), ("浅煎り", "浅煎り"),
                     ("中焙り", "中煎り"), ("中煎り", "中煎り")):
        if pat in text:
            return val
    return None


def build_record(list_name: str, url: str) -> dict | None:
    soup, raw = get(url)
    m = COLORME_JSON_PATTERN.search(raw)
    if not m:
        return None
    prod = json.loads(m.group(1)).get("product") or {}
    var = pick_variant(prod.get("variants", []))
    if not var:
        return None
    name = re.sub(r"\s+", " ", (prod.get("name") or list_name).replace("　", " ")).strip()
    exp = soup.select_one(".product_exp")
    exp_text = exp.get_text(" ", strip=True) if exp else ""
    for br in soup.find_all("br"):
        br.replace_with("\n")
    page_text = soup.get_text("\n", strip=True)
    sold_out = ("SOLD OUT" in page_text.upper() and "カートに入れる" not in page_text) or "売り切れ" in page_text[:3000]
    is_blend = any(k in name for k in BLEND_NAMES)
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            parsed["origin_country"] = detect_country_name(name)
            parsed["origin_source"] = "raw_name" if parsed["origin_country"] else None
    processing = parsed["processing_method"]
    lm = LABEL_PATTERN.search(exp_text)
    if lm:
        processing = normalize_processing_method(lm.group(2))
    elif not processing and "スマトラ式" in exp_text and not is_blend:
        processing = normalize_processing_method("スマトラ式")
    fm = re.search(r"【風味の印象と特徴】\s*(.+?)(?:【|★|●|$)", exp_text)
    flavor = re.sub(r"\s+", " ", fm.group(1)).strip()[:200] if fm else None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_from_text(exp_text),
        "roast_hint": None,
        "flavor_notes": flavor,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": var.get("option_price_including_tax"),
        "weight_g": weight_of(var),
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for name, url in collect_items():
        try:
            rec = build_record(name, url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {url} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_coffeesoldier.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeesoldier.json に出力しました")


if __name__ == "__main__":
    main()
