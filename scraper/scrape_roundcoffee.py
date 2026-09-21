# -*- coding: utf-8 -*-
"""
scrape_roundcoffee.py

round coffee ITOSHIMA(round-coffee.com、福岡県糸島市二丈深江2129-12、
自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify(/products.json)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /、制限なし。

【商品構成について】
実データ確認済み(2026-09時点、全6商品): product_type="コーヒー豆"が3件
(「シングルオリジン」「オリジナルブレンド」「デカフェ」)、"焼き菓子"が3件
(バナナケーキ等、非対象)。product_typeで機械的に絞り込める。

【1商品に複数銘柄が同梱されている点について】
実データ確認済み: 他店舗と異なり、この3商品はそれぞれ1つのShopify商品に
複数の実銘柄がoptions「豆の種類」のバリエーションとして同梱されている
(例:「シングルオリジン」商品にHuai Chompu/Las Perlitas/Las Deliciasの
3銘柄、重量(100/200/300g)・形態(豆/粉)と組み合わせた全18バリアント)。
本スクレイパーは「豆の種類」ごとに1レコードを生成し、重量は最小(100g)・
形態は「豆のまま」のバリアントの価格を代表として採用する。

【産地情報について】
実データ確認済み: 各商品ページのbody_html本文に銘柄ごとの紹介文が
「▪️<焙煎度>　<銘柄名>」(シングルオリジン)または「■<銘柄名>」
(オリジナルブレンド/デカフェ)の見出しで区切られ、「産地：<国名(英語)>」
(オリジナルブレンドのみ「・産地」の次行に「：<国名> × <国名>」の
2か国併記)という自由記述で産地が書かれている。見出し区切り・
ラベル位置(同じ行/次の行)が3商品間で微妙に異なり汎用パーサーの
信頼性が低いため、本スクレイパーでは実データから確認した銘柄名→産地の
対応表(BEAN_INFO)を保持し、options["豆の種類"]の値をキーに引く方式を
採る(価格・重量・在庫は毎回API経由で動的取得するため、この対応表が
古くなった場合は該当銘柄がBEAN_INFOに無い商品として除外され、誤った
産地を出力することはない)。

【デカフェについて】
実データ確認済み: 2銘柄とも「マウンテンウォーター・デカフェ」等の有機認証
製法。decaf_processの詳細な処理名までは自由記述から一意に確定できな
かったため、"デカフェ処理(詳細不明)"として保持する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 産地情報と同様、body_html本文には銘柄ごとに
「■<キャッチコピー>」見出し+テイスティング文+「■このコーヒーについて」
(焙煎度・風味キーワード・★アイコンによる苦味/酸味/甘さ/華やかさ評価・
淹れ方)が続く自由記述があるが、見出し区切りが3商品間で微妙に異なり
汎用パーサーでの信頼性が低いため、産地と同じくBEAN_INFO対応表に
キャッチコピー+テイスティング文+風味キーワードを直接保持する方式を
採る(★アイコン評価・淹れ方は定型的な補足情報のため含めない)。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "round coffee ITOSHIMA",
    "url": "https://round-coffee.com/",
    "platform": "Shopify",
    "address": "福岡県糸島市二丈深江2129-12",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://round-coffee.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(body_htmlの自由記述から実データ確認済みの
# 銘柄→産地対応表)
BEAN_INFO = {
    "【浅煎り】Huai Chompu": {
        "country": "タイ", "processing": "アナエロビック・ナチュラル", "category": "ストレート",
        "flavor_notes": "華やかな気分にしてくれるコーヒー。滑らかな口当たりで、口に含むとマスカットや"
                         "白ワインを連想させる豊かな香りが広がります。少し温度が下がるとより甘みを感じ、"
                         "トロピカルフルーツのようです。飲んでいて華やかな気分にさせてくれるコーヒーです。"
                         "風味：マスカット、白ワイン、マイヤーレモン、はちみつ",
    },
    "【中煎り】Las Perlitas": {
        "country": "コロンビア", "processing": "ウォッシュド", "category": "ストレート",
        "flavor_notes": "白桃から柑橘へフルーティーなコーヒー。中煎りらしいボディを感じつつも、"
                         "フルーティーさを楽しめるコーヒーです。ブルーベリージャムのような甘さから、"
                         "温度が下がると白桃のような甘さに変わっていきます。アフターテイストに若干"
                         "柑橘系の爽やかさがあり、次の一口が止まらないコーヒーです。"
                         "風味：ブルーベリー、ネーブルオレンジ、白桃",
    },
    "【中深煎り】Las Delicias": {
        "country": "ニカラグア", "processing": "ナチュラル", "category": "ストレート",
        "flavor_notes": "様々なシーンやフードに合わせやすいコーヒー。中深煎りならではの豊かなコクと"
                         "苦味、そしてそのなかにも甘みを楽しんでいただけるコーヒーです。しっかり目の"
                         "紅茶のような印象の中にも、ベリー系の爽やかさも少し感じられ、焼き菓子と"
                         "合わせやすいのが特徴的です。風味：紅茶、プラム、ビターチョコレート",
    },
    "ITOSHIMA 読書 BLEND（Tanzania×Nicaragua": {
        "category": "ブレンド", "blend_components": ["タンザニア", "ニカラグア"],
        "flavor_notes": "ITOSHIMA 読書BLEND。初めのうちはタンザニアの持つドライフルーツのような"
                         "甘味や香りが印象的ですが、温度が下がるにつれてニカラグアのまろやかな味わいが"
                         "顔を出してきます。本を読んだりしながら、ゆっくりと味の変化を楽しみたくなる"
                         "コーヒーです。風味：セミドライトマト、ドライアプリコット、カラメル、"
                         "ピンクグレープフルーツ",
    },
    "糸島 OUTDOOR Blend (Ethiopia×Thailand)": {
        "category": "ブレンド", "blend_components": ["エチオピア", "タイ"],
        "flavor_notes": "糸島 OUT DOOR BLEND。しっかりとした甘みと軽やかなフルーティさが気分を"
                         "リフレッシュさせてくれ、アウトドアでの休憩中に飲みたくなるコーヒーです。"
                         "軽めの酸味とふくよかなコクが引き立ち、後味にはほんのりと甘さが残り心地よい"
                         "余韻が楽しめます。風味：紅茶、野いちご、白桃、烏龍茶",
    },
    "DECAF (コクと甘み：中煎り)": {
        "country": "メキシコ", "decaf": True,
        "flavor_notes": "糸島DECAFE -コクと甘み-。口に含むと濃厚な甘みが口いっぱいに広がり、"
                         "また温度が下がると今度は柔らかな酸味がほんのり現れて表情を変えてくれます。"
                         "まろやかで甘みのあるコーヒーをお探しの方にオススメです。"
                         "風味：カシス、ダークチョコレート、プラム",
    },
    "DECAF(華やか&フルーティ：浅煎り)": {
        "country": "エチオピア", "decaf": True,
        "flavor_notes": "糸島DECAFE -華やか＆フルーティ-。白いお花のような華やかな香りと、"
                         "ホワイトグレープのような優しい甘みが心を落ち着かせ、心をリラックスさせて"
                         "くれるコーヒー。優しい味わいをお探しの方にオススメです。"
                         "風味：ジャスミン、マイヤーレモン、ホワイトグレープ、ホワイトティー",
    },
}


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict], bean_key: str) -> dict | None:
    """指定の「豆の種類」オプション値に属し、形態が「豆のまま」で最小重量の
    バリアントを選ぶ。"""
    candidates = [
        v for v in variants
        if v.get("option1") == bean_key and "粉" not in (v.get("option3") or "") and "Ground" not in (v.get("option3") or "")
    ]
    if not candidates:
        candidates = [v for v in variants if v.get("option1") == bean_key]
    if not candidates:
        return None

    def weight_key(v):
        m = re.search(r"(\d+)\s*g", v.get("option2") or "")
        return int(m.group(1)) if m else float("inf")

    return min(candidates, key=weight_key)


def build_records_for_product(product: dict) -> list[dict]:
    variants = product.get("variants") or []
    options = product.get("options") or []
    bean_option = next((o for o in options if "種類" in (o.get("name") or "")), None)
    if not bean_option:
        return []

    records = []
    for bean_key in bean_option.get("values", []):
        info = BEAN_INFO.get(bean_key)
        if info is None:
            print(f"[warn] 未知の銘柄のためBEAN_INFOに無くスキップ: {bean_key}")
            continue

        variant = pick_canonical_variant(variants, bean_key)
        price = int(float(variant["price"])) if variant and variant.get("price") is not None else None
        weight_g = None
        if variant:
            m = re.search(r"(\d+)\s*g", variant.get("option2") or "")
            weight_g = int(m.group(1)) if m else None
        all_out_of_stock = bool(variants) and not any(
            v.get("available") for v in variants if v.get("option1") == bean_key
        )

        # 銘柄名からブレンド名や焙煎度の角括弧を除いた表示用の商品名を作る
        display_name = f"{product.get('title', '')} - {bean_key}".strip()
        parsed = parse_product(display_name)
        category = info.get("category", parsed["category"])
        stock_status = detect_stock_status(display_name, all_out_of_stock)

        # 理由: 1つのShopify商品ページに複数銘柄が同梱されているため、
        # product_urlをそのままIDに使うaggregate_shops.pyのbuild_product_id()では
        # 銘柄間でID衝突する。variant idをクエリparamとして付与し、実在する
        # バリアント選択リンクとして機能させつつ銘柄ごとに一意なURLにする。
        product_url = f"https://round-coffee.com/products/{product.get('handle')}"
        if variant and variant.get("id"):
            product_url = f"{product_url}?variant={variant['id']}"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": display_name,
            "category": category,
            "origin_country": info.get("country"),
            "origin_source": "product_description" if info.get("country") else None,
            "designated_brand": parsed["designated_brand"],
            "processing_method": info.get("processing"),
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "flavor_notes": info.get("flavor_notes"),
            "post_processing_tags": parsed["post_processing_tags"],
            "decaf_process": "デカフェ処理(詳細不明)" if info.get("decaf") else None,
            "blend_components": info.get("blend_components", []),
            "price": price,
            "weight_g": weight_g,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": product_url,
        })
    return records


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()

    records = []
    for product in products:
        if product.get("product_type") != "コーヒー豆":
            continue
        records.extend(build_records_for_product(product))

    return records, []


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_roundcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_roundcoffee.json に出力しました")
