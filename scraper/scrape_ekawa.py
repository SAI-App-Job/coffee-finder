# -*- coding: utf-8 -*-
"""
scrape_ekawa.py

エカワ珈琲店(ekawa.ocnk.net、和歌山県和歌山市雑賀屋町39番地、自家焙煎
コーヒー豆のオンライン販売)の商品情報を取得する。おちゃのこネット(Ocnk)。

robots.txt確認済み(2026-09時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /)。
本スクレイパーは該当しない。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに/product/N形式の個別商品ページへの
リンクが17件直接含まれているため、そのままpid一覧として利用する。

【<title>タグが信頼できないことについて】
実データ確認済み: このサイトは<title>タグの中身が実際の商品名と一致
しない場合がある(例: pid=719の<title>は「味わいのブレンド」だが、実際
は「ブラジル・ダテーラ農園」のページ)。og:title(meta property="og:title")
は正しい商品名を反映しているため、こちらを商品名として採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: 「おまかせ３銘柄セット」「お試し２銘柄(豆のまま)」
「おまかせ２銘柄」のようなおまかせ・お試し詰め合わせ、「アウトレット
コーヒー」(規格外品の詰め合わせ)が非対象。NON_BEAN_KEYWORDSで除外する。
残り13件が対象。

【同一商品の重量・梱包バリエーションの重複について】
実データ確認済み: 残り13件のうち6銘柄(エチオピア イルガチェフェ・
イディドモカ/パプアニューギニア トロピカルマウンテン/香味のブレンド/
味わいのブレンド/深味のブレンド/ブラジル・ダテーラ農園)が「200g袋詰め
（宅急便）」と「100g袋×2袋＝200g（ネコポス便）」の2つの梱包形態で別
ページ登録されている(実質同一商品・同一重量200g)。商品名から重量以降
の記述(「、200g袋詰め」「100g×2袋＝200g」等)を取り除いた基準名で
グループ化し、(1)在庫あり優先、(2)「×2袋」形式でない単一梱包(200g
袋詰め)を優先、(3)商品URLの昇順、の順で1件を代表として採用する。
6銘柄+梱包重複のない「エイジング(オールド)コーヒー」1件の計7件が
最終的な対象になる。

【在庫状況について】
実データ確認済み: 梱包バリエーションの重複を除いた実質7銘柄のうち、
「深味のブレンド」「ブラジル・ダテーラ農園」の2銘柄が両梱包形態とも
在庫なし。出品自体は残しつつout_of_stock=Trueで保持する(プロジェクト
方針通り)。

【og:titleの前後に付く装飾記号について】
実データ確認済み: 一部商品のog:titleは前後に半角アスタリスク(**)が
付与されている(例: 「**エチオピア イルガチェフェ・イディドモカ ...**」)。
これは商品名の一部ではなく装飾のため、抽出時に取り除く。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "エカワ珈琲店",
    "url": "https://ekawa.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "和歌山県和歌山市雑賀屋町39番地",
    "prefecture": "和歌山県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ"
                          "Disallow: /で本スクレイパーは該当しない)",
}

BASE_URL = "https://ekawa.ocnk.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["おまかせ", "アウトレット", "お試し"]
# 商品名から「重量＋梱包」の説明以降を切り落とすためのパターン
# (例: 「ブラジル・ダテーラ農園、２００ｇ袋詰」→「ブラジル・ダテーラ農園」、
#  「味わいのブレンド（100g×2袋／200g）...」→「味わいのブレンド」)
WEIGHT_TAIL_PATTERN = re.compile(r"[（(]?[、,]?\s*[0-9０-９]+\s*[gｇ].*$")
WEIGHT_PATTERN = re.compile(r"[0-9０-９]+\s*[gｇ]")
FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [
        loc.get_text(strip=True) for loc in soup.find_all("loc")
        if re.search(r"/product/\d+$", loc.get_text(strip=True))
    ]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].strip().strip("*").strip()
    title = re.sub(r"\s+", " ", title)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    out_of_stock = "在庫なし" in soup.get_text()
    return {"title": title, "price": price, "out_of_stock": out_of_stock}


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    base = WEIGHT_TAIL_PATTERN.sub("", title)
    base = re.sub(r"[、,・/／\s]+$", "", base).strip()
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = None
    if weight_m:
        digits = weight_m.group(0).translate(FULLWIDTH_DIGITS)
        digits = re.sub(r"[^\d]", "", digits)
        weight_g = int(digits) if digits else None
    return base or title, weight_g


def pick_canonical_items(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        base, weight_g = base_name_and_weight(item["title"])
        item["base_name"] = base
        item["weight_g"] = weight_g
        groups.setdefault(base, []).append(item)

    canonical = []
    for base, group in groups.items():
        def sort_key(it):
            is_split_pack = "×" in it["title"] or "x" in it["title"].lower()
            return (
                0 if not it["out_of_stock"] else 1,
                1 if is_split_pack else 0,
                it["url"],
            )
        group.sort(key=sort_key)
        canonical.append(group[0])
    return canonical


def build_record(item: dict) -> dict | None:
    title = item["base_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title, item["out_of_stock"])

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
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    all_items = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        all_items.append({
            "title": fields["title"],
            "price": fields["price"],
            "out_of_stock": fields["out_of_stock"],
            "url": product_url,
        })

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item)
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
    with open("data_ekawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ekawa.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
