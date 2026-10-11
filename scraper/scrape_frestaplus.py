# -*- coding: utf-8 -*-
"""
scrape_frestaplus.py

フレスタプラス@あらの珈琲(茨城県つくば市並木4-4-2 並木ショッピングセンター1F 105、
公式 https://frestaplus.com/)のコーヒー豆の商品情報を取得する。公式サイトは商品紹介のみで、
カートはYahoo!ショッピングストア(store.shopping.yahoo.co.jp/frestaplus)にあるため、
そのストアの商品一覧・詳細ページから価格と在庫を取得する。

【プラットフォーム】
他のYahoo!ショッピング店舗(scrape_mameyanetshop.py 等)と同様、店舗の商品一覧
(/search.html、2ページ目以降は ?page=1,2,...)の Next.js `__NEXT_DATA__` JSON
(props.initialState.bff.searchResults.items.<ページ番号>[1].content.items)に商品名・価格・URLが
埋め込まれている。robots.txtでは /search.html のクエリなし・page指定は Disallow 対象外。

【対象商品】
実データ確認済み(2026-10時点、全91件): ギフトセット・ドリップバッグ・リキッドアイスコーヒー・
カフェオレベース・フィルター・ドリッパー・カップ・マイスターセット等は除外。
同一銘柄が 100g / 200g(一部 1kg)で別ページに並ぶため、最小重量(100g、100gが無い銘柄は
200g、コピルアック マンデリンは50g)のページだけを代表に採用する。
銘柄名・産地・焙煎度は商品説明(焙煎度/ローストポイント/○○煎り等の記載)から判断した
表(ITEMS)で与える。焙煎度が複数併記・未記載のものは roast_level=None とし、併記は roast_hint に残す。
商品説明に挽き具合オプション(豆のまま/中挽き等)があるが焙煎度の選択肢は無い。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "フレスタプラス@あらの珈琲",
    "url": "https://frestaplus.com/",
    "platform": "Yahoo!ショッピング(自社サイトのカートはYahoo!店 frestaplus)",
    "address": "茨城県つくば市並木4-4-2 並木ショッピングセンター1F 105",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(2026-10確認。User-agent: *は/cgi-bin/・/search.htmlの絞り込みクエリ等のみDisallow。"
                          "本スクレイパーが使う/search.html・?page=N は制限対象外)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/frestaplus"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"
}
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# (ページコード, 整形名, ブレンドか, 産地国, 焙煎度, 焙煎度の補足(roast_hint), 重量g)
ITEMS = [
    ("d-mokha100", "深モカ イルガチェフ", False, "エチオピア", "深煎り", "フルシティロースト", 100),
    ("straw100", "エチオピア ストロベリーモカ", False, "エチオピア", "中煎り", "浅めの中煎り", 100),
    ("cochere100", "エチオピア モカ イルガチェフ アリーチャウオシュド", False, "エチオピア", "浅煎り", "浅めに焙煎", 100),
    ("honey100", "コスタリカ レッドハニー", False, "コスタリカ", "中煎り", None, 100),
    ("sierra100", "コロンビア パシオン・デ・ラ・シエラ 中深煎り", False, "コロンビア", "中深煎り", "深めのシティロースト", 100),
    ("sierrafrench100", "コロンビア パシオン・デ・ラ・シエラ 深煎り", False, "コロンビア", "深煎り", "フレンチロースト", 100),
    ("tora100", "マンデリン", False, "インドネシア", "深煎り", "フレンチロースト", 100),
    ("kenya100", "ケニア レッドマウンテン", False, "ケニア", None, None, 100),
    ("rwanda100", "ルワンダ スカイヒルコプロカ", False, "ルワンダ", None, None, 100),
    ("sigri100", "パプアニューギニア シグリ農園", False, "パプアニューギニア", "中深煎り", "フルシティロースト", 100),
    ("ueue-100", "グアテマラ ロズマラゴ ロズマ農園", False, "グアテマラ", "中深煎り", None, 100),
    ("pantano100-origin", "ブラジル パンタノ農園 ミネラル特別栽培", False, "ブラジル", "中煎り", "ハイロースト", 100),
    ("cajamarcagold100-origin", "ペルー マチュピチュ", False, "ペルー", "深煎り", "フルシティロースト", 100),
    ("hawaiikona100", "ハワイコナコーヒー ハワイアンクイーン農園", False, "アメリカ(ハワイ)", "中深煎り", None, 100),
    ("dcaf100", "deCAFE エチオピア カフェインレスコーヒー", False, "エチオピア", None, None, 100),
    ("copi100", "コピルアック「ジャコウネコのおみやげ」", False, "インドネシア", None, None, 100),
    ("wild-luwak50", "マンデリン・コピルアック(ワイルドルアック)", False, "インドネシア", None, "ハイロースト〜シティロースト", 50),
    ("fresta-blend100", "オリジナルブレンド NO1", True, None, "中深煎り", "浅めの中深煎り/深めの中深煎り", 100),
    ("meister-100", "オリジナルブレンド NO2", True, None, "中深煎り", "シティロースト", 100),
    ("french-blend100", "オリジナルブレンド NO3 フレンチ", True, None, "深煎り", "フレンチロースト", 100),
    ("exp100", "エスプレッソ ブレンド", True, None, None, "深煎り/中深煎り/中煎り", 100),
    ("uncle-100", "オリジナルブレンド アンクルケニア", True, None, None, "中深煎り+深煎り", 100),
    ("ice-blend200", "アイスコーヒー用ブレンド", True, None, "深煎り", "フレンチロースト", 200),
    ("sukkiri-200", "アイスコーヒー用ブレンド スッキリ", True, None, None, None, 200),
    ("sweetm200", "オリジナルブレンド スイートミックス", True, None, "中深煎り", "シティロースト", 200),
]


def fetch_list_items() -> dict[str, dict]:
    by_code: dict[str, dict] = {}
    for page in range(0, 20):
        url = f"{BASE_URL}/search.html" + (f"?page={page}" if page else "")
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
            data = json.loads(m.group(1))
            page_items = list(data["props"]["initialState"]["bff"]["searchResults"]["items"].values())[0][1]["content"]["items"]
        except Exception:
            break
        if not page_items:
            break
        for it in page_items:
            code = (it.get("url") or "").split("?")[0].rsplit("/", 1)[-1].replace(".html", "")
            by_code[code] = it
    return by_code


def fetch_detail(url: str) -> dict:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
        return {"in_stock": True, "notes": None}
    text = resp.content.decode("utf-8", "replace")
    dm = re.search(r'og:description" content="([^"]*)"', text)
    notes = None
    if dm:
        desc = html.unescape(dm.group(1)).replace("<br>", "\n")
        lines = [l.strip() for l in desc.split("\n") if l.strip()]
        lines = [l for l in lines if not re.match(r"^(内容量|焙煎度[/／]|[〇○●■◇・☆★])", l)]
        notes = " ".join(lines)[:300] or None
    in_stock = "schema.org/OutOfStock" not in text and "schema.org/SoldOut" not in text
    return {"in_stock": in_stock, "notes": notes}


def build_record(code, name, is_blend, origin, roast, roast_hint, weight, item) -> dict:
    url = (item.get("url") or "").split("?")[0]
    detail = fetch_detail(url)

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name" if origin and origin.split("(")[0] in name else "description"
        parsed = apply_category_hint_fallback(parsed, name)

    out = not detail["in_stock"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_selectable": False,  # 挽き具合のみ選択可、焙煎度は商品ごとに固定
        "roast_hint": roast_hint,
        "flavor_notes": detail["notes"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    by_code = fetch_list_items()
    print(f"[info] 一覧 {len(by_code)}件取得")
    records = []
    for code, name, is_blend, origin, roast, roast_hint, weight in ITEMS:
        item = by_code.get(code)
        if not item:
            print(f"[warn] 一覧に無い: {code}")
            continue
        records.append(build_record(code, name, is_blend, origin, roast, roast_hint, weight, item))
    return records


def main():
    records = scrape_all_products()
    with open("data_frestaplus.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_frestaplus.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_level"], r["stock_status"])


if __name__ == "__main__":
    main()
