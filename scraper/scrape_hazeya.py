# -*- coding: utf-8 -*-
"""
scrape_hazeya.py

はぜやの豆たち / はぜや珈琲(hazeya.shop-pro.jp、〒093-0033 北海道網走市
駒場北3丁目9-7、自家焙煎豆のオンライン販売)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。

住所は/?mode=skページ(特定商取引法に基づく表記)にて実データ確認済み:
「〒093-0033　北海道　網走市駒場北3丁目9-7」、Tel&Fax 0152-67-9800。
候補リストの住所(南3条東9-7)とは異なるため、店舗自身の一次情報である
この住所を採用する。

robots.txt確認済み(2026-09時点): User-agent: *は/secure/と/cart/のみ
制限。AhrefsBot等SEO系ボットのみ個別にDisallow: /。

【文字コード】EUC-JP(実データ確認済み)。

【商品一覧の取得方法について】
実データ確認済み(2026-09時点、全64件、1ページに全件表示): 一覧ページの
<div class="title">から商品名を取得し、詳細ページのvar Colorme JSON
から価格・バリアントを取得する2段階方式(405coffee.pyと同じ考え方)。

【対象商品の絞り込みについて】
実データ確認済み: 実際の焙煎豆単品(200g、16件)は例外なくタイトルが
「【浅煎り】」「【中煎り】」「【深煎り】」のいずれかで始まる。ギフト
セット・ドリップバッグ・リキッドアイスコーヒー・カフェオレベース・
オリジナルマグカップ・オリジナル豆缶(缶容器のグッズ)・コーノ製ペーパー
フィルターはこの形式と異なるため、「【◯煎り】」始まりのみを対象とする
絞り込みが最も確実。

【重量・挽き方バリアントについて】
実データ確認済み: 全商品が200g固定(重量違いの重複なし)。挽き方(豆の
まま/粉・細/粉・中/粉・粗)は選べるが価格は共通のため、豆のまま
(option1_value="豆")を代表バリアントとして採用する。

【焙煎度について】
実データ確認済み: 商品名の【】内が浅煎り/中煎り/深煎りの3段階表記で、
coffee_parserのROAST_KEYWORDS(カタカナ表記)とは粒度が異なるため
roast_levelには入れずroast_hintとして保持し、roast_selectable=Falseと
する(405coffee.pyと同じ考え方)。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "はぜやの豆たち(はぜや珈琲)",
    "url": "https://hazeya.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道網走市駒場北3丁目9-7",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。User-agent: *は/secure/と/cart/のみ制限。"
                          "AhrefsBot等SEO系ボットのみ個別にDisallow: /)",
}

BASE_URL = "https://hazeya.shop-pro.jp/"
LIST_URL = "https://hazeya.shop-pro.jp/?mode=srh&cid=&keyword=&sort=n"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

ROAST_PREFIX_PATTERN = re.compile(r"^【(浅煎り|中煎り|深煎り)】")
ROAST_HINT_KEYWORDS = ["浅煎り", "中煎り", "深煎り"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def fetch_list_items() -> list[dict]:
    soup = fetch_page(LIST_URL)
    items = []
    # 理由: 一覧ページのアンカータグはclass属性が"thumbnail over"のように2つ
    # 指定されているように見えるが、実データ確認済み: 実際のHTMLソースは
    # class="thumbnail over" href="..." class="over"のようにclass属性自体が
    # 重複しており、html.parserは最後の1つ(class="over")のみを採用する。
    # そのためa.thumbnailセレクタでは0件になる。div.titleを起点にli内の
    # 最初のaタグ(href="?pid=N"形式)を取得する方式にする。
    for li in soup.select("ul > li"):
        title_el = li.select_one("div.title")
        a_el = li.find("a", href=re.compile(r"pid=\d+"))
        if not a_el or not title_el:
            continue
        href = a_el.get("href", "")
        m = re.search(r"pid=(\d+)", href)
        if not m:
            continue
        raw_title = title_el.get_text(" ", strip=True)
        # 理由: 「Ｍａｓｔｅｒ's　ｂｌｅｎｄ」のように全角ラテン文字で入力
        # されている商品名があり(実データ確認済み)、NFKC正規化しないと
        # coffee_parserのBLEND_KEYWORDS判定("blend"は半角のみ想定)等が
        # 効かない。あさみ珈琲豆店と同じ対応。
        title = unicodedata.normalize("NFKC", raw_title)
        title = re.sub(r"\s+", " ", title).strip()
        if not ROAST_PREFIX_PATTERN.search(title):
            continue
        items.append({"pid": m.group(1), "title": title, "url": f"{BASE_URL}?pid={m.group(1)}"})
    return items


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            import json
            data = json.loads(m.group(1))
        except Exception:
            return None
        return data.get("product")
    return None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    whole_bean = [v for v in variants if "豆" == (v.get("option1_value") or "").strip()]
    pool = whole_bean or variants
    return pool[0]


def detect_roast_hint(text: str) -> str | None:
    for kw in ROAST_HINT_KEYWORDS:
        if kw in text:
            return kw
    return None


def build_record(item: dict, colorme_product: dict) -> dict:
    # 詳細ページのvar Colorme.product.nameには<br>タグや全角スペースの残骸が
    # 残ることがある(実データ確認済み)ため、一覧側のクリーンなタイトルを採用し、
    # 詳細ページのJSONは価格・在庫情報の取得のみに使う。
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        variant = pick_canonical_variant(colorme_product.get("variants", []))
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": variant.get("option_price_including_tax") if variant else None,
            "product_url": item["url"],
        }

    variant = pick_canonical_variant(colorme_product.get("variants", []))
    stock_num = colorme_product.get("stock_num")
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": detect_roast_hint(title),
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": variant.get("option_price_including_tax") if variant else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    list_items = fetch_list_items()

    records = []
    flavored_records = []
    for item in list_items:
        try:
            soup = fetch_page(item["url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['url']} ({e})")
            continue
        colorme_product = extract_colorme_product(soup)
        if not colorme_product:
            continue
        detail = build_record(item, colorme_product)
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
    with open("data_hazeya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hazeya.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
