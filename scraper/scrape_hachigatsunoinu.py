# -*- coding: utf-8 -*-
"""
scrape_hachigatsunoinu.py

八月の犬コーヒー(八月の犬、hatiinu.ocnk.net、京都府京丹後市大宮町河辺3319)の商品情報を取得する。おちゃのこネット(Ocnk)。

【販売先について】
同店は楽天市場(www.rakuten.co.jp/hatiinu/「自家焙煎珈琲豆挽き売り 八月の犬」)にも出店している(評価3,896件)が、
今回は公式の自社ショップ(hatiinu.ocnk.net)を採用した。自社ショップは重量別カテゴリ(200g/500g/1000g/デカフェ)ごとの
通常価格が一覧でき、価格の確認がしやすい。楽天は送料込みセット・月替わり・福袋等が混在し、100g〜2000gのサイズ展開がある別ラインナップ。

【対象商品について】
実データ確認済み(2026-10-21): 「コーヒー200g」(product-list/72)14商品、「コーヒー500g」(product-list/73)・
「デカフェ」(product-list/69)のうち200g版がない8銘柄(500g版)の計22銘柄を収録(ブレンド13・シングル9)。
同一銘柄の500g・1000g版は、最小重量の商品(200g、200g版がなければ500g)を代表とした。
ギフト・飲み比べセット・福袋・1000gのみの大容量・コーヒー器具・砂糖・フィルター類は除外。
価格は商品ページの税込表示(販売価格は税抜表示で、括弧内に税込を併記)を採用。豆のまま/粗挽き〜極細挽きの選択式(豆のままを採用)。
商品説明が短いため、焙煎度は説明に明記のあるものだけを設定した。
自家焙煎の根拠: ふるさと納税ページ・楽天のショップ名「自家焙煎珈琲豆挽き売り」、紹介記事(おとなのえんそく 2020-12-14、店頭販売・注文後焙煎)。
実店舗: 京都府京丹後市大宮町河辺3319(特定商取引法表示ページ /info の販売主所在地)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "八月の犬コーヒー",
    "url": "https://hatiinu.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "京都府京丹後市大宮町河辺3319",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10-21確認。robots.txtはGPTBot等の特定AIクローラのみDisallow、それ以外は制限なし。識別可能なUser-Agentを使用)",
    "source_note": "自社ショップ(https://hatiinu.ocnk.net/)のカテゴリ(product-list/72・73・69)と各商品ページ、特商法表示(/info)を2026-10-21に確認。楽天市場にも出店(https://www.rakuten.co.jp/hatiinu/)。日付表記のある更新情報なし。自家焙煎の根拠はショップ内には薄く、ふるさと納税ページ・楽天のショップ名・紹介記事による",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://hatiinu.ocnk.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2

# (商品ID, 商品名, 重量(g), ブレンドか, 焙煎度(説明に明記がある場合のみ), 焙煎度の補足)
ITEMS = [
    ("165", "ハウスブレンド スマトラブレンド", 200, True, "深煎り", "深煎りタイプ"),
    ("163", "ペルー チャンチャマイヨ", 200, False, None, None),
    ("160", "ホンジュラス コパン", 200, False, None, None),
    ("150", "ハウスブレンド ホンジュラスブレンド", 200, True, None, None),
    ("146", "ハウスブレンド グアテマラブレンド", 200, True, None, None),
    ("143", "ハウスブレンド コロンビアブレンド", 200, True, None, None),
    ("140", "ハウスブレンド モカブレンド", 200, True, "中深煎り", "中深煎りタイプ"),
    ("137", "ハウスブレンド ブラジルブレンド", 200, True, None, None),
    ("132", "ハウスブレンド カリビアンブレンド", 200, True, "中深煎り", "中深煎りタイプ"),
    ("131", "ハウスブレンド アフリカンブレンド", 200, True, "深煎り", "深煎りタイプ"),
    ("37", "ブレイクファーストブレンド カフェマッティーナ", 200, True, None, None),
    ("104", "ハウスブレンド ティンガティンガ", 200, True, "深煎り", "深煎りのため酸味はあまりきつくありません"),
    ("118", "ハウスブレンド ココベルベット", 200, True, "深煎り", "深煎りのため酸味はきつくありません"),
    ("119", "ニカラグア ジャバニカ", 200, False, None, None),
    ("167", "タンザニア AA キリマンジャロ", 500, False, "深煎り", "深く焙煎することで…"),
    ("151", "ハウスブレンド アイスブレンド", 500, True, None, None),
    ("133", "グアテマラ SHB サンマルコス", 500, False, None, None),
    ("106", "ハウスブレンド カフェヴィータ(エスプレッソ用ブレンド)", 500, True, None, None),
    ("121", "バリアラビカ神山(SHINZAN)", 500, False, None, None),
    ("120", "コロンビア シエラネバダ農園", 500, False, None, None),
    ("107", "グアテマラ デカフェ カフェインレス", 500, False, None, None),
    ("129", "モカ デカフェ カフェインレス", 500, False, None, None),
]

# 商品名から産地を検出できないものの明示(バリ島産のアラビカ)
ORIGIN_OVERRIDES = {"121": "インドネシア"}

PRICE_TAX_PATTERN = re.compile(r"税込\s*:\s*([\d,]+)\s*円")
PRICE_PATTERN = re.compile(r"販売価格\s*:\s*([\d,]+)\s*円")
TAG_LINE_PATTERN = re.compile(r"^(?:【[^】]*】\s*)+$")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def clean_description(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or TAG_LINE_PATTERN.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def build_record(pid: str, name: str, weight_g: int, is_blend: bool, roast_level: str | None, roast_hint: str | None) -> dict:
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product/{pid}"), "html.parser")
    text = soup.get_text(" ", strip=True)
    tax_m = PRICE_TAX_PATTERN.search(text)
    price_m = PRICE_PATTERN.search(text)
    price = int((tax_m or price_m).group(1).replace(",", "")) if (tax_m or price_m) else None
    stock_el = soup.select_one(".stock")
    stock_text = stock_el.get_text(strip=True) if stock_el else ""
    sold_out = any(w in stock_text for w in ("なし", "品切", "SOLD"))
    status = "完売" if sold_out else "販売中"

    d = soup.select_one("div.item_desc_text")
    full_desc = clean_description(d.get_text("\n", strip=True)) if d else ""
    desc = re.sub(r"\s+", " ", full_desc)[:400] or None

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(unicodedata.normalize("NFKC", name))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if pid in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
            parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"] and full_desc:
            c = detect_country_name(full_desc)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
    if is_blend:
        parsed["processing_method"] = None
    elif not parsed["processing_method"] and full_desc:
        parsed["processing_method"] = extract_from_description(full_desc.replace("生産処理", "精選方法"))["processing_method"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": status,
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/product/{pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, name, weight_g, is_blend, roast_level, roast_hint in ITEMS:
        try:
            records.append(build_record(pid, name, weight_g, is_blend, roast_level, roast_hint))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hachigatsunoinu.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hachigatsunoinu.json に出力しました")


if __name__ == "__main__":
    main()
