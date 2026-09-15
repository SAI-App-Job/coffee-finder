# -*- coding: utf-8 -*-
"""
scrape_bysenmon.py

THE ROASTERY 焙煎門(coffee.trb-lab.com、宮崎県都城市山田町中霧島3292-4
(谷頭エリア)、自家焙煎豆のオンライン販売・店頭販売)の商品情報を取得する。
Astroベースの独自ECサイト(BASE/Ocnk/shop-pro等の既知プラットフォームでは
ない、自社開発のオンラインショップ)。

【営業状況について】
実データ確認済み(2026-09時点): トップページ(https://coffee.trb-lab.com/)に
「毎週日曜日 13:00〜16:00」との営業日表記あり。テイクアウト専門の小さな
焙煎所・コーヒースタンドとして現在も稼働中(候補リストの「Sundays-only
takeout stand」を裏付け)。

【住所について】
公式サイト自身に実データ確認済み(2026-09時点、特定商取引法ページは無いが
トップページのACCESSセクションに構造化表示): 「THE ROASTERY 焙煎門
ADDRESS 宮崎県都城市山田町中霧島3292-4（谷頭エリア）」との記載を確認。
候補リストの住所と一致。

【プラットフォーム・robots.txtについて】
実データ確認済み: Astroフレームワークで構築された自社ECサイト
(https://coffee.trb-lab.com/shop)。robots.txt自体は存在せず(直接アクセス
するとSPAのトップページがフォールバックで返る、404ハンドラ未設定の
典型的な挙動)、明示的な禁止事項が無いため実質許可として扱う。
Cloudflareのチャレンジプラットフォーム(cdn-cgi/challenge-platform)の
スクリプトタグがページに埋め込まれているが、実データ確認済み: 通常の
requestsでのAPI直接アクセス(下記)はチャレンジを要求されず200が返る。

【商品情報の取得方法について】
実データ確認済み: オンラインショップ(/shop)はJSでレンダリングされるSPAで、
実データは`/api/products`(JSON、認証不要)から取得している。各商品には
`product_type`フィールドがあり、"roasted_beans"(焙煎豆)・"drip_bag"
(ドリップバッグ)・"gift_set"(ギフトセット)に分類されている。本
スクレイパーは"roasted_beans"のみを対象とする。

【対象商品について】
実データ確認済み(全18件中roasted_beansは14件): 「焙煎門 飲みくらべ
セット」(90g、複数銘柄の少量詰め合わせ)は単一銘柄ではないため
NON_BEAN_KEYWORDS("セット")で除外し、残り13件を採用する。

【焙煎度について】
実データ確認済み: APIの`roast_level`フィールドは"dark"/"medium"/"light"の
3値のみで、本プロジェクトが採用する8段階(ライト/シナモン/ミディアム/
ハイ/シティ/フルシティ/フレンチ/イタリアン)のどれに対応するか一意に
決められないため、このフィールドは使用しない。商品名自体に焙煎度を示す
語が含まれないため、roast_levelは全件nullとなる(不正確な推測をしない
ための意図的な判断)。

【産地について】
実データ確認済み: 商品名(例:「タンザニア（キリマンジャロ）」「タイ
アナエロビック」)に国名表記が含まれるため、通常のparse_product()による
商品名解析で産地・特定銘柄が取得できる。「ゲイシャ」のみAPIのorigin
フィールドが「限定ロット」(産地不特定のスペシャル枠を示す語であり実際の
国名ではない)で、商品名にも国名表記が無いため、origin_countryはnullの
まま(不明)とする。

なお「タイ アナエロビック」は商品名・APIのoriginフィールド双方に「タイ」
とあるが、coffee_parser.pyのORIGIN_COUNTRY_KEYWORDSには日本語表記の
「タイ」は含まれていない(「タイ」は他の日本語単語に頻出する2文字のため、
自由記述文からの誤検出を避ける目的で意図的に未収録と見られる。英語表記
"thailand"のみ収録)。本スクレイパーではAPIの構造化originフィールドが
厳密に「タイ」と完全一致する場合に限りローカルに国名を補完する
(coffee_parser.py共通ロジックの変更は本タスクの範囲外のため、voilacoffee
等と同様にスクレイパー内でローカル補正する)。

【価格・重量について】
実データ確認済み: 対象13件は全て挽き方違い(豆のまま/中細挽き/粗挽き)の
3バリアントを持つが、実データ確認済みでいずれも同一価格・同一重量
(100g)。本スクレイパーは商品本体のprice_tax_included/weight_gramsを
そのまま採用する(挽き方による価格差は無い)。
"""

import requests

from coffee_parser import parse_product, detect_stock_status, detect_country_name

SHOP_INFO = {
    "name": "THE ROASTERY 焙煎門",
    "url": "https://coffee.trb-lab.com/",
    "platform": "独自ECサイト(Astro)",
    "address": "宮崎県都城市山田町中霧島3292-4",
    "prefecture": "宮崎県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在せず"
                          "SPAのトップページがフォールバックで返る。"
                          "明示的な禁止事項なし)",
}

API_URL = "https://coffee.trb-lab.com/api/products"
PRODUCT_URL_TEMPLATE = "https://coffee.trb-lab.com/shop/{slug}/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット"]


def fetch_products() -> list[dict]:
    resp = requests.get(API_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def build_record(product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = PRODUCT_URL_TEMPLATE.format(slug=product.get("slug", ""))
    price = product.get("price_tax_included")
    weight_g = product.get("weight_grams")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    # 商品名に国名表記が無い場合のみ、構造化originフィールドからの
    # フォールバックを試みる(理由はモジュールdocstring参照。「限定ロット」等
    # 実際の国名でない値はdetect_country_nameがNoneを返すため無害)。
    if not parsed["origin_country"]:
        api_origin = (product.get("origin") or "").strip()
        country = detect_country_name(api_origin)
        if not country and api_origin == "タイ":
            # 理由はモジュールdocstring参照(coffee_parser.pyに未収録の国名のローカル補正)
            country = "タイ"
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "description"

    stock_status = detect_stock_status(title, (product.get("stock_quantity") or 0) <= 0)

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = [p for p in fetch_products() if p.get("product_type") == "roasted_beans"]

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_bysenmon.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bysenmon.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
