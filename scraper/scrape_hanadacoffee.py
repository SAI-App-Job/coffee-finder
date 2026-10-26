# -*- coding: utf-8 -*-
"""
scrape_hanadacoffee.py

花田コーヒ(花田コーヒ株式会社。大阪府大阪市中央区高津3-2-10の日本橋本店・本社工場と八尾山本店の2店舗。
1949年創業。hanadacoffee.net、カラーミーショップ独自ドメイン、charset=EUC-JP)の商品情報を取得する。
業務用(卸)が主力の老舗で、このスクリプトは個人向けの焙煎豆(ブレンド・シングルオリジン)だけを対象にする。

【対象】商品検索一覧(?mode=srh&keyword=&sort=n、約8ページ・73件)から焙煎豆のみ。
次は対象外: ドリップバッグ、コーヒーバッグ、水出しコーヒー(パック)、リキッド、カフェオレベース、セット、
フィルター・ドリッパー・サーバー等の器具、テスト商品。
【価格・重量】商品ページの表示価格(例「590円」)は100gあたりの単価。注文時に容量(200g/500g/1kg)を選ぶ方式で、
バリエーションごとの税込価格が Colorme.product.variants にある(例: マウンテンブレンド 200g=1,180円/500g=2,850円/
1kg=5,600円)。このため「豆のまま」の最小容量(200g)のバリエーション価格・重量を代表とする。
容量選択のない商品は商品名の「200g」から重量を取る(税込総額が表示価格)。ブレンド510〜560円は100g単価で、
200gの販売価格は1,020〜1,120円。1kgパックは対象外。
【産地・種別】説明文冒頭の「原産国:」から取得(半角カナは全角化)。複数国・「他」があるもの、または商品名に
ブレンドを含むものはブレンド、それ以外はストレート。
【焙煎度】商品名の括弧書き(中深煎り等)と、説明文の「煎り具合」欄を採用(両方ある場合は説明文を優先)。
「中深〜深煎り」のような幅のある表記は roast_level を null にして roast_hint に記す。選択不可(店が決めた焙煎度)。
【在庫】カートボタンが無ければ品切れ。
robots.txt(2026-10-26確認): User-agent: * は /secure/ と /cart/ のみ禁止。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import detect_country_name, detect_stock_status, parse_product

SHOP_INFO = {
    "name": "花田コーヒ",
    "url": "https://hanadacoffee.net/",
    "platform": "カラーミーショップ(独自ドメイン hanadacoffee.net)",
    "address": "大阪府大阪市中央区高津3-2-10",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "https://hanadacoffee.net/ の商品一覧・各商品ページ・特商法(?mode=sk)・店舗情報(2店舗)を2026-10-26に確認。"
                   "住所は日本橋本店・本社工場(もう1店は八尾山本店)。ページ表示価格は100g単価のため、200gのバリエーション価格を"
                   "代表にした。業務用(卸)が主力で、個人向け商品のみ対象。新商品は2026-09-30付で追加。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://hanadacoffee.net/"
LIST_URL = BASE_URL + "?mode=srh&keyword=&sort=n"
CRAWL_DELAY_SECONDS = 2.0
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = (
    "ドリップ", "バッグ", "セット", "リキッド", "水出し", "カフェオレベース", "フィルター", "濾紙", "カリタ", "V60",
    "ドリッパー", "サーバー", "ＫＷＦ", "KWF", "テスト", "クリーナー", "メジャーカップ", "1kg", "100袋",
)
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*")
WEIGHT_RE = re.compile(r"(\d+)\s*(kg|g)", re.I)
ROAST_RE = re.compile(r"(極深煎り|中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")


def fetch(url: str) -> str:
    time.sleep(CRAWL_DELAY_SECONDS)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> dict[str, str]:
    items: dict[str, str] = {}
    for page in range(1, 15):
        soup = BeautifulSoup(fetch(LIST_URL + ("" if page == 1 else f"&page={page}")), "html.parser")
        new = 0
        for a in soup.find_all("a", href=re.compile(r"^\?pid=\d+")):
            pid = re.search(r"pid=(\d+)", a["href"]).group(1)
            name = re.sub(r"[\s　]+", " ", a.get_text(" ", strip=True))
            if pid not in items:
                items[pid] = name
                new += 1
            elif name and not items[pid]:
                items[pid] = name
        if new == 0:
            break
    return items


def variant_weight(text: str) -> int | None:
    m = WEIGHT_RE.search(unicodedata.normalize("NFKC", text or ""))
    if not m:
        return None
    return int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)


def build_record(pid: str, list_name: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    product = (json.JSONDecoder().raw_decode(html, m.end())[0]).get("product") or {}
    title = re.sub(r"[\s　]+", " ", (product.get("name") or list_name)).strip()
    if not title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    soup = BeautifulSoup(html, "html.parser")
    has_cart = "カートに入れる" in html
    info = soup.select_one("div.product-info") or soup.select_one("div.product__explain")
    lines = [unicodedata.normalize("NFKC", l.strip()) for l in
             (info.get_text("\n", strip=True).split("\n") if info else []) if l.strip()]

    # 価格・重量: 豆のまま × 最小容量
    variants = product.get("variants") or []
    cand = []
    for v in variants:
        opts = unicodedata.normalize("NFKC", f"{v.get('option1_value') or ''}|{v.get('option2_value') or ''}")
        if "細挽き" in opts or "中挽き" in opts or "粗挽き" in opts or "エスプレッソ" in opts:
            continue
        w = variant_weight(v.get("option1_value")) or variant_weight(v.get("option2_value"))
        cand.append((w if w is not None else 10**6, v.get("option_price_including_tax")))
    weight = price = None
    if cand:
        w, p = min(cand)
        weight = None if w == 10**6 else w
        price = p or None
    if weight is None:
        weight = variant_weight(title)
    if price is None:
        price = product.get("sales_price_including_tax") or None

    origin_line = next((l for l in lines if l.startswith("原産国")), "")
    origin_text = origin_line.split(":", 1)[1].strip() if ":" in origin_line else ""
    tokens = [t.strip() for t in re.split(r"[、,]", origin_text) if t.strip()]
    has_other = any(t in ("他", "その他") for t in tokens)
    countries = []
    for t in tokens:
        c = detect_country_name(t)
        if c and c not in countries:
            countries.append(c)

    is_blend = "ブレンド" in title or len(countries) >= 2 or has_other
    parsed = parse_product(title)
    if is_blend:
        category, origin, origin_source = "ブレンド", None, None
        brand = None
    else:
        category = "ストレート"
        origin = countries[0] if countries else detect_country_name(title)
        origin_source = "product_description" if origin else None
        brand = parsed["designated_brand"]

    # 焙煎度: 説明文の「煎り具合/煎り目」欄 > 商品名の括弧書き
    roast_text = None
    for i, l in enumerate(lines):
        if l in ("煎り具合", "煎り目") and i + 1 < len(lines):
            roast_text = lines[i + 1]
            break
    roast_level = roast_hint = None
    if roast_text:
        if "〜" in roast_text or "~" in roast_text:
            roast_hint = roast_text
        else:
            rm = ROAST_RE.search(roast_text)
            roast_level = rm.group(1) if rm else None
            roast_hint = roast_text if not rm else rm.group(1)
    else:
        rm = ROAST_RE.search(unicodedata.normalize("NFKC", title))
        roast_level = roast_hint = rm.group(1) if rm else None

    body = [l for l in lines if not l.startswith("原産国") and not re.search(r"円|定価|数量", l)
            and not re.fullmatch(r"(200|500)\s*g|1kg|挽き方|豆のまま|細挽き|中挽き|粗挽き|エスプレッソ|細挽|中挽|粗挽|[-−＋+個]", l)
            and "量で価格が変わります" not in l and "カートに" not in l and "オプション" not in l
            and not l.startswith("特設ページ")]
    norm_title = re.sub(r"\s+", "", unicodedata.normalize("NFKC", title))
    body = [l for l in body if re.sub(r"\s+", "", l) != norm_title
            and l not in ("返品について", "特定商取引法に基づく表記", "数量", "個")]
    for stop in ("煎り具合", "煎り目", "おすすめの時間"):
        if stop in body:
            body = body[:body.index(stop)]
    flavor = " ".join(body)[:300] or None

    stock_status = detect_stock_status(title, structural_out_of_stock=not has_cart)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": category,
        "origin_country": origin,
        "origin_source": origin_source,
        "designated_brand": brand,
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_selectable": False,
        "roast_hint": roast_hint,
        "flavor_notes": flavor,
        "farm_note": ("原産国: " + "、".join(tokens)) if (is_blend and tokens) else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [{"origin_country": c} for c in countries] if is_blend else [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, name in list_items().items():
        if not name or any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        rec = build_record(pid, name)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_hanadacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hanadacoffee.json に出力しました")


if __name__ == "__main__":
    main()
