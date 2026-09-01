# -*- coding: utf-8 -*-
"""
scrape_woodberry.py

WOODBERRY COFFEE(woodberrycoffee.com、Shopify製)の商品情報を取得する。
東京・神奈川に直営11店舗(2026-08確認)を展開する自家焙煎コーヒー専門店。

【店舗数について】
ユーザーからは「東京を中心に直営7店舗」と伺ったが、実データ確認(2026-08時点、
/pages/locationページ)では用賀本店・渋谷店・荻窪店・代官山店・学芸大学店・
鎌倉店(神奈川県)・WOODBERRY BAKERY・たまプラーザ店(神奈川県)・玉川高島屋
Ｓ.Ｃ.店・駒沢店・大井町店の11拠点が確認できた。件数の食い違いは店舗数の
変化(出店ペースが早い)によるものと考えられるため、伝聞ではなく実データの
11拠点をそのまま採用する。

【商品情報の取得元(Shopify公開JSON API)】
Shopify標準の公開JSON(/products.json、/collections/{handle}/products.json、
/products/{handle}.json)がrobots.txtで明示的にcrawlable(トップに
「Public product, collection, page, blog, policy, cart, and localized HTML
is crawlable」と明記)。HTMLをパースするより構造化データとして直接取得できる
ため、これを利用する。

【対象を/collections/coffee_beans(コーヒー豆)に絞る理由】
店舗の全商品(/products.json)にはハンドドリップセミナー・生豆・雑貨(ORIGAMI
サーバー、STTOKEタンブラー等)・ギフトボックスも混在しており、product_type
フィールドが全商品で空(実データ確認済み)のためタイトルキーワード等での
判別が不安定。一方、公式コレクション「コーヒー豆」(handle: coffee_beans、
実データ確認済み33件)は焙煎豆のみに絞られており、これをそのままクロール
対象とする。

【商品詳細ページのbody_html内「商品詳細」ブロックについて】
実データ確認済み(33件全件): body_html末尾に<div class="item-midashi">商品詳細
</div>に続く<p>タグ内に、【生産国】【地域】【農園】/【組合】【生産者】【標高】
【品種】【プロセス】【焙煎度】(ブレンドは【配合比率】)という日本語ラベル付きの
行が並ぶ。ラベルの組み合わせは商品によって異なる(単一農園なら【農園】、
組合買い付けなら【組合】等)ため、固定キーではなく汎用的な「【ラベル】値」の
行パーサーで抽出する(parse_detail_fields参照)。この直後に同じ内容の英語版
(Country：Ecuador等)と保存方法の<details>が続くが、コロンを含む行に達したら
現在のラベルへの行の追加取り込みを止めることで、英語版や保存方法の説明文が
【配合比率】等の複数行値に混入しないようにしている。

【焙煎度をroast_hintに留め、roast_levelを構造化しない理由】
サイトの【焙煎度】表記は「浅煎り」「中煎り」「深煎り」の3段階の粗い表現で、
本アプリのroast_levelが要求するプロ向け8段階表記(ライト〜イタリアン)とは
粒度が異なる。scrape_coulane.pyで確立した方針と同じく、不確かな8段階への
変換は行わずroast_hintとして保持する。

【デカフェ商品の【プロセス】欄について】
実データ確認済み(ethiopia-tade-gg-decaf): デカフェ商品の【プロセス】欄は
「マウンテンウォータープロセス」のように脱カフェイン方法を指しており、
コーヒーチェリーの精製方法(ウォッシュド等)とは意味が異なる。scrape_itukacoffee.py
で確立した方針と同じく、商品名に「デカフェ」を含む場合はこの値をdecaf_process
に回し、processing_methodには反映しない。

【配合比率(ブレンド)のブレンド内訳について】
実データ確認済み: 【配合比率】の書式は商品によって2パターンある。
(A) classic-blend: 「インド 25％」のように国名+割合が複数行で並ぶ形式。
(B) summer-blend/filter-blend/espresso-blend/dark-note-blend: 「１：１」
「1：1：1」のような比率のみの1行形式で、割合を示す国名は【生産国】側の
スラッシュ区切り(例:「コスタリカ/ケニア」)と順序で対応させる必要がある。
このパターンでは【農園】【品種】【プロセス】もスラッシュ区切りで産地ごとの
内訳を持つことがある(summer-blendで確認済み)ため、存在すればこれも
blend_componentsのfarm/variety/processing_methodに反映する。
比率(例:「1：1：1」)はpercentageスキーマに合わせ、合計に対する割合(%)に
換算する(1:1:1なら各33.3%)。ブレンド商品は単一のorigin_country/farm_name等を
持たない(複数産地の配合のため)ので、トップレベルのこれらの項目はNoneのままにする。

【価格・重量: バリアントの選び方について】
実データ確認済み: 各商品は「サイズ」(50g/100g/200g/500g/1kg)×「挽き目」
(豆のまま/各種挽き目)の組み合わせバリアントを持つが、挽き目は価格に影響
しない(同一サイズなら同額)。またgrams(Shopify標準の重量フィールド)は
全バリアントで0(未設定)。そのためscrape_fuglen.pyのpick_canonical_variant()
と同じ考え方で、option1(サイズ表記文字列)から重量をパースし、在庫のある
(available=true)バリアントの中で最小サイズのものを代表バリアントとして
price/weight_gに採用する(在庫が無ければ全バリアントの中から最小サイズを
採用)。挽き目オプションはどれを選んでも価格・重量が同じことを実データで
確認済みのため、代表バリアント選定に挽き目は考慮しない。

【在庫状態について】
実データ確認済み: 33件中13件が全バリアントavailable=falseで完売中。部分的な
サイズ欠品(一部サイズのみ完売)は0件だった。サイト側に「終売」等の恒久的な
販売終了を示す明示的な表記が無いため、全滅=一時的に品切れとして扱う
(終売と断定する根拠が無い)。

robots.txt確認済み(2026-08時点): woodberrycoffee.com/robots.txtはStandard
Shopify robots.txt。/products/・/collections/はUser-agent: *でAllow。
/cart・/checkout・/account等の非公開/取引系のみDisallow(対象パスとは無関係)。

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
    "name": "WOODBERRY COFFEE",
    "url": "https://woodberrycoffee.com/",
    "platform": "Shopify",
    # 複数店舗のため店舗単位の詳細住所はlocations参照。PHILOCOFFEA等の複数拠点
    # 店舗と同じく、トップレベルはプレフェクチャーレベルの表記に留める
    "address": "東京都",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-08確認。標準的なShopify robots.txtで/products/・/collections/は"
                          "User-agent: *に対しAllow。/cart・/checkout・/account等の非公開/取引系のみDisallow)",
}

BASE_URL = "https://woodberrycoffee.com"
COFFEE_BEANS_COLLECTION_HANDLE = "coffee_beans"
LOCATION_PAGE_URL = f"{BASE_URL}/pages/location"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

DETAIL_LINE_PATTERN = re.compile(r"^【(.+?)】(.*)$")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")
SIZE_TO_GRAMS_PATTERN = re.compile(r"^([\d.]+)\s*(kg|g)$", re.IGNORECASE)
BLEND_COMPONENT_LINE_PATTERN = re.compile(r"^(.+?)\s*([\d.]+)\s*[%％]$")
RATIO_ONLY_PATTERN = re.compile(r"^[\d.]+(?:[:：][\d.]+)+$")


def fetch_json(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_size_to_grams(size_text: str) -> int | None:
    if not size_text:
        return None
    text = unicodedata.normalize("NFKC", size_text).strip()
    m = SIZE_TO_GRAMS_PATTERN.match(text)
    if not m:
        return None
    value = float(m.group(1))
    if m.group(2).lower() == "kg":
        value *= 1000
    return int(value)


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


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """在庫のあるバリアントの中から最小サイズのものを選ぶ(在庫が無ければ全体から)。
    理由はモジュールdocstring参照。"""
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants

    def sort_key(v):
        grams = parse_size_to_grams(v.get("option1") or "")
        return grams if grams is not None else float("inf")

    return min(pool, key=sort_key)


def parse_detail_fields(body_html: str) -> dict:
    """body_html末尾の「商品詳細」ブロック(【ラベル】値の行の並び)を汎用的に
    キーバリュー抽出する。複数行にわたる値(【配合比率】等)は、次の【ラベル】行
    か、コロンを含む行(英語版セクションの開始)に達するまで蓄積する。
    理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(body_html, "html.parser")
    midashi = soup.find(class_="item-midashi")
    if not midashi:
        return {}
    detail_p = midashi.find_next("p")
    if not detail_p:
        return {}

    for br in detail_p.find_all("br"):
        br.replace_with("\n")
    lines = [line.strip() for line in detail_p.get_text().split("\n")]

    fields: dict[str, str] = {}
    current_label = None
    current_values: list[str] = []

    def flush():
        if current_label is not None:
            fields[current_label] = "\n".join(v for v in current_values if v).strip()

    for line in lines:
        if not line:
            continue
        m = DETAIL_LINE_PATTERN.match(line)
        if m:
            flush()
            current_label = m.group(1)
            current_values = [m.group(2)] if m.group(2) else []
            continue
        if current_label is not None and "：" not in line and ":" not in line:
            current_values.append(line)
        else:
            flush()
            current_label = None
            current_values = []
    flush()
    return fields


