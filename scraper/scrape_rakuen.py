# -*- coding: utf-8 -*-
"""
scrape_rakuen.py

楽園(自家焙煎・珈琲豆専門店　楽園、rakuen-beans.crayonsite.net)の商品情報を
取得する。神奈川県川崎市宮前区の単独店舗。

【crayon(クレヨン)プラットフォームについて】
実データ確認済み(2026-08時点): フッターに"powered by crayon（クレヨン）"の
記載があり、静的アセットが crayonimg.e-shops.jp / crayoncal.e-shops.jp
配下に置かれている。今回初めて対応するプラットフォームのため、
explore_candidate.pyのPLATFORM_FINGERPRINTSにも追加している。

【個別商品ページを持たない点について】
豆コネクト(scrape_mameconnect.py)と同様、/p/2/(取り扱い珈琲豆ページ)に
「ストレート」「ブレンド」の2見出しの下、それぞれ<p>タグ内に<br>区切りで
1行1商品の価格表が埋め込まれているのみで、個別の商品詳細ページ・カート機能は
存在しない。よってproduct_urlは常にnullとし、aggregate_shops.py側の
build_product_id()の`{店舗名}:{商品名}`フォールバックに乗る(表内の商品名
10件が重複なく一意であることを実データで確認済み)。

【全角/半角表記ゆれについて】
価格行は「ブラジル(そのときにお値段と味がマッチしたもの)　　200g￥８００」の
ように、価格の桁だけ全角数字だったり(￥８００)、他の行では半角数字＋カンマ
(￥1,200)だったりと表記が統一されていない。行ごとにunicodedata.normalize
("NFKC", line)をかけることで、全角数字・全角カッコ・全角スペース・全角￥を
一括で半角に正規化してから正規表現でパースする(生豆コーヒー特有の産地名等の
漢字仮名はNFKCの対象外なので情報が失われる心配はない)。

【「ブレンド」判定の補強について】
「モカスペシャル」「モカロワイヤル」は商品名に「ブレンド」の文字を含まない
(coffee_parser.pyのBLEND_KEYWORDSでは検出できない)が、サイト側の
<h2>ブレンド</h2>見出し配下に掲載されている実データを確認済みのため、
セクション見出しでcategoryを補強する。

【焙煎について】
ページ本文に「この焙煎機を遣って　ご注文いただいてから焙煎します　苦味
まろやか　お好きなようにいたします」とあり、注文時に焙煎の濃淡を相談できる
方式であることが明記されているため、roast_selectable=Trueとする。

robots.txt確認済み(2026年8月時点): https://rakuen-beans.crayonsite.net/robots.txt
はHTTP 404(crayon標準のカスタム「ページが見つかりません」ページが返るのみで、
robots.txt自体が存在しない)。Disallow指定が無いため全面許可とみなす。
"""

import json
import re
import unicodedata
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "楽園",
    "url": "https://rakuen-beans.crayonsite.net/",
    "platform": "crayon(クレヨン)",
    "address": "神奈川県川崎市宮前区平2-1-5",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。robots.txt自体が存在しない[HTTP 404、"
                          "crayon標準のカスタム404ページが返るのみ]。Disallow指定なし)",
}

PRODUCT_LIST_URL = "https://rakuen-beans.crayonsite.net/p/2/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 商品名に「ブレンド」を含まないがブレンド見出し配下に掲載されている商品が
# あるため(「モカスペシャル」「モカロワイヤル」、実データ確認済み)、
# セクション見出しでcategoryを補強する。
SECTION_TO_CATEGORY = {"ブレンド": "ブレンド"}

# NFKC正規化後(全角数字・全角カッコ・全角￥→半角)の行を想定したパターン。
# 例:「ブラジル(そのときにお値段と味がマッチしたもの)  200g¥800」
LINE_PATTERN = re.compile(r"^(?P<name>[^(]+?)\s*(?:\((?P<note>[^)]*)\))?\s*(?P<weight>\d+)g¥(?P<price>[\d,]+)\s*$")


def fetch_lineup_rows() -> list[dict]:
    resp = requests.get(PRODUCT_LIST_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = []
    for block in soup.select("div.text_area"):
        h2 = block.find("h2")
        p = block.find("p")
        if not h2 or not p:
            continue
        section_name = h2.get_text(strip=True)
        if section_name not in ("ストレート", "ブレンド"):
            continue

        for br in p.find_all("br"):
            br.replace_with("\n")
        for line in p.get_text().split("\n"):
            normalized = unicodedata.normalize("NFKC", line).strip()
            if not normalized:
                continue
            m = LINE_PATTERN.match(normalized)
            if not m:
                # 「他にも季節等に合わせたスポット商品を販売いたします」「米１０月~４月限定」
                # のような商品行以外の注記は、価格パターンに一致しないため自然に除外される
                continue
            rows.append({
                "name": m.group("name").strip(),
                "note": (m.group("note") or "").strip(),
                "weight_g": int(m.group("weight")),
                "price": int(m.group("price").replace(",", "")),
                "section": section_name,
            })
    return rows


def build_record(row: dict) -> dict:
    parsed = parse_product(row["name"])
    if SECTION_TO_CATEGORY.get(row["section"]) == "ブレンド":
        parsed["category"] = "ブレンド"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": row["name"],
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_selectable": True,  # 「ご注文いただいてから焙煎します」と明記(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],  # 実データではブレンド商品の産地内訳が見つからず未対応
        "flavor_notes": row["note"] or None,  # 括弧内の商品説明文
        "price": row["price"],
        "weight_g": row["weight_g"],
        "stock_status": "販売中",  # サイト上に在庫状態を示す表示が無いため、掲載=販売中として扱う
        "out_of_stock": False,
        "product_url": None,
    }


def scrape_all_products() -> list[dict]:
    rows = fetch_lineup_rows()
    return [build_record(row) for row in rows]


def main():
    records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_rakuen.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_rakuen.json に出力しました")


if __name__ == "__main__":
    main()
