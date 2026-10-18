# -*- coding: utf-8 -*-
"""
scrape_kuroshiocoffee.py

くろしお珈琲(https://kuroshiocoffee.com/、高知県高知市長浜567-4、WordPress + Welcart)の
商品情報を取得する。

【店舗発見の経緯】
全国再調査(高知県)の新規発掘で発見。住所は特定商取引法表示(/tradelaw/、販売事業者
「くろしお珈琲 中島篤史」)で確認。

【対象商品について】
実データ確認済み(2026-10時点): トップページに並ぶ26商品のうち、焙煎豆は14銘柄
(ブレンド2・シングル12)。コーヒーバッグ(3p/10p)・ネルドリップ珈琲・カフェオレベース・
ボトルセット・お試しセット(豆60g×4種)は除外。
post sitemap には、トップページから外れた過去商品(廃盤・売り切れで非公開の旧ページ、
業務用500gなど)が約25件含まれるが、現行の商品一覧に出ていないため対象外とし、
トップページの商品リンクのみを対象にする。
各商品は単一SKU(200グラム。クロシオブレンドのみ徳用500g=250g×2袋)のため、その
SKUを代表とする。価格は税込。
在庫は div.zaikostatus(在庫有り/売り切れ/廃盤)と div.itemsoldout で判定し、売り切れは
「完売」として収録する(9銘柄)。

【robots.txtについて】
WordPress標準(/wp-admin/ のみ Disallow)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "くろしお珈琲",
    "url": "https://kuroshiocoffee.com/",
    "platform": "WordPress + Welcart",
    "address": "高知県高知市長浜567-4",
    "prefecture": "高知県",
    "robots_txt_status": "許可(WordPress標準。/wp-admin/ のみDisallow。識別可能なUser-Agentを使用)",
}

HOME_URL = "https://kuroshiocoffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# 豆の商品コード(コーヒーバッグ coffeebag__*、ギフト gift__*、チケット ticket__* は除外)
BEAN_CODE_PATTERN = re.compile(r"^(c|cs)__\d+$")

# 商品ページの記述(生産国・産地・生産者)から確認した産地(商品名に国名が無いため明示する)
ORIGIN_BY_CODE = {
    "cs__62": "ケニア",            # 生産国:Kenya
    "cs__63": "エチオピア",        # 生産国:Ethiopia
    "cs__64": "パプアニューギニア",  # 生産国:Papua New Guinea
    "cs__65": "タンザニア",        # 生産国:Tanzania
    "cs__66": "エチオピア",        # 生産国:Ethiopia
    "cs__67": "ペルー",            # 生産国:Peru
    "cs__69": "エチオピア",        # 「エチオピア シコ」(Guji)
    "cs__71": "タンザニア",        # Acacia Hills / Karatu, Oldeani
    "cs__72": "エチオピア",        # Sidama / Shantawene
    "cs__73": "ペルー",            # 生産地Peru
    "cs__74": "コロンビア",        # 生産国:Colombia
    "cs__75": "コロンビア",        # 「コロンビア ラスペルリタス」
}
PROCESS_BY_CODE = {
    "cs__63": "ナチュラル",
    "cs__66": "ナチュラル",
    "cs__67": "ロングファーメンテーション・ウォッシュド",
    "cs__69": "ウォッシュド",
    "cs__71": "ウォッシュド",
    "cs__72": "アナエロビック・ウォッシュド",
    "cs__73": "ウォッシュド",
    "cs__74": "ウォッシュド",
    "cs__75": "ウォッシュド",
}

SPEC_LINE_PATTERN = re.compile(
    r"^(生産国|生産地方|生産地区|生産地|生産者名?|標高|精製所?|精製方法|精製方法解説|品種|農園|収穫|インポーター|FOB|"
    r"品質分析|数量|発注単位|荷姿|パッケージ|産地|村|農園／精製所|A\.|B\.)"
)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def extract_flavor(item_desc, name: str) -> str | None:
    if not item_desc:
        return None
    lines = [l.strip() for l in item_desc.get_text("\n", strip=True).split("\n") if l.strip()]
    keep = []
    for line in lines:
        flat = re.sub(r"\s+", "", clean_name(line))
        flat_name = re.sub(r"\s+", "", name)
        if (flat and len(flat) <= 40 and (flat in flat_name or flat_name in flat))                 or SPEC_LINE_PATTERN.match(line) or len(line) > 200:
            continue
        keep.append(line)
    return " ".join(keep)[:400] if keep else None


def list_item_urls() -> list[str]:
    html = fetch(HOME_URL)
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for a in soup.select('a[href^="https://kuroshiocoffee.com/"]'):
        href = a["href"]
        path = urllib.parse.unquote(href[len(HOME_URL):]).strip("/")
        if not path or path.startswith(("category/", "wp-", "usces-", "tradelaw", "privacy", "contact", "instagram", "beanslist")):
            continue
        if href not in urls:
            urls.append(href)
    return urls


def build_record(url: str) -> dict | None:
    soup = BeautifulSoup(fetch(url), "html.parser")
    h1 = soup.select_one("h1.item-name")
    code_el = soup.select_one(".itemcode")
    if not h1 or not code_el:
        return None
    code = code_el.get_text(strip=True)
    if not BEAN_CODE_PATTERN.match(code):
        return None

    name = clean_name(h1.get_text(strip=True))
    # 商品名が「徳用500g」のみで銘柄名が無い(説明の見出しは「クロシオブレンド ダークロースト」)
    if code == "cs__60":
        name = "クロシオブレンド ダークロースト"
    sku = soup.select_one(".skuname")
    wm = re.search(r"(\d+)\s*グラム", sku.get_text(strip=True) if sku else "")
    weight = int(wm.group(1)) if wm else None
    price_el = soup.select_one(".field_price")
    pm = re.search(r"¥\s*([\d,]+)", price_el.get_text() if price_el else "")
    price = int(pm.group(1).replace(",", "")) if pm else None

    zaiko = soup.select_one(".zaikostatus")
    zaiko_text = zaiko.get_text(strip=True) if zaiko else ""
    sold_out = bool(soup.select_one(".itemsoldout")) or zaiko_text in ("売り切れ", "廃盤") or (
        zaiko_text != "" and "在庫有り" not in zaiko_text
    )

    is_blend = "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        origin = ORIGIN_BY_CODE.get(code) or detect_country_name(name)
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name" if origin in name else "description"
        parsed = apply_category_hint_fallback(parsed, name)
    roast = parsed["roast_level"]
    if not roast and "ダークロースト" in name:
        roast = "ダークロースト"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": PROCESS_BY_CODE.get(code) or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": extract_flavor(soup.select_one(".item-description"), name),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_item_urls():
        time.sleep(CRAWL_DELAY_SECONDS)
        try:
            record = build_record(url)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {url} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


if __name__ == "__main__":
    records = scrape_all_products()
    with open("data_kuroshiocoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kuroshiocoffee.json に出力しました")