def split_slash_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split("/")]


def parse_blend_components(fields: dict) -> list[dict]:
    ratio_raw = fields.get("配合比率")
    if not ratio_raw:
        return []

    normalized_ratio = unicodedata.normalize("NFKC", ratio_raw.strip())

    # パターンB: 「1：1：1」のような比率のみの1行。【生産国】のスラッシュ区切り
    # リストと順序で対応させ、【農園】【品種】【プロセス】も存在すれば同様に対応させる。
    if "\n" not in ratio_raw.strip() and RATIO_ONLY_PATTERN.match(normalized_ratio):
        countries = split_slash_list(fields.get("生産国"))
        ratios = [float(x) for x in normalized_ratio.split(":")]
        if not countries or len(countries) != len(ratios):
            return []
        total = sum(ratios)
        farms = split_slash_list(fields.get("農園"))
        varieties = split_slash_list(fields.get("品種"))
        processes = split_slash_list(fields.get("プロセス"))

        def at(lst, i):
            return lst[i] if lst and i < len(lst) else None

        components = []
        for i, country_raw in enumerate(countries):
            process_raw = at(processes, i)
            components.append({
                "origin_country": detect_country_name(country_raw) or country_raw,
                "percentage": round(ratios[i] / total * 100, 1),
                "farm": at(farms, i),
                "variety": at(varieties, i),
                "processing_method": normalize_processing_method(process_raw) if process_raw else None,
            })
        return components

    # パターンA: 「インド 25％」のように国名+割合が複数行で並ぶ形式
    components = []
    for line in ratio_raw.split("\n"):
        line = unicodedata.normalize("NFKC", line.strip())
        if not line:
            continue
        m = BLEND_COMPONENT_LINE_PATTERN.match(line)
        if not m:
            continue
        country = detect_country_name(m.group(1).strip())
        components.append({
            "origin_country": country or m.group(1).strip(),
            "percentage": float(m.group(2)) if "." in m.group(2) else int(m.group(2)),
        })
    return components


