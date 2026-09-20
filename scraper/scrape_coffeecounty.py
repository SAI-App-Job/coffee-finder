# -*- coding: utf-8 -*-
"""
scrape_coffeecounty.py

COFFEE COUNTY Kurume(shop.coffeecounty.cc、〒830-0018
福岡県久留米市通町102-8、自家焙煎スペシャルティコーヒー豆専門店)の
商品情報を取得する。カラーミーショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://shop.coffeecounty.cc/?mode=sk)で
「830-0018 福岡県久留米市通町102-8」を確認済み(2026-09時点、EUC-JPで
直接デコードして確認)。

【文字コードについて】
実データ確認済み: Content-Type: text/html; charset=EUC-JP。

【商品名の言語について】
実データ確認済み: 商品名が英語表記("Ethiopia Gogogu Natural 200g"等)。
coffee_parser.pyのORIGIN_COUNTRY_KEYWORDS_ENで産地判定できる。

【テーマについて】
実データ確認済み: `li.productlist-unit`テーマ。商品名は`<p>`内に
「New Item」等のバッジ文言と共に`<br>`区切りで入っている場合があるため、
バッジ文言を除去してから使う。価格は`p.pricebox`に「5,000円(内税)」の
ように直接出力されている。

【重量について】
実データ確認済み: 商品名に「200g」「400g (200g×2)」のように明記。
複数形態(200g/400g)は別商品として個別に登録されているため、重複排除は
行わず商品名から抽出できる最初の重量をweight_gとする。

robots.txt確認済み(2026-09時点): shop-pro.jp標準の記述で、本スクレイパーが
使う一覧ページ(?mode=srh)は制限対象外。

【flavor_notes追加に伴う詳細ページ取得への変更について(2026-09-20追記)】
実データ確認済み: 詳細ページのdiv.setumeibox-in内に、買い付けエピソード・
農園背景の自由記述段落が2〜5個続き、その直後にテイスティング文の段落が
あり、最後に「生産者：」「農園名：」「生産国：」等のラベルで始まる構造化
スペック段落が続く(段落は<br><br>の二重改行で区切られており、単一<br>の
前後に\r\n等の空白のみのテキストノードが挟まる実装上の癖があるため、
SHIBACOFFEE/アメヤ珈琲と同じcontents単位の段落分割方式を再利用する)。
ラベルで始まる段落が最初に現れた位置より前の段落をすべて結合し
flavor_notesとして採用する(買い付けエピソード等の背景説明も含めて採用、
既存の他店舗と同様の方針)。この抽出のため一覧ページのみで完結していた
設計を変更し、各商品の詳細ページも取得するようにした。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "COFFEE COUNTY Kurume",
    "url": "https://shop.coffeecounty.cc/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福岡県久留米市通町102-8",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、"
                          "本スクレイパーが使う一覧ページは制限対象外)",
}

BASE_URL = "https://shop.coffeecounty.cc"
LIST_BASE_URL = "https://shop.coffeecounty.cc/?mode=srh&keyword=&sort=n"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
MAX_PAGES = 20

NON_BEAN_KEYWORDS = ["Gift", "GIFT", "Tシャツ", "Tote", "トート", "Sticker", "Mug", "Merch"]
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)
BADGE_PATTERN = re.compile(r"^(New Item|SALE|SOLD OUT)\s*", re.IGNORECASE)
CRAWL_DELAY_SECONDS = 1
COFFEE_LABEL_START_PATTERN = re.compile(
    r"^(生産者|農園名|生産国|ロット名|生産処理場|生産地域|地域|マイクロミル|農園主|精製所|農園・マイクロミル)[：:\s]"
)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def split_into_paragraphs(el) -> list[str]:
    """<br><br>(二重改行)を段落区切りとして分割する。理由はモジュール
    docstring参照(単一<br>の前後に\\r\\n等の空白のみのテキストノードが
    挟まる実装上の癖があるため、contents単位で空白のみのノードを区切り
    として扱う。SHIBACOFFEE/アメヤ珈琲と同じ方式)。"""
    paragraphs = []
    current_parts: list[str] = []
    for child in el.contents:
        name = getattr(child, "name", None)
        if name == "br":
            continue
        text = child.get_text() if name else str(child)
        text = text.strip()
        if not text:
            if current_parts:
                paragraphs.append(" ".join(current_parts))
                current_parts = []
        else:
            current_parts.append(text)
    if current_parts:
        paragraphs.append(" ".join(current_parts))
    return paragraphs


def extract_flavor_notes(product_url: str) -> str | None:
    """理由はモジュールdocstring参照。"""
    try:
        soup = fetch_page(product_url)
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
        return None
    el = soup.select_one("div.setumeibox-in")
    if not el:
        return None
    kept = []
    for para in split_into_paragraphs(el):
        if COFFEE_LABEL_START_PATTERN.match(para):
            break
        kept.append(para)
    text = " ".join(kept)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def scrape_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = []
    for li in soup.select("li.productlist-unit"):
        link_el = li.select_one('a[href^="?pid="]')
        ptbox = li.select_one("div.pt-box")
        if not link_el or not ptbox:
            continue

        # 商品名は<p>内の最後の行(バッジ<span>の後の<br>以降)。単純に
        # get_text("\n")で分割し、バッジ文言を除いた最後の非空行を採用する。
        name_p = ptbox.find("p")
        title = ""
        if name_p:
            lines = [l.strip() for l in name_p.get_text("\n").split("\n") if l.strip()]
            lines = [BADGE_PATTERN.sub("", l).strip() for l in lines]
            lines = [l for l in lines if l]
            title = lines[-1] if lines else ""
        if not title or any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
            continue

        href = link_el.get("href", "")
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href

        price = None
        price_el = ptbox.select_one("p.pricebox")
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        items.append({"raw_name": title, "product_url": product_url, "price": price})
    return items


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

    if not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title)
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
        "roast_level": parsed["roast_level"],
        "flavor_notes": extract_flavor_notes(item["product_url"]),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_items = []
    seen_urls = set()
    page = 1
    while page <= MAX_PAGES:
        items = scrape_list_page(page)
        new_items = [i for i in items if i["product_url"] not in seen_urls]
        if not new_items:
            break
        for i in new_items:
            seen_urls.add(i["product_url"])
        all_items.extend(new_items)
        page += 1

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import json

    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_coffeecounty.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeecounty.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
