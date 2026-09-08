# -*- coding: utf-8 -*-
"""
scrape_rokumeicoffee.py

ROKUMEI COFFEE CO.(六鳴珈琲、rokumei.coffee、奈良県奈良市西御門町31、自家焙煎豆の
オンライン販売)の商品情報を取得する。

プラットフォームについて: 本プロジェクトの確立済み6パターン(BASE/カラーミー/
Shopify/Ocnk/WooCommerce/EC-CUBE)のいずれにも該当しない。実データ確認の
結果、"future-shop.jp"・"future-shop.net"ドメインへのスクリプト参照および
"itembox.cloud"の商品画像CDNから、フューチャーショップ(Future Shop)という
別のECプラットフォームと判明した。この店舗については依頼側で「奈良本店＋
都内支店等を含む急拡大中の複数拠点展開だが11店舗未満のため対象、オンライン
ショップがスクレイプ可能なら実装してよい」との明示的な指示があったため、
新パターンではあるが実装する(スコープ判断の詳細はレポート参照)。

抽出方法について: 各商品ページにschema.org準拠のJSON-LD(<script type=
"application/ld+json">)が埋め込まれており、これを情報源として使う。
重量バリエーションが複数ある商品は"ProductGroup"型(hasVariant配列に各
重量のPro price/availabilityあり)、単一SKUの商品(定期便コース等、後述の
理由で除外対象)は"Product"型(offersが直接ぶら下がる)で出力される。
json.loads()はデフォルト(strict=True)だと失敗する商品が複数あることを
実データ確認済み(説明文HTML内に生の改行等の制御文字が混入しておりJSON
としては不正な場合があるため)。strict=Falseで読み込むことで回避する。

robots.txt確認済み(2026-09時点): User-agent: * に対しDisallow指定なし
(制限なし)。Sitemap: https://rokumei.coffee/sitemap.xml の記載あり。

【商品一覧の取得方法について】
実データ確認済み: サイト自身のsitemap.xmlは2022年生成の古い内容で現行
商品と乖離があるため使わない。代わりにコーヒー豆カテゴリ一覧ページ
(/c/coffeebeans)自体をクロールし、そこに列挙された商品リンク(/c/coffeebeans/
<slug>形式、2026-09時点で34件)を巡回する。

【非コーヒー豆商品の除外について】
実データ確認済み: 全34件のうち以下13件が単一銘柄の豆売りではなく非対象:
- 【おまかせ定期便】焙煎士のおすすめ 150g×3種類コース／300g×3種類コース(2件、
  複数銘柄詰め合わせの定期便)
- 迷ったらこれ バランスセット／心地よい苦みを感じる ビターセット／
  日常を豊かにする4種のブレンドコーヒー飲み比べセット／同5種セット／
  果実のような味わいを楽しむ フルーティセット／日常を豊かにする1Dayセット／
  【初回限定1,980円】お試し飲み比べセット コーヒー豆100g×2種(7件、いずれも
  複数銘柄の飲み比べセット)
- 【定期便】カスガ／ミカサ／ロクメイ／サルサワ各ブレンド 500gコース(4件、
  同一ブレンドの単発購入商品(rcob-*)と重複する定期便サブスクリプション)
- 【初回限定・おひとり様1回限り】スペシャルティコーヒー お試し飲み比べセット
  100g×3種(1件、複数銘柄セット)
NON_BEAN_KEYWORDS(「定期便」「セット」「飲み比べ」)で除外する。残り20件
(オリジナルブレンド8種+シングルオリジン11種+アイスブレンド1種)を対象とする。

【重量バリエーションについて】
実データ確認済み: 主力銘柄は150g(定価)/500g(10%OFF)/1kg(15%OFF)の3サイズ、
一部の希少銘柄(パナマ ゲイシャ)は75g/150gの2サイズのみ。hasVariant配列内の
各バリアント名末尾の重量表記(「150g」「500g_10%OFF」「1kg_15%OFF」)から
重量を読み取り、在庫があるバリアントの中で最小重量を代表として採用する
(全バリアント品切れの場合は全バリアントの中から最小重量を採用)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ROKUMEI COFFEE CO.",
    "url": "https://rokumei.coffee/",
    "platform": "Future Shop(フューチャーショップ、house未確立パターン。"
                "schema.org JSON-LDを情報源として使用)",
    "address": "奈良県奈良市西御門町31",
    "prefecture": "奈良県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: * に対しDisallow指定なし、"
                          "制限なし)",
}

BASE_URL = "https://rokumei.coffee"
CATEGORY_URL = f"{BASE_URL}/c/coffeebeans"
CRAWL_DELAY_SECONDS = 2.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["定期便", "セット", "飲み比べ"]
CATEGORY_LINK_PATTERN = re.compile(r"^/c/coffeebeans/[a-z0-9_-]+$")
LD_JSON_PATTERN = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)
WEIGHT_G_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
WEIGHT_KG_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.IGNORECASE)


def fetch_html(url: str) -> str:
    """実データ調査で判明: このサイトは短時間の連続アクセスで429 Too Many
    Requestsを返すことがある。1回だけリトライ(長めに待機)して再試行する。
    """
    for attempt in range(2):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        if resp.status_code == 429 and attempt == 0:
            time.sleep(8.0)
            continue
        resp.raise_for_status()
        return resp.text
    resp.raise_for_status()
    return resp.text


def fetch_category_product_urls() -> list[str]:
    html = fetch_html(CATEGORY_URL)
    soup = BeautifulSoup(html, "html.parser")
    urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if CATEGORY_LINK_PATTERN.match(href):
            urls.add(f"{BASE_URL}{href}")
    return sorted(urls)


def extract_weight_g(text: str) -> int | None:
    if not text:
        return None
    m_kg = WEIGHT_KG_PATTERN.search(text)
    if m_kg:
        return int(float(m_kg.group(1)) * 1000)
    m_g = WEIGHT_G_PATTERN.search(text)
    if m_g:
        return int(m_g.group(1))
    return None


def parse_ld_json_blocks(html: str) -> list[dict]:
    blocks = []
    for m in LD_JSON_PATTERN.finditer(html):
        try:
            blocks.append(json.loads(m.group(1), strict=False))
        except (json.JSONDecodeError, ValueError):
            continue
    return blocks


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def is_available(v):
        offer = v.get("offers") or {}
        return offer.get("availability", "").endswith("InStock")

    available = [v for v in variants if is_available(v)]
    pool = available or variants

    def weight_key(v):
        w = extract_weight_g(v.get("name") or "")
        return w if w is not None else float("inf")

    return min(pool, key=weight_key)


def fetch_product_fields(product_url: str) -> dict | None:
    """商品ページのJSON-LDから商品名・価格・重量・在庫状態を抽出する。"""
    html = fetch_html(product_url)
    blocks = parse_ld_json_blocks(html)

    product_group = next((b for b in blocks if b.get("@type") == "ProductGroup"), None)
    product_single = next((b for b in blocks if b.get("@type") == "Product"), None)

    if product_group:
        title = (product_group.get("name") or "").strip()
        variants = product_group.get("hasVariant") or []
        variant = pick_canonical_variant(variants)
        if not variant:
            return None
        offer = variant.get("offers") or {}
        price = offer.get("price")
        weight_g = extract_weight_g(variant.get("name") or "")
        all_out_of_stock = bool(variants) and not any(
            (v.get("offers") or {}).get("availability", "").endswith("InStock")
            for v in variants
        )
        return {
            "title": title,
            "price": int(price) if price is not None else None,
            "weight_g": weight_g,
            "structural_out_of_stock": all_out_of_stock,
        }

    if product_single:
        title = (product_single.get("name") or "").strip()
        offer = product_single.get("offers") or {}
        price = offer.get("price")
        weight_g = extract_weight_g(title)
        structural_out_of_stock = not offer.get("availability", "").endswith("InStock")
        return {
            "title": title,
            "price": int(price) if price is not None else None,
            "weight_g": weight_g,
            "structural_out_of_stock": structural_out_of_stock,
        }

    return None


def build_record(fields: dict, product_url: str) -> dict | None:
    title = fields["title"]
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": fields["price"],
            "product_url": product_url,
        }

    stock_status = detect_stock_status(title, fields["structural_out_of_stock"])

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
        "price": fields["price"],
        "weight_g": fields["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_category_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            fields = fetch_product_fields(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue

        detail = build_record(fields, product_url)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_rokumeicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_rokumeicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
