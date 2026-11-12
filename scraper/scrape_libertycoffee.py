# -*- coding: utf-8 -*-
"""
scrape_libertycoffee.py

珈琲工房リバティ(https://libertycafe.theshop.jp/、群馬県高崎市下室田町889、榛名山麓の自家焙煎珈琲工房)の
商品情報を取得する。BASE(theshop.jp)。

【店舗発見の経緯】
群馬県の再調査(2026-10-26)で、過去の見送り(商品数が多く同一銘柄が別URLで重複)をロジックで解消できると判断して実装。

【対象商品について】
実データ確認済み(2026-10-26): ショップは全304商品で、焙煎豆は「重量(100g/200g/…/2kg)×挽き方(豆/粉)」ごとに
別商品として並び、同一銘柄が別URLで重複し、乾物・食品・器具・ドリップ教室・チョコレート等も混在する。
そこでカテゴリ「珈琲豆」と全商品一覧から、銘柄ごとに1商品に統合し、最小重量(100gがあれば100g)の
「豆のまま(豆でも粉でも可を含む)」の商品を代表にして、下のITEMSに商品ID・銘柄名・重量を固定している。
除外: 【粉】指定の商品、1kg以上(業務用・大容量)のみの銘柄、セット・福袋・ギフト、ドリップバッグ/パック、
コピー商品(「コピー：」)、重複登録、コーヒー以外(食品・器具・講座等)。
価格(割引表示がある場合は割引後の販売価格)・在庫(item_purchasability)・説明(og:description)・
焙煎度(説明文)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import html
import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲工房リバティ",
    "url": "https://libertycafe.theshop.jp/",
    "platform": "BASE",
    "address": "群馬県高崎市下室田町889",
    "prefecture": "群馬県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "https://libertycafe.theshop.jp/law (所在地・営業時間9-18時・木曜定休)、/about (榛名山麓の小さな珈琲工房、手網で直火焙煎)、各商品ページを2026-10-26に確認。同一銘柄が重量違い・挽き方違いで並ぶため、銘柄ごとに最小重量の豆のままの商品を代表に統合。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://libertycafe.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 銘柄名, 重量(g), 分類の上書き(Noneなら自動判定), 産地(ブレンド/不明はNone))
ITEMS = [
    ("40151123", "さくらブルボン", 100, None, None),
    ("35427607", "ニカラグア マラゴジッペ", 100, None, "ニカラグア"),
    ("33403464", "焚き火コーヒー", 100, None, None),
    ("32797391", "コスタリカ ガンボア農園 ホワイトハニー", 100, None, "コスタリカ"),
    ("32797359", "エチオピア ゲイシャ ゲレナ農園", 100, None, "エチオピア"),
    ("32797103", "ウガンダ アフリカムーン", 100, None, "ウガンダ"),
    ("32792066", "エチオピア イルガチャフィ", 100, None, "エチオピア"),
    ("32796831", "コロンビア サンアグスティン農園 カフェインレス", 100, None, "コロンビア"),
    ("32796654", "イエメン モカマタリ NO.9", 100, None, "イエメン"),
    ("32794882", "メキシコ アルツーラ", 100, None, "メキシコ"),
    ("32794750", "エルサルバドル サント トマス農園 ブルボン", 100, None, "エルサルバドル"),
    ("32794169", "ブラジル アマレロブルボン", 100, None, "ブラジル"),
    ("32794626", "ブラジル プレミアムショコラ サントアントニオ農園", 100, None, "ブラジル"),
    ("32794563", "トラジャ", 100, None, "インドネシア"),
    ("32792225", "LIBERTYHEART", 100, None, "グアテマラ"),
    ("32794036", "焼きまんじゅうがどんどんすすんじゃう うんめぇコーヒー", 100, "ブレンド", None),
    ("32793844", "ケニア AA", 100, None, "ケニア"),
    ("32793771", "エチオピア レケンプティ", 100, None, "エチオピア"),
    ("32792768", "インドネシア マンデリン G1", 100, None, "インドネシア"),
    ("32793675", "コロンビア スプレモ", 100, None, "コロンビア"),
    ("32793610", "リバティブレンド", 100, "ブレンド", None),
    ("32793525", "ブラジル サントス", 100, None, "ブラジル"),
    ("32792868", "令和ブレンド", 100, "ブレンド", None),
    ("32793066", "タンザニア キリマンジャロ", 100, None, "タンザニア"),
    ("32792681", "エチオピア シダモ", 100, None, "エチオピア"),
    ("32792631", "ペルー チャンチャマイヨ MCM", 100, None, "ペルー"),
    ("32792332", "ブラジル ピーベリー", 100, None, "ブラジル"),
    ("32612843", "ハワイコナ", 100, None, "アメリカ"),
    ("32612079", "ジャマイカ ブルーマウンテン NO.1", 100, None, "ジャマイカ"),
    ("35494007", "ハニーショコラ", 200, None, "ブラジル"),
    ("39387894", "ブルンジ レッドブルボン", 200, None, "ブルンジ"),
    ("41431622", "ブラジル 山口農園 ブルボン", 200, None, "ブラジル"),
    ("41431343", "手摘み完熟コーヒー豆", 200, None, "ブラジル"),
    ("40763916", "トラジャ 無農薬", 200, None, "インドネシア"),
    ("40667186", "メキシコ SHG クステペック農園", 200, None, "メキシコ"),
    ("40487716", "フルッタ・メルカドン", 200, None, "ブラジル"),
    ("40150963", "ペルー マチュピチュインカウアイ", 200, None, "ペルー"),
    ("40150932", "リバティのカフェインレス", 400, None, "コロンビア"),
    ("32613310", "ブラジル モンテアレグレ", 200, None, "ブラジル"),
    ("32613016", "マラウィ チシ ミスク", 200, None, "マラウイ"),
    ("32611241", "ブラジル フルーツバスケット", 200, None, "ブラジル"),
    ("32609535", "極みアイスコーヒー豆", 200, "ブレンド", None),
    ("32609089", "モカスペシャル", 300, None, None),
    ("32607104", "ブラジル ブライトミナス サルト農園 パルプドナチュラル", 200, None, "ブラジル"),
    ("32607052", "ラオス G-1 ナチュラル ボラベン", 200, None, "ラオス"),
    ("32606948", "モカブレンド 深煎り", 200, "ブレンド", None),
    ("32603014", "ホンジュラス", 200, None, "ホンジュラス"),
    ("32602839", "ドミニカ バラオナ", 200, None, "ドミニカ共和国"),
    ("32613736", "超ブレンド", 400, "ブレンド", None),
    ("32611592", "東ティモール ハウレウン 無農薬", 200, None, "東ティモール"),
    ("35557371", "ブラジル サントス スペシャル", 300, None, "ブラジル"),
]

# 商品名・説明文からの自動判定が誤る/曖昧なものの焙煎度(説明文の記載に基づく。Noneは焙煎度の記載なし)
ROAST_OVERRIDES = {
    "33403464": "中煎り〜深煎り",  # 説明文「お好みで中煎り～深煎りまでお選び頂けます」
    "41431343": "中深煎り〜深煎り",  # 説明文「中深煎り～深煎りがチョコレート感が増します」
    "35557371": "中煎り〜深煎り",  # 説明文「中煎り焙煎と深煎り焙煎の豆をそれぞれブレンド」
    "32607104": None,  # 商品名の「ブライト」がライトローストと誤判定されるため(記載なし)
}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
DISCOUNT_PATTERN = re.compile(r"¥\s*([\d,]+)\s*\d+%\s*OFF\s*¥\s*([\d,]+)")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り|極浅煎り)")


def page_text(html_text: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(re.sub(r"\s+", " ", t))


def build_record(item_id, name, weight_g, category_override, origin):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    if resp.status_code != 200:
        print(f"[warn] HTTP {resp.status_code}: item_id={item_id}")
        return None
    html_text = resp.text
    text = page_text(html_text)

    desc_m = DESC_PATTERN.search(html_text)
    desc_full = html.unescape(desc_m.group(1)) if desc_m else ""
    desc = re.sub(r"\s+", " ", desc_full).strip()[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    disc_m = DISCOUNT_PATTERN.search(text)
    if disc_m:
        price = int(disc_m.group(2).replace(",", ""))
    pm = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(pm) and pm.group(1) == "unpurchasable"

    roast = None
    rm = ROAST_PATTERN.search(unicodedata.normalize("NFKC", desc_full))
    if rm:
        roast = rm.group(1)

    parsed = parse_product(name)
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": ROAST_OVERRIDES[item_id] if item_id in ROAST_OVERRIDES else (roast or parsed["roast_level"]),
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, origin in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, origin)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            record = None
        if record is not None:
            records.append(record)
        time.sleep(REQUEST_INTERVAL_SEC)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_libertycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_libertycoffee.json に出力しました")


if __name__ == "__main__":
    main()
