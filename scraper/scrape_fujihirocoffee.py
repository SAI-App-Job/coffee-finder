# -*- coding: utf-8 -*-
"""
scrape_fujihirocoffee.py

ふじひろ珈琲(https://www.fujihiro-coffee.co.jp/、島根県出雲市多伎町口田儀834-1)の商品情報を取得する。
カラーミーショップ(shop-pro.jp系、独自ドメイン。fujihiro-coffee.shop-pro.jp も同一ストア)。

【店舗発見の経緯】
全国再調査(島根県)の新規発掘で発見。

【住所について】
特定商取引法表示(/?mode=sk)の販売業者は「有限会社 藤博」(運営統括責任者: 伊藤 博人)、住所は
「〒699-0904 島根県出雲市多伎町口田儀834-1」、電話 0853-24-1760。一方、飲食店情報サイト(Retty)では
同じ電話番号の「ふじひろ珈琲」が「島根県出雲市渡橋町1223-1」の自家焙煎喫茶店として掲載されている。
公式サイト・公式ブログ(fujihiro-coffee.blog.jp)には焙煎所の所在地の明記が無く、渡橋町の店舗が焙煎所かは
公式情報では確認できなかったため、方針どおり特商法の住所を採用した(要確認)。

【robots.txt】
確認済み(2026-10-15時点): User-agent: * は /secure/ と /cart/ のみ制限(SEO系ボットのみ全面禁止)。

【対象商品について】
実データ確認済み(2026-10-15時点): 商品検索一覧(?mode=srh&keyword=&sort=n、4ページ)の41件のうち、
コーヒー豆はストレート8銘柄・ブレンド6銘柄の計14商品(全て200g。商品ページの「内容量：200g」/商品名の「200g」)。
除外: 200g×2〜6袋入のまとめ買い(ふじひろ・ロイヤルブレンド)、縁むすび珈琲のセット・桐箱西陣織巾着入ギフト・
福来樽珈琲セット、ドリップカフェ(ドリップバッグ)各種・3点セット、サンクス/販促グッズ、
オリジナルアイスコーヒー(無糖・液体)。
各ストレートの商品ページに「原産国：」が明記されているため産地は下のITEMSに明示する。
ブレンドの原産国表記は無い。「縁むすび珈琲」は商品説明にブレンドとの明記は無いが、ブレンド銘柄としてブレンド扱いとする(要確認)。
価格は商品ページの`var Colorme`のバリエーション(豆のまま)の税込価格。文字コードはEUC-JP。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ふじひろ珈琲",
    "url": "https://www.fujihiro-coffee.co.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "島根県出雲市多伎町口田儀834-1",
    "prefecture": "島根県",
    "robots_txt_status": "許可(2026-10-15確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://www.fujihiro-coffee.co.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

# (pid, 商品名, 重量(g), ブレンドか, 焙煎度, 産地(ストレートのみ、商品ページの「原産国：」表記))
ITEMS = [
    ("14272592", "ブラジル・サントス NO.2#18", 200, False, None, "ブラジル"),
    ("14273265", "コロンビア・スプレモ", 200, False, None, "コロンビア"),
    ("14272973", "スマトラ・マンデリン・G-1", 200, False, None, "インドネシア"),
    ("14276283", "キリマンジャロ・タンザニア AA", 200, False, None, "タンザニア"),
    ("14276462", "グァテマラ・SHB", 200, False, None, "グアテマラ"),
    ("14277276", "モカ・マタリ No.9", 200, False, None, "イエメン"),
    ("14277905", "メキシコ・AL", 200, False, None, "メキシコ"),
    ("179863334", "ジャバ・ロブスタWIB", 200, False, "深煎り", "インドネシア"),
    ("14282885", "ふじひろブレンドコーヒー", 200, True, None, None),
    ("14313665", "ロイヤルブレンドコーヒー", 200, True, None, None),
    ("160322171", "スペシャルブレンドコーヒー", 200, True, None, None),
    ("133211960", "マイルドブレンドコーヒー", 200, True, None, None),
    ("133211951", "ゴールドブレンドコーヒー", 200, True, None, None),
    ("14317283", "縁むすび珈琲", 200, True, None, None),
]


def fetch_page(url: str) -> tuple[BeautifulSoup, str]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def extract_colorme(raw_html: str) -> dict:
    m = re.search(r"var\s+Colorme\s*=\s*", raw_html)
    if not m:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(raw_html[m.end():])
    except json.JSONDecodeError:
        return {}
    return data.get("product") or {}


def page_text(soup: BeautifulSoup) -> str:
    for x in soup(["script", "style"]):
        x.decompose()
    return re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))


def extract_description(text: str, name: str) -> str | None:
    """商品名見出し(「▼ 商品名」)から「■オプションの値段詳細」までの本文(原産国・内容量・味の説明)。"""
    m = re.search(r"▼\s*" + re.escape(name) + r"[^\n]*\n(.*?)■オプション", text, re.S)
    desc = m.group(1) if m else ""
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc[:400] or None


def detect_sold_out(text: str) -> bool:
    """商品本体の領域(「▼ 商品名」〜「特定商取引法に基づく表記」)にSOLD OUT等の表記があるか、購入欄(「購入数」)が無ければ完売。
    (この店舗の商品ページは「■オプションの値段詳細」の後ろに「型番・販売価格・購入数」が続く構造)"""
    start = text.find("ホーム" + chr(10) + "＞")
    end = text.find("特定商取引法に基づく表記", max(start, 0))
    region = text[max(start, 0): end if end > 0 else None]
    if re.search(r"SOLD\s*OUT|売り切れ|品切れ|在庫切れ", region, re.I):
        return True
    return "購入数" not in region


def pick_whole_bean_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    for v in variants:
        if (v.get("option1_value") or "").strip() in ("豆のまま", "豆"):
            return v
    return variants[0]


def scrape_all_products() -> list[dict]:
    records = []
    for pid, name, weight, is_blend, roast, origin in ITEMS:
        time.sleep(CRAWL_DELAY_SECONDS)
        url = f"{BASE_URL}/?pid={pid}"
        try:
            soup, raw = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        product = extract_colorme(raw)
        variant = pick_whole_bean_variant(product.get("variants") or [])
        if not variant:
            print(f"[warn] バリエーションが取得できません: pid={pid}")
            continue
        price = variant.get("option_price_including_tax")

        text = page_text(soup)
        desc = extract_description(text, product.get("name") or name)
        sold_out = detect_sold_out(text)

        parsed = parse_product(name)
        if parsed["is_flavored"]:
            continue
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["processing_method"] = None
            parsed["grade"] = None
        else:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "description"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(price) if price else None,
            "weight_g": weight,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_fujihirocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fujihirocoffee.json に出力しました")


if __name__ == "__main__":
    main()
