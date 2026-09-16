# -*- coding: utf-8 -*-
"""
scrape_majyacoffee.py

coffee shop Majya(Majya WEBSHOP、coffeeshopmajya.com、沖縄県宮古島市平良西里448)の
商品情報を取得する。Jimdo(独自ショップ機能)。本プロジェクトで初めて扱う
プラットフォームのため、既存テンプレートを流用せず個別に実装している。

【住所について】
候補リストでは第三者情報由来として要確認とされていたが、公式サイト自身の
利用規約ページ(https://www.coffeeshopmajya.com/j/shop/terms、実データ確認済み
2026-09時点)の「お問い合わせ窓口」欄に「住所：沖縄県宮古島市平良西里448 /
代表　前泊　究」、ページ末尾の店舗情報欄にも「〒906-0012 沖縄県宮古島市平良
西里448」と明記されており、一次情報(公式サイト自身)で確認できたため候補リストの
住所(字を含む表記)をそのまま採用する。

【robots.txtについて】
実データ確認済み(2026-09時点): `Disallow: /j/`が指定されており、利用規約・
特定商取引法ページ等`/j/`配下は本スクレイパーでは取得しない(上記の住所確認は
別途の一度限りの人力調査であり、本スクレイパーの定期実行対象には含めない)。
ホームページ("/")自体は`/app/`・`/j/`のいずれにも該当せず許可されており、
商品情報はホームページに直接埋め込まれているため、ホームページ1回の取得のみで
全商品を取得できる。Crawl-Delay: 5が指定されているが、リクエストが1回のみ
のため実質的に問題にならない。

【商品構成について】
実データ確認済み: ホームページに3つのJimdoショップ商品モジュールが直接
埋め込まれている。
  1. 自家焙煎お試しの３種類(3種の少量サンプルセット、産地の個別内訳は
     商品名からは特定できない詰め合わせ) - 除外
  2. 本格自家焙煎のコーヒー豆 - 対象。1つのJimdo商品に、5銘柄(産地)×
     2挽き方(豆/粉)=10バリアントとして登録されている(実データ確認済み)。
     ミチュ(エチオピア)・ボンジャルディン農園(ブラジル)・ラス・ブリサス農園
     (グアテマラ)・スウィートベリーSUP(コロンビア)・マンデリンG1アチェ
     (インドネシア)の5銘柄。銘柄ごとに分割し、「豆」バリアントを代表として
     採用する(価格は豆/粉で同一)。
  3. カフェオレベース各種　沖縄県内向け(リキッドのカフェオレベース、豆ではない) - 除外

【価格について】
実データ確認済み: 商品説明文(自由記述テキスト)に記載の価格は更新が追いついて
おらず、実際に選択・購入できるバリアントのセレクトボックス(data-params属性の
price)の方が最新の実売価格だった(例:「ミチュ」は説明文では￥1,660と表記され
ているが、バリアントの実売価格は￥1,520)。そのため価格は説明文からではなく、
構造化されたバリアントデータから取得する。

【産地国の取得について】
実データ確認済み: バリアントの選択肢テキスト自体には産地国名が含まれず
(例:「（豆）ミチュ　100g　￥1,520」)、産地国は商品説明文の段落
「ミチュ　(エチオピア)　中浅煎り」のような自由記述にしかない(<p>タグの
入れ子構造も銘柄によって微妙に異なる。実データ確認済み: 「ミチュ」は
2つの<span>に分かれているが、「ボンジャルディン農園」等は銘柄名が生テキスト
で<span>に囲まれていない)。そのため<p>タグ単位でHTMLタグを除去してから
プレーンテキストとして正規表現でパースする。銘柄名をキーに、説明文から
抽出した(産地国, 焙煎度ヒント)をバリアントデータにマージする。

【product_urlについて】
実データ確認済み: 5銘柄はいずれも同一のJimdo商品ページ(productId
m08138b628fc8822f)のバリアント選択(JS制御のセレクトボックス)であり、Jimdoには
Shopifyの`?variant=`のような銘柄ごとに実在する個別URLが存在しない。同一URLを
複数レコードに使うとaggregate_shops.py側でID衝突が起きるため、この商品の
レコードはproduct_urlをNoneとし、build_product_id()のフォールバック
(shop_name:raw_name、raw_nameには銘柄名を含むため一意)に委ねる。
"""

import html
import json
import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "coffee shop Majya",
    "url": "https://www.coffeeshopmajya.com/",
    "platform": "Jimdo",
    "address": "沖縄県宮古島市平良字西里448",
    "prefecture": "沖縄県",
    "robots_txt_status": "実質許可(2026-09確認。/app/と/j/がDisallowだが、商品情報が"
                          "埋め込まれたホームページ('/')自体はいずれにも該当せず許可)",
}

BASE_URL = "https://www.coffeeshopmajya.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はdocstring参照(サンプルセット・リキッド商品は非対象)
NON_BEAN_PRODUCT_KEYWORDS = ["お試し", "カフェオレベース"]

FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
NAME_PATTERN = re.compile(r'<h4 class="fn" itemprop="name">([^<]+)</h4>')
DESC_DIV_PATTERN = re.compile(r'class="description"[^>]*>(.*?)</div>', re.DOTALL)
PARAGRAPH_PATTERN = re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL)
DESC_LINE_PATTERN = re.compile(r"^(.+?)[\s　]+[（(]([^）)]+)[）)][\s　]*(.*)$")
OPTION_PATTERN = re.compile(
    r'<option class="j-product__variants__item" value="\d+" data-params="([^"]*)" title="([^"]*)"'
)
VARIANT_TITLE_PATTERN = re.compile(r"^[（(](豆|粉)[）)]\s*(.+?)\s*(\d+)\s*g\s+￥([\d,]+)")


def fetch_homepage_html() -> str:
    resp = requests.get(BASE_URL + "/", headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    return resp.text


def collect_product_blocks(html_text: str) -> list[tuple[str, str]]:
    """(商品名, その商品ブロックのHTML断片)のリストを返す。次の商品名が現れる
    位置までをその商品のブロックとみなす(Jimdoのモジュールは同じページに複数の
    商品が連続して埋め込まれているため)。"""
    names = list(NAME_PATTERN.finditer(html_text))
    blocks = []
    for idx, m in enumerate(names):
        start = m.end()
        end = names[idx + 1].start() if idx + 1 < len(names) else len(html_text)
        blocks.append((m.group(1).strip(), html_text[start:end]))
    return blocks


def parse_description_origins(block_html: str) -> dict[str, dict]:
    """商品説明文から「銘柄名　(産地国)　焙煎度」形式の段落を抽出し、
    銘柄名をキーとした{産地国, 焙煎度ヒント}の辞書を返す(理由はdocstring参照)。"""
    desc_m = DESC_DIV_PATTERN.search(block_html)
    if not desc_m:
        return {}
    origins = {}
    for para in PARAGRAPH_PATTERN.findall(desc_m.group(1)):
        plain = re.sub(r"<[^>]+>", "", para).strip()
        if not plain or plain.startswith("￥") or plain.startswith("￥"):
            continue
        m = DESC_LINE_PATTERN.match(plain)
        if not m:
            continue
        name, paren_content, roast_hint = m.groups()
        country = detect_country_name(paren_content)
        if not country:
            continue  # 括弧内が産地国ではない自由記述の段落(除外)
        origins[name.strip()] = {"country": country, "roast_hint": roast_hint.strip() or None}
    return origins


def parse_variants(block_html: str) -> list[dict]:
    variants = []
    for params_raw, title_raw in OPTION_PATTERN.findall(block_html):
        title = html.unescape(title_raw).translate(FULLWIDTH_DIGITS)
        m = VARIANT_TITLE_PATTERN.search(title)
        if not m:
            continue
        grind, origin_name, weight_g, _price_text = m.groups()
        try:
            params = json.loads(html.unescape(params_raw))
        except json.JSONDecodeError:
            continue
        variants.append({
            "grind": grind,
            "origin_name": origin_name.strip(),
            "weight_g": int(weight_g),
            "price": params.get("price"),
            "available": params.get("availability") == 1,
        })
    return variants


def pick_canonical_variants(variants: list[dict]) -> list[dict]:
    by_origin: dict[str, dict] = {}
    for v in variants:
        existing = by_origin.get(v["origin_name"])
        # 「豆」を優先する(挽かない状態が代表)
        if existing is None or (existing["grind"] != "豆" and v["grind"] == "豆"):
            by_origin[v["origin_name"]] = v
    return list(by_origin.values())


def build_record(variant: dict, origin_info: dict | None) -> dict | None:
    raw_name = f"{variant['origin_name']} {variant['weight_g']}g"
    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": variant["price"],
            "product_url": None,
        }

    if origin_info and origin_info.get("country") and not parsed["origin_country"]:
        parsed["origin_country"] = origin_info["country"]
        parsed["origin_source"] = "product_description"

    # 焙煎度(浅煎り/中浅煎り/中深煎り/深煎り)はROAST_LEVELSの8段階とは粒度が
    # 異なるためroast_levelには入れずroast_hintとして保持する(405coffeeと同じ
    # 方針)。この商品では挽き方(豆/粉)のみが選べ、焙煎度は銘柄ごとに固定
    roast_hint = origin_info.get("roast_hint") if origin_info else None

    parsed = apply_category_hint_fallback(parsed, None)

    if not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "non_bean": True,
            "product_url": None,
        }

    structural_out_of_stock = variant.get("available") is False
    stock_status = detect_stock_status(raw_name, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": variant["price"],
        "weight_g": variant["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        # 理由はdocstring参照(同一Jimdo商品ページの複数バリアントで、実在する
        # 銘柄別URLが無いため、shop_name:raw_nameフォールバックに委ねる)
        "product_url": None,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    html_text = fetch_homepage_html()
    blocks = collect_product_blocks(html_text)

    records = []
    flavored_records = []
    non_bean_records = []
    for name, block in blocks:
        if any(kw in name for kw in NON_BEAN_PRODUCT_KEYWORDS):
            continue

        origins = parse_description_origins(block)
        variants = pick_canonical_variants(parse_variants(block))
        for variant in variants:
            detail = build_record(variant, origins.get(variant["origin_name"]))
            if detail is None:
                continue
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_majyacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_majyacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
