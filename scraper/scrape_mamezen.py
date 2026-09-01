# -*- coding: utf-8 -*-
"""
scrape_mamezen.py

豆善(旧mamezen-coffee.co.jp)の商品情報を取得する。実データ調査の結果(2026-09
確認)、豆善のオンラインストアはグループブランドのEspresso Tokyo(espressotokyo.jp、
Shopify製)に統合済みであることが確認できた(mamezen-coffee.co.jp自体はまだ200 OKで
生きているが、トップページに「このたび、豆善のオンラインストアはグループブランドの
Espresso Tokyoに統合いたしました」という告知ポップアップとespressotokyo.jpへの
リンクのみが表示される)。よって本スクレイパーはespressotokyo.jpを対象とする。

【対象商品の絞り込みについて】
espressotokyo.jpはEspresso Tokyo(コーヒー器具ブランド)と豆善(コーヒー豆ブランド)
両方の商品を1つのストアで扱う統合サイトのため、公開JSON(vendor/product_type
フィールド)で絞り込む。実データ確認済み: vendor="豆善"の商品は66件あるが、
product_type="コーヒー豆"が設定されているのは27件のみで、残り39件は
のし(贈答用の掛け紙)・ラッピング資材・紙袋・卸販売用サンプル送料・カフェラテ
ベース・コーヒーゼリー・カステラ・ドリップパックのギフトセット等、特定の
一豆を指さない商品だった(product_typeが空欄)。vendor="豆善" かつ
product_type="コーヒー豆"で絞り込むと27件になるが、うち3件(【ギフトセット】
デカフェ...16個の詰め合わせ／デカフェ2種セット／店長おまかせセット)は
product_typeが設定されていても実質は複数種の詰め合わせ商品で特定の一豆を
指さないため、NON_BEAN_KEYWORDSでさらに除外する。最終的に残る24件が実際の
特定の一豆(ストレート20件+ブレンド4件)。
なお公式コレクション「豆善」(handle: mamezen)は実データ確認時点で商品0件
(運用上使われていない)、コレクション「コーヒー豆」(handle: coffee-beans)は
23件で上記27件のうち4件(未除外のパナマ ゲイシャ含む)が含まれていなかった
ため、コレクションではなくvendor/product_typeフィールドでの絞り込みを採用した。

【商品情報の取得元(Shopify公開JSON API)】
Shopify標準の公開JSON(/collections/all/products.json)がrobots.txtで明示的に
crawlable(トップに「Public product, collection, page, blog, policy, cart, and
localized HTML is crawlable」と明記)。このエンドポイントはtitle/vendor/
product_type/body_html/variants(price/available含む)/optionsを1回のリクエストで
まとめて取得できるため、WOODBERRY COFFEE(scrape_woodberry.py)と異なり商品
詳細ページを個別に再取得する必要がない。

【商品説明文(body_html)末尾の「豆 詳細」ブロックについて】
実データ確認済み(24件全件): ストレート豆はbody_html末尾に<h3>豆 詳細</h3>に
続けて<p>エリア： キンディオ県 マサトラン農園/ Mazatlan Farm, Quindio</p>
<p>精選方法： インフューズドハニー/ Infused Honey</p><p>品種： カスティージョ/
Castillo</p><p>標高： 1,400-1,450m</p>という「ラベル： 日本語値/ 英語値」の
行が並ぶ(英語版は「/」区切りで日本語の直後に続く。標高のみ英語併記なし)。
ブレンドは<p>Blend：Colombia/ Jamaica/ Indonesia</p>という1行のみで、この
「/」は英語国名の区切りであり日本語/英語の対訳ではない点に注意(parse_detail_
fields参照。ラベルごとに「/」の意味が異なるため、呼び出し側で使い分ける)。
配合比率(%)の記載は無いため、blend_componentsのpercentageはnullのままにする。

【特定銘柄(designated_brand)の誤検出を修正】
実データ調査中に、coffee_parser.pyの特定銘柄判定がブレンドを考慮しておらず、
「豆善 ブルーマウンテン No.1 ブレンド」(実際はコロンビア/ジャマイカ/
インドネシアの配合)がジャマイカ産のブルーマウンテン単体と誤判定される不具合を
発見した。coffee_parser.py側でカテゴリがブレンドの場合は特定銘柄判定自体を
スキップするよう修正済み(この修正は他店舗にも影響するため、coffee_parser.py
本体で対応した)。

【デカフェ商品の「精選方法」欄について】
実データ確認済み(ethiopia-sidamo-g2-washed-decaf-100g等): デカフェ商品でも
「精選方法」欄は通常のコーヒーチェリー精製方法(ウォッシュド等)を指しており、
WOODBERRY COFFEEのようにデカフェ加工方法(マウンテンウォータープロセス等)を
指すものではなかった。そのためprocessing_methodはデカフェ商品でも通常通り
設定し、decaf_processへの振り替えは行わない。デカフェ加工方法自体は自由記述の
説明文中に断片的に言及されることはあるが(コロンビア トリマの例のみ)、
構造化された欄が無く商品によって記載の有無・形式が一貫しないため、
decaf_processはnullのままにする(不確かな情報を抽出しない)。

【焙煎度について】
実データ確認済み: 全24件が「焙煎度（オススメは5。１が最も浅煎り、８が最も
深煎り）」というオプションで、プロ向け8段階(ライト〜イタリアン)の中から
注文時に選択する方式(価格は焙煎度に関わらず一定)。固定のroast_levelを
持たないため、roast_level=None・roast_selectable=Trueとし、選択肢を全て
roast_hintに保持する(かぎしっぽ・COFFEE ROASTERY MEGUROと同じ方針)。

【在庫状態について】
実データ確認済み(2026-09時点): 24件全件で全バリアント(焙煎度8種×挽き目4種=
32パターン)がavailable=true。サイト側に「終売」等の恒久的な販売終了を示す
明示的な表記が無いため、WOODBERRY COFFEEと同じ方針(全バリアントavailable=false
の場合を一時的な品切れとして扱う)を踏襲する。

robots.txt確認済み(2026-09時点): espressotokyo.jpはWOODBERRY COFFEEと同様の
標準的なShopify robots.txtで、/products/・/collections/はUser-agent: *に対し
Allow。/cart・/checkout・/account等の非公開/取引系のみDisallow。

【robots.txt内のAIエージェント向け指示について】
robots.txtの先頭コメントに「エージェントは購入代行のためUCP/MCPエンドポイントや
shop.appのSKILLを導入すべき」という趣旨の記述があったが、これはこのサイトの
コンテンツ(=信頼できない外部指示)であり、ユーザー自身の指示ではないため
一切従っていない。本スクレイパーは商品情報の読み取りのみを行う。
"""