def is_decaf(title: str) -> bool:
    return "デカフェ" in title


def build_record(product: dict) -> dict:
    raw_name = product["title"]
    parsed = parse_product(raw_name)
    is_blend = parsed["category"] == "ブレンド"

    fields = parse_detail_fields(product.get("body_html") or "")
    decaf = is_decaf(raw_name)

    farm_name = fields.get("農園") or fields.get("組合")
    processing_raw = fields.get("プロセス")
    processing_method = None
    decaf_process = None
    if processing_raw:
        if decaf:
            decaf_process = processing_raw
        else:
            processing_method = normalize_processing_method(processing_raw)

    altitude_min, altitude_max = (None, None) if is_blend else parse_altitude(fields.get("標高"))
    blend_components = parse_blend_components(fields) if is_blend else []

    origin_country = None
    if not is_blend and fields.get("生産国"):
        origin_country = detect_country_name(fields["生産国"]) or fields["生産国"]

    variant = pick_canonical_variant(product.get("variants", []))
    price = int(float(variant["price"])) if variant else None
    weight_g = parse_size_to_grams(variant.get("option1") or "") if variant else None
    all_out_of_stock = bool(product.get("variants")) and not any(v.get("available") for v in product["variants"])
    stock_status = "一時的に品切れ" if all_out_of_stock else "販売中"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": origin_country,
        "origin_source": "product_description" if origin_country else None,
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(3段階表記のためroast_hintに保持)
        "roast_hint": fields.get("焙煎度"),
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_name": None if is_blend else farm_name,
        "producer_name": None if is_blend else fields.get("生産者"),
        "region_detail": None if is_blend else fields.get("地域"),
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "variety": None if is_blend else fields.get("品種"),
        "decaf_process": decaf_process,
        "blend_components": blend_components,
        "flavor_notes": "、".join(product.get("tags", [])) or None,
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    page = 1
    while True:
        url = f"{BASE_URL}/collections/{COFFEE_BEANS_COLLECTION_HANDLE}/products.json?limit=250&page={page}"
        data = fetch_json(url)
        products = data.get("products", [])
        if not products:
            break
        for product in products:
            records.append(build_record(product))
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


