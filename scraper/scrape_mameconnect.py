# -*- coding: utf-8 -*-
"""
scrape_mameconnect.py

豆コネクト(mame-connect.com、株式会社南部ハウス 珈琲事業部運営)の商品情報を
取得する。神奈川県川崎市中原区(武蔵小杉)の単独店舗。

【個別商品ページを持たない静的1ページサイトである点について】
実データ確認済み(2026-08時点): mame-connect.comはWordPress製の1ページサイト
(mame-connect.com→www.mame-connect.comへ301リダイレクト)で、ホームページ内の
「#coffee」セクションに「主な取扱珈琲」という1つの表(品名/製法/地域・農園/
おすすめ焙煎/テースト)が埋め込まれているのみ。個別の商品詳細ページ・カート
機能は存在しない(生豆を選んで店頭で焙煎してもらう量り売り方式のため)。
よって他店舗のような一覧ページ→詳細ページというクロール構造は取らず、
ホームページ1回のfetchのみで完結する。

【価格を常にnullとする理由】
上記の通り量り売り・都度相談の販売形態のため、サイト上に価格が一切掲載
されていない。price/price_min/price_maxはいずれも常にnullとし、price_noteに
案内文を設定する(存在しない情報を推測・創作しないという方針を維持しつつ、
UI側で「価格未確認(=取得失敗)」と区別できるようにする)。

【商品URLを持たない点について】
個別ページが無いため、product_urlは常にnull。aggregate_shops.py側の
build_product_id()がproduct_url無しの場合`{店舗名}:{商品名}`にフォール
バックする既存の仕組みにそのまま乗る(表内の品名6件が重複なく一意であることを
実データで確認済み)。

【焙煎について】
ページ本文に「生豆から選ぶ」「お選びいただいた豆が一番おいしく味わえる焙煎
状態をご提供いたします」とあり、注文時に焙煎度合いを相談する方式であることが
明記されているため、roast_selectable=Trueとする。表の「おすすめ焙煎」列は
店舗が推奨する参考値としてroast_hintに保持する(roast_levelとしては扱わない)。

robots.txt確認済み(2026年8月時点): www.mame-connect.com/robots.txtは
/cms/wp-admin/のみ制限(admin-ajax.phpは許可)。コンテンツ全般への制限なし。
"""

import json
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, normalize_processing_method

SHOP_INFO = {
    "name": "豆コネクト",
    "url": "https://www.mame-connect.com/",
    "platform": "WordPress(静的1ページ。個別商品ページ・カート機能なし)",
    "address": "神奈川県川崎市中原区小杉町2-294-6 エスカリエ1F",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。mame-connect.com→www.mame-connect.comへ301リダイレクト。"
                          "robots.txtは/cms/wp-admin/のみ制限、コンテンツ全般への制限なし)",
}

BASE_URL = "https://www.mame-connect.com/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

PRICE_NOTE = "価格は店舗にお問い合わせください(生豆から選び、注文時に焙煎してもらう量り売り方式のため、価格は一律に掲載されていません)"


def fetch_lineup_rows() -> list[dict]:
    """ホームページ内「#coffee」セクションの表(品名/製法/地域・農園/おすすめ焙煎/
    テースト)を1行=1商品としてパースする。"""
    resp = requests.get(BASE_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    section = soup.select_one("section#coffee")
    if not section:
        return []
    table = section.select_one("table")
    if not table:
        return []

    rows = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        name = cells[0].get_text(strip=True)
        if not name:
            continue
        rows.append({
            "name": name,
            "processing": cells[1].get_text(strip=True),
            "region": cells[2].get_text(strip=True),
            "roast_hint": cells[3].get_text(strip=True),
            "taste": cells[4].get_text(strip=True),
        })
    return rows


def build_record(row: dict) -> dict:
    parsed = parse_product(row["name"])
    parsed = apply_category_hint_fallback(parsed, row["region"])

    # 「製法」列は商品名からの推測より確実な一次情報として優先的に反映する
    if row["processing"]:
        parsed["processing_method"] = normalize_processing_method(row["processing"])

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
        "roast_hint": row["roast_hint"] or None,  # 表の「おすすめ焙煎」列(参考表示)
        "roast_selectable": True,  # 「生豆から選ぶ」「ご注文いただいてから焙煎します」と明記(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": row["region"] or None,
        "blend_components": [],  # 実データではブレンド商品の産地内訳が見つからず未対応
        "flavor_notes": row["taste"] or None,  # 表の「テースト」列
        "price": None,
        "price_min": None,
        "price_max": None,
        "price_note": PRICE_NOTE,
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

    with open("data_mameconnect.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_mameconnect.json に出力しました")


if __name__ == "__main__":
    main()