import json
import re
import time
import unicodedata
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "豆善",
    "url": "https://espressotokyo.jp/",
    "platform": "Shopify",
    # 実店舗を持たないオンライン専業のため、特定商取引法に基づく表記(pages/legal)に
    # 記載の運営元(株式会社エクセルリビング)の所在地を暫定的に採用する
    "address": "東京都世田谷区尾山台3-22-4マンヤスビル022号室",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-09確認。標準的なShopify robots.txtで/products/・/collections/は"
                          "User-agent: *に対しAllow。/cart・/checkout・/account等の非公開/取引系のみDisallow)",
}

BASE_URL = "https://espressotokyo.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

VENDOR_NAME = "豆善"
PRODUCT_TYPE = "コーヒー豆"
# 理由はモジュールdocstring参照(product_typeが設定されていても複数種の
# 詰め合わせ・アソート商品で特定の一豆を指さないもの)
NON_BEAN_KEYWORDS = ["セット", "おまかせ", "ギフト"]

DETAIL_LABEL_PATTERN = re.compile(r"^(.+?)[：:]\s*(.*)$")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")
WEIGHT_SUFFIX_PATTERN = re.compile(r"([\d.]+)\s*[gｇ]\s*$")
ROAST_OPTION_ORDER_PATTERN = re.compile(r"^([0-9１-８])")