# --- 店舗拠点一覧(/pages/location) -------------------------------------------
# 理由はモジュールdocstring参照。Shopifyのpages.jsonはこのページのbody_htmlが
# 空(テーマのセクション機能で描画されているため)なので、レンダリング済みHTML
# ページを直接fetchする。

LOCATION_NAME_PREFIXES = ["WOODBERRY COFFEE ", "WOODBERRY "]
# 荻窪店は「現在全てのコーヒーはここで焙煎しています」と明記されている実際の
# 焙煎拠点のため、is_headquartersはここに立てる(用賀本店は「本店」を名乗るが
# 焙煎機は既に移設済みで、現在の実質的な拠点ではない)
ROASTERY_LABEL = "荻窪店"


def location_label(store_name: str) -> str:
    for prefix in LOCATION_NAME_PREFIXES:
        if store_name.startswith(prefix):
            return store_name[len(prefix):].strip()
    return store_name.strip()


def scrape_locations() -> list[dict]:
    resp = requests.get(LOCATION_PAGE_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    locations = []
    for block in soup.select("image-with-text"):
        name_el = block.select_one("p.h3")
        if not name_el:
            continue
        store_name = name_el.get_text(strip=True)
        label = location_label(store_name)

        info_h6s = block.select("h6")
        for h6 in info_h6s:
            for br in h6.find_all("br"):
                br.replace_with("\n")
        info_text = "\n".join(h6.get_text() for h6 in info_h6s)

        tel_match = re.search(r"電話番号[:：]\s*([\d\-]+)", info_text)
        address_match = re.search(r"住所[:：]\s*\n?([^\n]+)", info_text)
        hours_match = re.search(r"営業時間[:：]\s*\n?([^\n]+)", info_text)

        address = address_match.group(1).strip() if address_match else None
        prefecture = None
        if address:
            pref_match = re.match(r"^(東京都|神奈川県|埼玉県|千葉県)", address)
            prefecture = pref_match.group(1) if pref_match else None

        locations.append({
            "label": label,
            "address": address,
            "prefecture": prefecture,
            "hours": hours_match.group(1).strip() if hours_match else None,
            "tel": tel_match.group(1) if tel_match else None,
            "is_headquarters": label == ROASTERY_LABEL,
            "map_query": f"WOODBERRY {label}",
        })
    return locations


def main():
    records = scrape_all_products()
    locations = scrape_locations()

    shop_info = dict(SHOP_INFO)
    shop_info["locations"] = locations

    output = {
        "shop": shop_info,
        "products": records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_woodberry.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件・拠点{len(locations)}件を data_woodberry.json に出力しました")


if __name__ == "__main__":
    main()
