# -*- coding: utf-8 -*-
"""
scrape_okcoffee.py

OK COFFEE(OK COFFEE Saga Roastery、佐賀県神埼郡吉野ヶ里町)の楽天市場店(www.rakuten.co.jp/okcoffee)の
商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。

【楽天市場店を採用した理由】
同名の「OK COFFEE」のShopifyストア(okcoffeeroastery.com)は大阪府東大阪市の株式会社筒井商店の運営で、
IPコラボのブレンド(粉)が中心。佐賀の「OK COFFEE Saga Roastery」は楽天市場店(運営: 株式会社アイテク、
店舗運営責任者 福山 徹・コーヒー事業部)が主な販売先であることを、利用者の指摘で確認した(2026-10-19)。
ショップトップに「こだわりの自家焙煎コーヒー屋さんです」と記載。

【対象商品について】
ショップカテゴリ「コーヒー豆」(オリジナルブレンド・シングルオリジン)の豆の単品のうち、
各銘柄の最小重量・豆のままの価格(税込、メール便送料込み表記)を代表とする。
除外: 大容量(1kg・2kg)や福袋・飲み比べセット・ギフト・ドリップバッグ・水出し・カフェオレベース・スイーツ。
 - オリジナルブレンド5種(DRIVE/GAMBLE/THE BEST/MUSIC/WORKAHOLIC)は blendthebest001 の200g。
 - 平日/休日ブレンド(heijitukyujitu001)・モーニング/ランチブレンド(morninglunch001)は100g。
 - 季節限定ブレンド AUTUMN は200g(seasonalblend001)。
 - シングルオリジンは各200g(ブラジル/コロンビアの「選べる」150gは1銘柄ずつに展開)。
単品商品は SKU が無い(商品ページの価格 itemprop="price")。1kgの別ページ(*002)は代表重量でないため対象外。
販売業者: 株式会社アイテク 佐賀県神埼郡吉野ヶ里町豆田1750-1。店舗の住所はショップ情報の「返送先」を採用。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "OK COFFEE Saga Roastery",
    "url": "https://www.rakuten.co.jp/okcoffee/",
    "platform": "楽天市場",
    "address": "佐賀県神埼郡吉野ヶ里町吉田243-11",
    "prefecture": "佐賀県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ・一部パス等のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/okcoffee/)のショップカテゴリ「コーヒー豆」と各商品ページ(SKU情報)を2026-10-19に確認。住所はショップ情報の返送先",
    "last_verified_at": "2026-10-19",
}

SHOP_ID = "okcoffee"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 3

AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')

# (商品コード, SKUの選択肢に含まれるべき文字列(Noneは単品=SKUなし), 商品名, 重量g, 産地(Noneはブレンド), 焙煎度, urlフラグメント)
ITEMS = [
    ("blendthebest001", ["200g", "DRIVE"], "『DRIVE』ブレンド", 200, None, "中煎り", "drive"),
    ("blendthebest001", ["200g", "GAMBLE"], "『GAMBLE』ブレンド", 200, None, "深煎り", "gamble"),
    ("blendthebest001", ["200g", "THE BEST"], "『THE BEST』ブレンド", 200, None, "中深煎り", "thebest"),
    ("blendthebest001", ["200g", "MUSIC"], "『MUSIC』ブレンド", 200, None, "中浅煎り", "music"),
    ("blendthebest001", ["200g", "WORKAHOLIC"], "『WORKAHOLIC』ブレンド", 200, None, "極深煎り", "workaholic"),
    ("classic001", ["200g"], "『CLASSIC』リッチモカブレンド", 200, None, None, None),
    ("heijitukyujitu001", ["100g", "平日ブレンド"], "平日ブレンド", 100, None, None, "heijitsu"),
    ("heijitukyujitu001", ["100g", "休日ブレンド"], "休日ブレンド", 100, None, None, "kyujitsu"),
    ("morninglunch001", ["100g", "モーニングブレンド"], "モーニングブレンド", 100, None, None, "morning"),
    ("morninglunch001", ["100g", "ランチブレンド"], "ランチブレンド", 100, None, None, "lunch"),
    ("seasonalblend001", ["200g"], "季節限定ブレンド『AUTUMN』", 200, None, "深煎り", None),
    ("singlebrazil001", ["150g"], "ブラジル サントス", 150, "ブラジル", "中煎り", "brazil"),
    ("singlebrazil001", ["150g"], "コロンビア スプレモ", 150, "コロンビア", "中煎り", "colombia"),
    ("singleethiopiamocha001", None, "エチオピア モカ イルガチェフェ G2", 200, "エチオピア", "浅煎り", None),
    ("singlegayo001", None, "インドネシア ガヨマウンテン", 200, "インドネシア", "中深煎り", None),
    ("singleguatemala001", None, "グアテマラ", 200, "グアテマラ", "深煎り", None),
    ("singleharusuke001", None, "エチオピア ハルスケ", 200, "エチオピア", "浅煎り", None),
    ("singleindonesia001", ["200g"], "インドネシア『ROCK』スタイル", 200, "インドネシア", "極深煎り", None),
    ("singlejaguar001", None, "コスタリカ ジャガーハニー", 200, "コスタリカ", "中煎り", None),
    ("singlekilimanjaro001", None, "キリマンジャロ", 200, "タンザニア", "深煎り", None),
    ("singlelaos001", None, "ラオス", 200, "ラオス", "深煎り", None),
    ("singlemandarin001", None, "マンデリン", 200, "インドネシア", "深煎り", None),
    ("decafethiopia001", ["200g"], "エチオピア デカフェ", 200, "エチオピア", "深煎り", None),
]


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.encoding = "euc-jp"
    return resp


def extract_skus(html_text: str) -> list[dict]:
    """ページに埋め込まれた "sku":[...] のJSON配列を括弧対応で切り出す。"""
    i = html_text.find('"sku":[')
    if i < 0:
        return []
    start = i + len('"sku":')
    depth, in_str, esc = 0, False, False
    for k in range(start, len(html_text)):
        ch = html_text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == chr(92):
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html_text[start:k + 1])
    return []


_cache: dict = {}


def page_html(code: str):
    if code in _cache:
        return _cache[code]
    if _cache:
        time.sleep(REQUEST_INTERVAL)
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        _cache[code] = None
        return None
    _cache[code] = resp.text
    return resp.text


def build_record(code, sel, name, weight, origin, roast, frag):
    html_text = page_html(code)
    if not html_text:
        return None
    price = None
    if sel is None:
        m = PRICE_PATTERN.search(html_text)
        price = int(m.group(1)) if m else None
    else:
        for s in extract_skus(html_text):
            vals = unicodedata.normalize("NFKC", " ".join(s.get("selectorValues") or []))
            if all(unicodedata.normalize("NFKC", k) in vals for k in sel):
                price = int(s["taxIncludedPrice"])
                break
    if price is None:
        print(f"[warn] 価格取得失敗: {code} {name}")
        return None
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    parsed = parse_product(name)
    if origin is None:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "shop_attribute"
    url = ITEM_URL.format(code=code) + (f"#{frag}" if frag else "")
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list:
    records = []
    for item in ITEMS:
        rec = build_record(*item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_okcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_okcoffee.json に出力しました")


if __name__ == "__main__":
    main()