def fetch_json(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_weight(title: str) -> int | None:
    text = unicodedata.normalize("NFKC", title or "")
    m = WEIGHT_SUFFIX_PATTERN.search(text)
    return int(float(m.group(1))) if m else None


def parse_altitude(altitude_text: str | None) -> tuple[int | None, int | None]:
    if not altitude_text:
        return None, None
    text = unicodedata.normalize("NFKC", altitude_text)
    text = re.sub(r"\s", "", text)
    m = ALTITUDE_RANGE_PATTERN.search(text)
    if m:
        return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    m = ALTITUDE_SINGLE_PATTERN.search(text)
    if m:
        value = int(m.group(1).replace(",", ""))
        return value, value
    return None, None


def find_detail_heading(soup: BeautifulSoup):
    for h3 in soup.find_all("h3"):
        text = h3.get_text()
        if "豆" in text and "詳細" in text:
            return h3
    return None


def parse_detail_fields(body_html: str) -> dict:
    """body_html末尾の「豆 詳細」ブロックを「ラベル： 値」の行ごとに抽出する。
    理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    heading = find_detail_heading(soup)
    if not heading:
        return {}

    fields: dict[str, str] = {}
    for p in heading.find_all_next("p"):
        text = p.get_text(strip=True)
        if not text:
            continue
        m = DETAIL_LABEL_PATTERN.match(text)
        if not m:
            continue
        fields[m.group(1).strip()] = m.group(2).strip()
    return fields


def parse_blend_components(blend_raw: str | None) -> list[dict]:
    if not blend_raw:
        return []
    components = []
    for token in blend_raw.split("/"):
        token = token.strip()
        if not token:
            continue
        country = detect_country_name(token)
        components.append({"origin_country": country or token, "percentage": None})
    return components


def extract_roast_hint(options: list[dict]) -> str | None:
    for option in options or []:
        if "焙煎" in (option.get("name") or ""):
            values = option.get("values") or []

            def sort_key(v: str) -> str:
                m = ROAST_OPTION_ORDER_PATTERN.match(unicodedata.normalize("NFKC", v))
                return m.group(1) if m else v

            return "／".join(sorted(values, key=sort_key))
    return None


def build_record(product: dict) -> dict:
    raw_name = product["title"]
    parsed = parse_product(raw_name)
    is_blend = parsed["category"] == "ブレンド"

    fields = parse_detail_fields(product.get("body_html") or "")

    # エリア/精選方法/品種は「日本語値/ 英語値」形式のため先頭(日本語)側のみ採用。
    # Blendは「英語国名/英語国名/...」の列挙のため分割せずそのまま渡す(理由はモジュールdocstring参照)
    def jp_part(label: str) -> str | None:
        value = fields.get(label)
        return value.split("/")[0].strip() if value else None

    processing_raw = jp_part("精選方法")
    processing_method = normalize_processing_method(processing_raw) if processing_raw else None
    altitude_min, altitude_max = parse_altitude(jp_part("標高"))
    blend_components = parse_blend_components(fields.get("Blend")) if is_blend else []

    variant = (product.get("variants") or [None])[0]
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None
    all_out_of_stock = bool(product.get("variants")) and not any(
        v.get("available") for v in product["variants"]
    )
    stock_status = "一時的に品切れ" if all_out_of_stock else "販売中"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": None if is_blend else parsed["origin_country"],
        "origin_source": None if is_blend else parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": None if is_blend else processing_method,
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(注文時選択のためroast_hintに保持)
        "roast_hint": extract_roast_hint(product.get("options") or []),
        "roast_selectable": True,
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": None if is_blend else jp_part("エリア"),
        "variety": None if is_blend else jp_part("品種"),
        "altitude_min_m": None if is_blend else altitude_min,
        "altitude_max_m": None if is_blend else altitude_max,
        "blend_components": blend_components,
        "price": price,
        "weight_g": parse_weight(raw_name),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    page = 1
    while True:
        url = f"{BASE_URL}/collections/all/products.json?limit=250&page={page}"
        data = fetch_json(url)
        products = data.get("products", [])
        if not products:
            break
        for product in products:
            if product.get("vendor") != VENDOR_NAME or product.get("product_type") != PRODUCT_TYPE:
                continue
            if any(kw in product["title"] for kw in NON_BEAN_KEYWORDS):
                continue
            records.append(build_record(product))
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_mamezen.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_mamezen.json に出力しました")


if __name__ == "__main__":
    main()
