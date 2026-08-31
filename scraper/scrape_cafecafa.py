# -*- coding: utf-8 -*-
"""
scrape_cafecafa.py

CafeCafa(cafecafa.com、神奈川県茅ヶ崎市、2000年創業)の商品情報を取得する。

【価格を一切取得しない理由(このショップ固有の設計判断)】
実データ確認済み(2026-08時点): 注文ページ(/mart/beans.html)の商品名・価格は
すべて画像(PNG)としてページに埋め込まれており、テキスト・alt属性のいずれにも
含まれていない(例: web20.pngという1枚の画像に「グァテマラ・アンティグァ
Retana」という商品名と「200g ¥2,400/400g ¥3,600」等の価格が描画されている)。
そのため通常のrequests+BeautifulSoupによるテキスト抽出では商品名も価格も
一切取得できない。さらに/mart/beans.htmlの価格画像の並びと/coffees.htmlの
商品説明は1対1で綺麗に対応しておらず(例:「香味深い珈琲」区分は価格ページで
6商品分の画像があるが、説明ページでは4商品しか名前が記載されていない)、
機械的な突き合わせもできない。ユーザーとの協議の結果、OCRには踏み込まず、
/coffees.html(商品説明ページ)のみを情報源とし、price/price_min/price_max/
weight_gは常にnullのまま、product_urlも持たせない方針とした
(/mart/beans.htmlはそもそもfetchしない)。

【商品情報の抽出元(/coffees.html)】
「珈琲豆の選び方」ページ。3つの区分(爽やかな珈琲＝id111／香味深い珈琲＝id222／
濃厚な珈琲＝id333)の見出し画像(bar1/bar2/bar3.png)アンカーを境に、各区分の
紹介文(h3)のあとに商品が<h2><em>商品名</em></h2><h3><em>ストレート/ブレンド
</em>説明文...</h3>という順で並ぶ。区分名はcategory_hintに保持する。

【category(ストレート/ブレンド)を商品名からではなくh3内の型ラベルで決める理由】
当店のブレンド銘柄(「東海岸」「湘南」「えぼし」「フレンチ」「ショコラ」)は
いずれも商品名に「ブレンド」という語を含まないため、coffee_parser.parse_product()
のBLEND_KEYWORDS判定では検出できない。サイト自身がh3内の最初の<em>で
「ストレート」「ブレンド」を明記しているため、これを一次情報として優先する。

【roast_levelを常にnullで上書きする理由】
coffee_parser.ROAST_KEYWORDSはスペシャルティコーヒー業界標準の8段階表記
(ライト〜イタリアン)に対する検出用で、「フレンチ」もその1つ(フレンチロースト)
として登録されている。当店のブレンド銘柄名「フレンチ」がこのキーワードと
偶然一致してしまい、parse_product()にそのまま任せると「フレンチロースト」
という構造化された焙煎度クレームを作ってしまう(サイト本文は「深煎り」という
一般的な表現のみで、8段階表記のどこに位置するかは明記していない)。実在しない
精度の情報を作らないという方針により、roast_levelは常にnullとし、本文中の
「深煎り」等の表現はflavor_notes(原文ママ)としてのみ保持する。

【同名商品(エチオピア・ベンサ Shentawane)が2回登場する点について】
実データ確認済み: 「香味深い珈琲」区分と「濃厚な珈琲」区分の両方に同じ
「エチオピア・ベンサ Shentawane」が別の焙煎・別の説明文で掲載されている
(サイト本文にも「同じ豆でも印象は全く異なります」と明記されており、店側も
意図的に別商品として扱っている)。product_urlを持たないためaggregate_shops.py
のbuild_product_id()は{店舗名}:{商品名}にフォールバックし、同名のままだと
IDが衝突してしまう。disambiguate_raw_name()で、2回目の登場時にサイト本文が
明記する語("深煎り")、無ければ区分名を商品名末尾に括弧書きで付与し一意にする
(いずれもサイト自身の文言をそのまま使い、架空の語を創作しない)。

robots.txt確認済み(2026-08時点): www.cafecafa.com/robots.txtはHTTP 404
(ファイル自体が存在しない)。Disallow指定が無いため全面許可とみなす。

【文字化け対策について】
実データ確認済み(実際のワークフロー実行で発覚): www.cafecafa.com/coffees.html
のHTTPレスポンスヘッダーはContent-Type: text/html(charsetパラメータ無し)。
ページ本文の<meta charset="utf-8">とは無関係に、requestsはcharset未指定時に
ISO-8859-1へフォールバックして resp.text をデコードしてしまい、日本語が
すべて文字化けする(scrape_events_ccf.pyで発見済みの問題と同種)。resp.text
ではなく resp.content(生バイト列)をBeautifulSoupに渡し、ページ自身のmeta
charsetタグから検出させることで回避する。
"""

