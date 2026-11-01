# -*- coding: utf-8 -*-
"""
scrape_yamadacoffeeokinawa.py

YAMADA COFFEE OKINAWA(山田珈琲 沖縄。shop.yamadacoffeeokinawa.com、カラーミーショップ)の
商品情報を取得する。沖縄県那覇市泊の「chapteR 那覇泊店」と宜野湾市の「宜野湾店」の2店舗。
(奄美の「山田珈琲 Amami Island」・岐阜の山田珈琲とは別店)

【文字コード】EUC-JP(実データ確認済み、2026-11時点)。

【対象商品について】
カテゴリ「CREATIVE COFFEE」(ブレンド)と「COFFEE OF MATERIAL」(シングルオリジン・デカフェ)の
商品を対象とする。TRIAL SET・GIFT・SIMPLE COFFEE ITEM(カフェオレベース・コーヒーバッグ)・
BREW GOODS・ORIGINAL GOODS、および「詰め合わせセット」は除外する。
全商品が200g(最小重量。100g等の小分けは無い)で、ローストレベル違いは別商品として並ぶため
それぞれ別銘柄として収録する。バリエーションは挽き方(豆/粉/パウダー)のみで、価格は同一。
一覧ページ(?mode=cate)から商品を拾い、商品ページの `var Colorme` JSON(税込価格 sales_price_including_tax、
在庫 stock_num。inventory_control=product で、0なら品切れ)と説明文を取得する。

robots.txt確認済み(2026-11-02): User-agent: * は /cart/ のみ制限。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "YAMADA COFFEE OKINAWA",
    "url": "https://shop.yamadacoffeeokinawa.com/",
    "platform": "カラーミーショップ",
    "address": "沖縄県那覇市泊2-15-6",
    "prefecture": "沖縄県",
    "robots_txt_status": "許可(2026-11-02確認。/cart/以外は制限なし)",
    "source_note": "YAMADA COFFEE OKINAWA(https://shop.yamadacoffeeokinawa.com/)のカテゴリ CREATIVE COFFEE・COFFEE OF MATERIAL と各商品ページを2026-11-02に確認。"
                   "公式 https://yamadacoffeeokinawa.com/about に chapteR 那覇泊店(那覇市泊2-15-6)と宜野湾店(宜野湾市宜野湾3-17-3)の2店舗の住所・営業時間あり(代表住所は特商法の所在地の那覇泊店)。お知らせ・新豆入荷は2026-10-28〜11-01と新しい。",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://shop.yamadacoffeeokinawa.com/"
CATEGORIES = [
    # (カテゴリID, ブレンドか)
    (2107079, True),   # CREATIVE COFFEE
    (2120828, False),  # COFFEE OF MATERIAL
]
REQUEST_INTERVAL = 2
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

EXCLUDE_KEYWORDS = ["セット", "詰め合わせ", "ギフト", "ドリップバッグ", "コーヒーバッグ", "カフェオレ"]
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_LABELS = [
    "フルシティロースト", "シティロースト", "ミディアムロースト", "フレンチロースト",
    "ハイロースト", "ライトロースト", "イタリアンロースト", "シナモンロースト",
]


def fetch(url: str) -> str:
    for attempt in range(3):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "60"))
            print(f"[warn] 429: {wait}秒待機 {url}")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        resp.encoding = "euc-jp"
        return resp.text
    raise RuntimeError(f"取得失敗: {url}")


def list_products(cbid: int) -> list[tuple[str, str, str | None]]:
    """カテゴリ一覧から(商品ID, 一覧上の商品名, 一覧上の説明=焙煎度)を取る"""
    html_text = fetch(f"{BASE_URL}?mode=cate&cbid={cbid}&csid=0&sort=n")
    soup = BeautifulSoup(html_text, "html.parser")
    rows = []
    for unit in soup.select("div.product-list__unit__inner"):
        a = unit.select_one("a.product-list__name")
        if not a:
            continue
        m = re.search(r"pid=(\d+)", a.get("href", ""))
        if not m:
            continue
        expl = unit.select_one("p.product-list__expl")
        rows.append((m.group(1), a.get_text(" ", strip=True), expl.get_text(" ", strip=True) if expl else None))
    return rows


def clean_name(title: str) -> str:
    t = re.sub(r"\s+", " ", title.replace("　", " ")).strip()
    t = re.sub(r"^【[^】]*限定[^】]*】\s*", "", t)
    t = re.sub(r"[※＊*]\s*おひとり様\d+点まで", "", t)
    t = WEIGHT_PATTERN.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def extract_description(html_text: str) -> str | None:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    start = text.find("カートに入れる")
    end = text.find("オプションの値段詳細")
    if start == -1 or end == -1 or end <= start:
        return None
    body = text[start + len("カートに入れる"):end]
    body = re.sub(r"\s+", " ", body).strip()
    return body[:400] or None


def build_record(pid: str, list_title: str, list_expl: str | None, is_blend: bool) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html_text = fetch(url)
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        print(f"[warn] Colorme JSONなし: {url}")
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = (product.get("name") or list_title).strip()
    name = clean_name(title)
    if any(k in name for k in EXCLUDE_KEYWORDS):
        return None

    stock_num = product.get("stock_num")
    sold_out = stock_num is not None and stock_num <= 0
    price = product.get("sales_price_including_tax")
    w = WEIGHT_PATTERN.search(title)
    weight = int(w.group(1)) if w else None
    roast = next((r for r in ROAST_LABELS if list_expl and r in list_expl), None)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
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
        "flavor_notes": extract_description(html_text),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    seen = set()
    for cbid, is_blend in CATEGORIES:
        rows = list_products(cbid)
        time.sleep(REQUEST_INTERVAL)
        for pid, title, expl in rows:
            if pid in seen:
                continue
            seen.add(pid)
            if any(k in title for k in EXCLUDE_KEYWORDS):
                continue
            try:
                rec = build_record(pid, title, expl, is_blend)
            except requests.RequestException as e:
                print(f"[warn] 商品ページ取得失敗: pid={pid} ({e})")
                rec = None
            if rec is not None:
                records.append(rec)
            time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yamadacoffeeokinawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamadacoffeeokinawa.json に出力しました")


if __name__ == "__main__":
    main()
