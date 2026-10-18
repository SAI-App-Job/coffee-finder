# -*- coding: utf-8 -*-
"""
scrape_jokicoffee.py

JOKI COFFEE(jokicoffee.shop-pro.jp、高知県長岡郡本山町本山521-1、カラーミーショップ/
shop-pro.jp)の商品情報を取得する。公式サイトは https://www.jokicoffee.com/ 。

【店舗発見の経緯】
全国再調査(高知県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): ショップ全17商品(Blend 3、Straight 14)。Foodカテゴリ
(スコーン・クッキー)は検索結果(?mode=srh&cid=&keyword=)に含まれないため、取得対象外。
一覧は12件/ページのため、ページ送りで全件を取得する(1ページ目のみだと12件で打ち切られる)。
各商品は「豆のまま/粗挽き/中挽き」×「100g/200g」(一部50g)のバリアントを持つ。
代表1件として「豆のまま」の最小重量(ただし50gなどの小分けより100gを優先)を採用する。
価格は税込(option_price_including_tax)で収録する(店舗表記は税抜)。

【在庫について】
実データ確認済み: inventory_control=none(在庫管理未設定、stock_numは常にnull)。
商品ページ(form[name=product_form])に「SOLD OUT/売り切れ/品切れ/完売」等の文言があるか、
「カートに入れる」ボタンが無いかで判定する(2026-10-15時点は全商品がカートボタンあり・
売り切れ文言なし)。

【焙煎度・説明について】
カラーミー側の商品説明は空のため、公式サイト(WordPress)の商品ページ(OFFICIAL_URLS)
から焙煎度(浅煎り Valo/中煎り Harmonia/深煎り Pimeys、ブレンドは英語表記)とテイスティング
ノートを取得する。公式ページが無い5商品は焙煎度・説明をNoneとする。

【robots.txtについて】
他のshop-pro.jp系店舗と同一の記述。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, detect_country_name, apply_category_hint_fallback

SHOP_INFO = {
    "name": "JOKI COFFEE",
    "url": "https://jokicoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "高知県長岡郡本山町本山521-1",
    "prefecture": "高知県",
    "robots_txt_status": "許可(他のshop-pro.jp系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://jokicoffee.shop-pro.jp/"
SEARCH_URL = "https://jokicoffee.shop-pro.jp/?mode=srh&cid=&keyword=&page={page}"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
SOLD_OUT_PATTERN = re.compile(r"SOLD\s*OUT|売り切れ|売切れ|品切れ|完売|在庫切れ|入荷待ち|販売終了|販売停止", re.I)

# カラーミーのpid -> 公式サイト(WordPress)の商品ページ(焙煎度・説明の取得元)
OFFICIAL_URLS = {
    "69033489": "https://www.jokicoffee.com/kahvi/502.html",   # Virta
    "69132313": "https://www.jokicoffee.com/kahvi/500.html",   # Meri
    "69132340": "https://www.jokicoffee.com/kahvi/493.html",   # Adelie
    "122085671": "https://www.jokicoffee.com/kahvi/1506.html",  # Mandheling Bintang Lima
    "129476033": "https://www.jokicoffee.com/kahvi/1537.html",  # Mexico Chiapas Decaf
    "187117246": "https://www.jokicoffee.com/shop/55817.html",  # Rwanda Buhoro
    "192127437": "https://www.jokicoffee.com/kahvi/55841.html",  # Wote Konga Natural
    "193164646": "https://www.jokicoffee.com/kahvi/55868.html",  # Wote Konga Washed
    "193478516": "https://www.jokicoffee.com/shop/55783.html",  # Colombia Las Flores Sidra
    "193479146": "https://www.jokicoffee.com/shop/2144.html",   # Tanzania TANJA
    "193772896": "https://www.jokicoffee.com/shop/2406.html",   # Ethiopia Harar Deder
    "193800342": "https://www.jokicoffee.com/shop/55627.html",  # Nicaragua Los Placeres
}

# ブレンドの焙煎度は公式サイトが英語表記のため日本語に対応づける(roast_hintに原文を保持)
ROAST_EN_TO_JA = {
    "hi-medium": "中浅煎り",
    "city-medium": "中煎り",
    "fullcity-dark": "深煎り",
}

SPEC_LINE_PATTERN = re.compile(
    r"^(Region|Plantation|Variety|Process|Altitude|Woreda|Kebele|Company|Owner|Factory|Farm|Estate|Producer|CWS|Cup Profile|Aroma/Flavor)\s*:",
    re.I,
)


def fetch(url: str, encoding: str | None = None) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = encoding or "utf-8"
    return resp.text


def list_product_ids() -> list[tuple[str, str]]:
    """検索結果(12件/ページ)を空になるまでページ送りして (pid, 商品名) を集める。"""
    found: dict[str, str] = {}
    for page in range(1, 20):
        html = fetch(SEARCH_URL.format(page=page), "euc-jp")
        new = 0
        for m in re.finditer(r'<a[^>]*href="[^"]*pid=(\d+)"[^>]*>(.*?)</a>', html, re.S):
            text = re.sub(r"<[^>]*>", "", m.group(2)).strip()
            if text and m.group(1) not in found:
                found[m.group(1)] = text
                new += 1
        time.sleep(CRAWL_DELAY_SECONDS)
        if new == 0:
            break
    return list(found.items())


def pick_variant(variants: list[dict]) -> tuple[dict | None, int | None]:
    """「豆のまま」の最小重量(50g等の小分けより100gを優先)のバリアントを返す。"""
    beans = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")]
    candidates = []
    for v in beans or variants:
        m = WEIGHT_PATTERN.search(v.get("option2_value") or "")
        if m:
            candidates.append((int(m.group(1)), v))
    if not candidates:
        return None, None
    at_least_100 = [c for c in candidates if c[0] >= 100]
    weight, variant = min(at_least_100 or candidates, key=lambda c: c[0])
    return variant, weight


def fetch_official(pid: str) -> tuple[str | None, str | None, str | None]:
    """公式ページから (焙煎度(日本語), 焙煎度の原文, テイスティングノート) を返す。"""
    url = OFFICIAL_URLS.get(pid)
    if not url:
        return None, None, None
    time.sleep(CRAWL_DELAY_SECONDS)
    soup = BeautifulSoup(fetch(url), "html.parser")
    article = soup.find("article")
    if not article:
        return None, None, None
    text = article.get_text("\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    roast_ja = roast_raw = None
    notes = []
    stop = False
    for i, line in enumerate(lines):
        if i == 0:  # 記事の先頭行は商品名
            continue
        if line.startswith("商品名："):
            stop = True
        if line.lower().startswith("roast"):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            roast_raw = nxt
            m = re.match(r"(浅煎り|中煎り|深煎り)", nxt)
            if m:
                roast_ja = m.group(1)
            else:
                key = nxt.strip().lower().replace(" ", "")
                for k, v in ROAST_EN_TO_JA.items():
                    if key.startswith(k):
                        roast_ja = v
                        break
            continue
        if stop or line in (roast_raw,):
            continue
        if SPEC_LINE_PATTERN.match(line) and not line.lower().startswith(("cup profile", "aroma/flavor")):
            continue
        if len(line) > 150:  # 農園・産地の紹介文は除く
            continue
        if re.match(r"^(アロマ\s*[/／]\s*フレーバー)$", line):
            continue
        notes.append(line)
    flavor = " ".join(notes)[:400] if notes else None
    return roast_ja, roast_raw, flavor


def build_record(pid: str, fallback_title: str) -> dict | None:
    html = fetch(BASE_URL + f"?pid={pid}", "euc-jp")
    m = COLORME_JSON_PATTERN.search(html)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = (product.get("name") or fallback_title).strip()
    variant, weight = pick_variant(product.get("variants") or [])
    price = variant.get("option_price_including_tax") if variant else product.get("sales_price_including_tax")

    soup = BeautifulSoup(html, "html.parser")
    form = soup.select_one("form[name=product_form]")
    form_text = form.get_text(" ", strip=True) if form else ""
    has_cart = bool(form and any(
        "カートに入れる" in (b.get("value") or b.get_text())
        for b in form.select("button, input[type=submit]")
    ))
    sold_out = bool(SOLD_OUT_PATTERN.search(form_text)) or not has_cart

    crumbs = [a.get_text(strip=True) for a in soup.select("ul.topicpath-nav a")]
    is_blend = "Blend" in crumbs

    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
    if "Decaf" in title:
        parsed["category"] = "デカフェ"

    roast_ja, roast_raw, flavor = fetch_official(pid)
    stock_status = detect_stock_status(title, structural_out_of_stock=sold_out)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_ja or parsed["roast_level"],
        "roast_hint": roast_raw,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": BASE_URL + f"?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, title in list_product_ids():
        try:
            record = build_record(pid, title)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if record is not None:
            records.append(record)
    return records


if __name__ == "__main__":
    records = scrape_all_products()
    with open("data_jokicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_jokicoffee.json に出力しました")