import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "CafeCafa",
    "url": "https://www.cafecafa.com/",
    "platform": "独自HTML(静的サイト、注文はmart.cgiという独自CGIフォーム。標準的なECプラットフォームではない)",
    "address": "神奈川県茅ヶ崎市東海岸北3-15-24",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。robots.txt自体が存在しない[HTTP 404]。Disallow指定が無いため全面許可とみなす)",
}

COFFEES_URL = "https://www.cafecafa.com/coffees.html"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

CATEGORY_LABELS = {
    "111": "爽やかな珈琲",
    "222": "香味深い珈琲",
    "333": "濃厚な珈琲",
}


def disambiguate_raw_name(name: str, description: str, category_label: str, seen_names: set[str]) -> str:
    if name not in seen_names:
        seen_names.add(name)
        return name
    suffix = "深煎り" if "深煎り" in description else category_label
    candidate = f"{name}({suffix})"
    seen_names.add(candidate)
    return candidate


def fetch_product_blocks() -> list[dict]:
    """/coffees.htmlをドキュメント順に走査し、各商品の(商品名, 型ラベル, 説明文,
    区分名)を抽出する。"""
    resp = requests.get(COFFEES_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    # 理由はモジュールdocstring参照(charset未指定レスポンスのISO-8859-1誤判定対策)
    soup = BeautifulSoup(resp.content, "html.parser")

    contents = soup.select_one("#contents")
    if not contents:
        return []

    blocks = []
    current_category = None
    expect_category_intro = False
    pending_name = None

    for tag in contents.find_all(["p", "h1", "h2", "h3"]):
        if tag.name == "p" and "btn03" in (tag.get("class") or []):
            current_category = CATEGORY_LABELS.get(tag.get("id"))
            expect_category_intro = True
            continue
        if tag.name == "h1":
            continue
        if tag.name == "h3" and expect_category_intro:
            # 区分の紹介文(商品ではない)
            expect_category_intro = False
            continue
        if tag.name == "h3" and current_category is None:
            # 区分アンカーより前にあるページ全体の分類説明文
            continue
        if tag.name == "h2":
            em = tag.find("em")
            pending_name = (em.get_text(strip=True) if em else tag.get_text(strip=True))
            continue
        if tag.name == "h3" and pending_name:
            em = tag.find("em")
            type_label = em.get_text(strip=True) if em else None
            full_text = tag.get_text(separator=" ", strip=True)
            description = full_text
            if type_label and description.startswith(type_label):
                description = description[len(type_label):].strip()
            description = re.sub(r"\s+", " ", description).strip()
            blocks.append({
                "name": pending_name,
                "type_label": type_label,
                "description": description,
                "category_label": current_category,
            })
            pending_name = None

    return blocks


def build_record(block: dict, seen_names: set[str]) -> dict:
    raw_name = disambiguate_raw_name(block["name"], block["description"], block["category_label"], seen_names)

    parsed = parse_product(raw_name)
    parsed = apply_category_hint_fallback(parsed, block["category_label"])

    # サイトが明示するストレート/ブレンドの型ラベルを一次情報として優先する
    # (ブレンド銘柄名に「ブレンド」という語を含まないため商品名からの推測は不可)
    if block["type_label"] in ("ストレート", "ブレンド"):
        parsed["category"] = block["type_label"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(「フレンチ」ブレンド名との偶然一致対策)
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "category_hint": block["category_label"],
        "blend_components": [],
        "flavor_notes": block["description"] or None,
        "price": None,
        "price_min": None,
        "price_max": None,
        "price_note": "価格は購入ページに画像として掲載されており自動取得できません。"
                      "最新価格はCafeCafa公式サイトのOrderページでご確認ください",
        "weight_g": None,
        "stock_status": "販売中",  # サイト上に在庫状態を示す表示が無いため、掲載=販売中として扱う
        "out_of_stock": False,
        "product_url": None,
    }


def scrape_all_products() -> list[dict]:
    blocks = fetch_product_blocks()
    seen_names: set[str] = set()
    return [build_record(block, seen_names) for block in blocks]


def main():
    records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_cafecafa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_cafecafa.json に出力しました")


if __name__ == "__main__":
    main()
