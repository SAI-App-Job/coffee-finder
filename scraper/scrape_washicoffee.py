# -*- coding: utf-8 -*-
"""
scrape_washicoffee.py

鷲コーヒー(washi.net、山形県米沢市本町2丁目5-21、自家焙煎豆のオンライン販売。
1999年創業)の商品情報を取得する。プラットフォームは標準的なASP/EC構築サービス
ではなく、静的HTML(Microsoft FrontPage製)の商品ページ群+紀真堂(kishindo.co.jp)の
レンタルショッピングカートシステム(kago.cgi)という独自構成。

【住所について】
公式サイトの特定商取引法ページ(https://www.washi.net/tokuteisyou.htm)で実データ
確認(2026-09時点): 山形県米沢市本町2丁目5-21。

robots.txt確認済み(2026-09時点): https://www.washi.net/robots.txtは
「User-agent: * / Allow: /」のみで制限なし。

【商品ページの一覧取得方法について】
実データ確認済み(2026-09時点): 買い物かごトップ(k-0.htm)から k-1.htm〜k-21.htm・
k-cuba.htm・k-cuba-b.htm・k-papua.htm・k-ruby.htm・k-h_b.htm・k-h_c.htm・
k-decaf-c.htm・k-guren-2026.htm・k-nicaragua-shg-2026.htm・k-tanzania_ab-qs-2026.htm・
k-gihuto.htmという商品固有の静的ページへのリンクが並ぶ。このうちk-19.htm(水出し
アイスパック)・k-20.htm/k-21.htm(コーヒーギフトセット)・k-gihuto.htm(コーヒー
ギフト)は焙煎豆単品ではないため、商品名に含まれるキーワードで除外する
(NON_BEAN_KEYWORDS)。

【文字コード】Shift_JIS(実データ確認済み)。

【価格・重量(パックサイズ)について】
実データ確認済み: 各商品ページの<SELECT NAME="odercode">内に
`<OPTION VALUE="商品ID=商品名（パックサイズ）=価格=　=税込=URL">`という形式の
注文用選択肢が並び、常に先頭が最小パックサイズ(100gパック)であることを確認済み
(k-1・k-10・k-decaf-c等、複数商品で確認)。この先頭オプションを代表バリアントとして
価格・重量(100g)を採用する。パック表記の括弧は全角「（）」と半角「()」の両方が
実データで確認済み(k-papua.htmのみ半角)のため、正規表現は両対応にしている。

【商品詳細情報(■ラベル値)について】
実データ確認済み: 商品説明の直後に「生産地 XXX<br>農園名 XXX<br>標高 XXX<br>
等級 XXX<br>収穫時期 XXX<br>品種 XXX<br>スクリーンサイズ XXX<br>精選方法 XXX<br>
認証 XXX」という、ラベルと値をスペースで区切った行が<br>区切りで並ぶ(決まった
9ラベルのうち、商品によって一部欠けることがある)。<br>を改行に変換した上で、
行頭が既知ラベルに一致する行から値を取り出す。ブレンド商品にはこのブロック自体が
無いため、産地・農園情報はストレート商品のみに適用する。

【焙煎度について】
実データ確認済み: 商品画像近くに「焙煎度：　中煎り<br>（ハイロースト）」のような
2段階表記(和名+専門用語)がある。和名(中煎り等)を商品名に含む場合が多く
coffee_parser.parse_product()で商品名から判定できるが、含まれない商品もあるため
保険としてページからも抽出しroast_hintとして保持する(roast_levelは商品名からの
判定を優先する)。

【flavor_notes(テイスティングノート)の追加取得について(2026-09-19追記)】
実データ確認済み(k-guren-2026.htm): 「焙煎度：」の近くに「風味：」という
ラベルがあり、続けて<br>区切りで「しっかりとした飲みごたえのあるコク」
「キレのある心地よい苦味香ばしさを余韻で感じる」という具体的な風味描写が
入る。この行群は「風味：」の直後、空行(<br><br>)に達するまでで区切られており、
その先には無関係な販促文言(「50周年記念商品のため...」)が続く。DETAIL_LABELSは
既知9ラベルの固定リストのため「風味」は元々対象外だったが、別途
parse_flavor_notes()で「風味：」〜最初の空行までを抽出してflavor_notesとする。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, normalize_processing_method, detect_stock_status, detect_country_name
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "鷲コーヒー",
    "url": "https://www.washi.net/",
    "platform": "独自ASP(紀真堂のレンタルショッピングカート kishindo.co.jp/netlink/rents)",
    "address": "山形県米沢市本町2丁目5-21",
    "prefecture": "山形県",
    "robots_txt_status": "許可(2026-09確認。robots.txtは「User-agent: * / Allow: /」のみで制限なし)",
}

BASE_URL = "https://www.washi.net"
LIST_URL = f"{BASE_URL}/k-0.htm"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

# 理由はモジュールdocstring参照(水出しアイスパック・コーヒーギフトは焙煎豆単品でない)
NON_BEAN_KEYWORDS = ["ギフト", "水出し", "アイスパック"]

PRODUCT_PAGE_PATTERN = re.compile(r'href="(k-[a-z0-9_.\-]+\.htm)"')
OPTION_PATTERN = re.compile(r'VALUE="\d+=([^=]+?)[（(](\d+)g(?:パック)?[）)]=(\d+)=')
ROAST_PATTERN = re.compile(r"焙煎度[：:]\s*　?\s*([^\s<（]+)")
DETAIL_LABELS = ["生産地", "農園名", "標高", "等級", "収穫時期", "品種", "スクリーンサイズ", "精選方法", "認証"]
DETAIL_LINE_PATTERN = re.compile(r"^(" + "|".join(DETAIL_LABELS) + r")\s+(.+)$")
FLAVOR_LABEL_PATTERN = re.compile(r"^風味[：:]\s*(.*)$")


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "shift_jis"
    return resp.text


def fetch_product_page_urls() -> list[str]:
    html = fetch_text(LIST_URL)
    pages = []
    seen = set()
    for m in PRODUCT_PAGE_PATTERN.finditer(html):
        page = m.group(1)
        if page in seen:
            continue
        seen.add(page)
        pages.append(page)
    return pages


def parse_detail_labels(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text()

    labels = {}
    for line in text.split("\n"):
        line = line.strip()
        m = DETAIL_LINE_PATTERN.match(line)
        if m:
            labels[m.group(1)] = m.group(2).strip()
    return labels


def parse_flavor_notes(html: str) -> str | None:
    """理由はモジュールdocstring参照(「風味：」〜最初の空行までを抽出する)。"""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    lines = soup.get_text().split("\n")

    flavor_lines: list[str] = []
    collecting = False
    for raw_line in lines:
        line = raw_line.strip()
        if not collecting:
            m = FLAVOR_LABEL_PATTERN.match(line)
            if m:
                collecting = True
                if m.group(1):
                    flavor_lines.append(m.group(1))
            continue
        if not line:
            break
        flavor_lines.append(line)
    return "".join(flavor_lines).strip() or None


def build_record(page: str) -> dict | None:
    url = f"{BASE_URL}/{page}"
    html = fetch_text(url)

    option_m = OPTION_PATTERN.search(html)
    if not option_m:
        return None
    raw_name = option_m.group(1).strip()
    weight_g = int(option_m.group(2))
    price = int(option_m.group(3))

    if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
        return {"shop_name": SHOP_INFO["name"], "raw_name": raw_name, "non_bean": True, "product_url": url}

    parsed = parse_product(raw_name)
    is_blend = parsed["category"] == "ブレンド"

    roast_m = ROAST_PATTERN.search(html)
    roast_hint = roast_m.group(1).strip() if roast_m else None
    flavor_notes = parse_flavor_notes(html)

    labels = {} if is_blend else parse_detail_labels(html)
    if labels.get("生産地") and not parsed["origin_country"]:
        country = detect_country_name(labels["生産地"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    if labels.get("精選方法") and not parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])

    farm_note_parts = []
    if labels.get("農園名"):
        farm_note_parts.append(f"農園名: {labels['農園名']}")
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    if labels.get("等級"):
        farm_note_parts.append(f"等級: {labels['等級']}")
    if labels.get("認証"):
        farm_note_parts.append(f"認証: {labels['認証']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    stock_status = detect_stock_status(raw_name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"] or (labels.get("等級") if not is_blend else None),
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": flavor_notes,
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    pages = fetch_product_page_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    non_bean_records = []
    for page in pages:
        product_url = f"{BASE_URL}/{page}"
        prev = previous.get(product_url)
        try:
            detail = build_record(page)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("non_bean"):
            non_bean_records.append(detail)
            continue
        if is_unchanged(prev, raw_name=detail["raw_name"], price=detail.get("price")):
            records.append(prev)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, non_bean_records


if __name__ == "__main__":
    records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_washicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_washicoffee.json に出力しました"
          f"(非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
