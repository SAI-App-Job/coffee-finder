# -*- coding: utf-8 -*-
"""
scrape_27coffee.py

27 COFFEE ROASTERS(27coffee.jp、Shopify製)の商品情報を取得する。
神奈川県藤沢市が拠点。辻堂本店・CORNER 27・鎌倉店・坂ノ下店・茅ヶ崎店の5拠点
展開(店舗情報はaggregate_shops.py側では扱わず、data/shops.jsonへ手動で
SHOP_LOCATION形式を追加する。scraper側はSHOP_INFOに本店住所のみ持たせる)。

robots.txt確認済み(2026-08時点): 標準的なShopify生成robots.txtで、/products/・
/collections/ 配下は許可されている(/cart・/checkout・/account・/admin等のみ
Disallow)。AIエージェントによる購入完了を禁じる旨の記述もあるが、本スクレイパー
は商品情報の読み取りのみで購入操作は一切行わないため無関係。

【products.jsonエンドポイントについて】
FUGLENと異なり単一コレクションに絞らず、サイト全体の `/products.json` を
ページング(limit=250)で辿る方式を採用した。理由: 実データ確認したところ
コレクション分類が「NEW」「送料無料」等の販促軸と混在しており、豆売り商品を
モレなく拾うには`product_type`フィールド(実データ確認済み: 豆売り商品は一貫して
"Coffee Beans")で判定する方が確実だったため。

【豆売り商品の絞り込み】
product_type=="Coffee Beans" のうち、タイトルに「セット」を含むもの(複数種類の
豆を詰め合わせたギフト商品、実データ確認済み: 通常商品と価格体系が大きく異なる
複数バリアント構成)、「水出し」を含むもの(個包装の水出しコーヒーパック、
実データ確認済み: グラム単位の豆売りではなく個数売りで、weight_g概念が馴染まない)
を除外する。

【body_htmlの構造について】
FUGLENのようなth/td表ではなく、`<h2>■見出し</h2>` の直後に複数の要素(div/p/ul等)
が次のh2まで続く構成(実データ確認済み)。実在する見出しラベルは「■カッピング
コメント」「■ロースト」「■プロセス」「■バランス表」「■生産地」「■内容」
「■ストーリー」で、品種は独立見出しではなく「■内容」直下の`<li><strong>品種
</strong>...</li>`に埋め込まれている(初期実装では「■焙煎度」「■精製方法」
「■品種」という見出しを誤って想定しており、実データで全滅していたため修正)。
ロースト・プロセスは選択式UIをそのまま書き出したもので、実際に採用されている
項目の要素だけclass名に"-on"を含む(例: `class="... roast-on"`
`class="process-base process-washed process-on-washed"`)。次のh2が来るまでの
全兄弟要素を対象に、class名に"-on"を含む要素のテキストを拾う方式にした。
カッピングコメントは見出し直後の最初の`<p>`(内訳の色分けdiv群より前)を採用する。
値表記は「日本語 / English」形式(FUGLENの「英語(日本語)」とは順序も区切りも
違う)のため、スラッシュ区切りで前半(日本語)を取り出す専用ヘルパーを用意した。

【重量の扱いについて】
実データ確認したところ、Shopifyのvariant.grams フィールドが実際の重量と
食い違うケースが見つかった(例: タイトルに「100g」とあるバリアントで
grams:800という値が入っていた)。信頼できないため、weight_gは常に
variant.titleの文字列(例:"100g"、"200g / 中挽き")から正規表現で抜き出す
方式に統一し、gramsフィールド自体は使わない。
"""

import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "27 COFFEE ROASTERS",
    "url": "https://27coffee.jp/",
    "platform": "Shopify(サイト全体のproducts.jsonエンドポイントを利用)",
    "address": "神奈川県藤沢市辻堂元町6-5-3",  # 辻堂本店。他4拠点はdata/shops.jsonへ手動追加
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。標準Shopify robots.txt。/products/・/collections/は許可対象)",
}

BASE_URL = "https://27coffee.jp"
CRAWL_DELAY_SECONDS = 1  # robots.txt確認済み(2026-08時点): Crawl-delay指定なし
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "Coffee Beans"
EXCLUDE_TITLE_KEYWORDS = ["セット", "水出し"]

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def split_ja_en(text: str | None) -> str | None:
    """「日本語 / English」形式のテキストから日本語部分(スラッシュ前)を取り出す。"""
    if not text:
        return None
    parts = text.split(" / ")
    return parts[0].strip() or None


def collect_section_nodes(h2) -> list:
    """h2見出しから次のh2直前までの兄弟要素(タグのみ、NavigableStringは除く)を集める。"""
    nodes = []
    for sib in h2.find_next_siblings():
        if getattr(sib, "name", None) == "h2":
            break
        if getattr(sib, "name", None):
            nodes.append(sib)
    return nodes


def extract_on_text(nodes: list) -> str | None:
    """選択式UIで実際に採用されている項目(class名に"-on"を含む要素)のテキストを
    集める。ロースト・プロセスのように複数のdivグループに分かれていても、
    次のh2までの全兄弟要素を対象にするため取りこぼさない。"""
    texts = []
    for node in nodes:
        for el in node.select('[class*="-on"]'):
            t = el.get_text(strip=True)
            if t:
                texts.append(t)
    return " / ".join(texts) if texts else None


def extract_content_list(nodes: list) -> dict:
    """「■内容」セクションの<li><strong>ラベル</strong>値...</li>形式を
    ラベル→値の辞書に変換する(品種・生産処理場・標高等はここにまとまっている)。"""
    result = {}
    for node in nodes:
        for li in node.select("li"):
            label_el = li.find(["strong", "b"])
            if not label_el:
                continue
            label = label_el.get_text(strip=True)
            label_el.extract()
            value = re.sub(r"\s+", " ", li.get_text(separator=" ", strip=True))
            if value:
                result[label] = value
    return result


def fetch_products_page(page: int) -> list[dict]:
    url = f"{BASE_URL}/products.json"
    resp = requests.get(url, params={"limit": 250, "page": page}, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("products", [])


def parse_body_sections(body_html: str) -> tuple[dict, dict, str | None]:
    """h2見出し(■カッピングコメント/■ロースト/■プロセス/■生産地/■内容)ごとに
    次のh2直前までの兄弟要素から値を取り出す。
    戻り値は (sections, content_list, flavor_notes) のタプル。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    sections = {}
    content_list = {}
    flavor_notes = None

    for h2 in soup.find_all("h2"):
        label = h2.get_text(strip=True).lstrip("■").strip()
        nodes = collect_section_nodes(h2)
        if not nodes:
            continue

        if label == "生産地":
            text = re.sub(r"\s+", " ", " ".join(n.get_text(" ", strip=True) for n in nodes)).strip()
            sections["origin_note"] = text or None
        elif label == "カッピングコメント":
            # 内訳の色分けdiv群より前にある最初の<p>だけをテイスティングノートとして採用する
            first_p = next((n for n in nodes if n.name == "p"), None)
            if first_p:
                raw_text = re.sub(r"\s+", " ", first_p.get_text(strip=True))
                flavor_notes = split_ja_en(raw_text)
        elif label == "ロースト":
            sections["roast_note"] = extract_on_text(nodes)
        elif label == "プロセス":
            sections["processing_note"] = extract_on_text(nodes)
        elif label == "内容":
            content_list = extract_content_list(nodes)

    return sections, content_list, flavor_notes


def parse_weight_from_variant_title(variant_title: str | None) -> int | None:
    if not variant_title:
        return None
    m = WEIGHT_PATTERN.search(variant_title)
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """在庫があるバリアントの中で最小重量(タイトル文字列から解析)のものを優先し、
    無ければ全バリアント中最小重量のものを使う。gramsフィールドは信頼できないため
    使用しない(実データ確認済み: 表記と食い違う値が入っているケースがあった)。"""
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants
    return min(
        pool,
        key=lambda v: parse_weight_from_variant_title(v.get("title")) or float("inf"),
    )


def is_target_product(product: dict) -> bool:
    if product.get("product_type") != TARGET_PRODUCT_TYPE:
        return False
    title = product.get("title", "")
    return not any(kw in title for kw in EXCLUDE_TITLE_KEYWORDS)


def build_record(product: dict) -> dict:
    title = product.get("title", "")
    product_url = f"{BASE_URL}/products/{product.get('handle')}"
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        variant = pick_canonical_variant(product.get("variants", []))
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(float(variant["price"])) if variant else None,
            "product_url": product_url,
        }

    sections, content_list, flavor_notes = parse_body_sections(product.get("body_html", ""))

    origin_note = split_ja_en(sections.get("origin_note"))
    if origin_note:
        detected = detect_country_name(origin_note) or origin_note
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    processing_note = split_ja_en(sections.get("processing_note"))
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    roast_note = split_ja_en(sections.get("roast_note"))
    variety = split_ja_en(content_list.get("品種"))

    variant = pick_canonical_variant(product.get("variants", []))
    structural_out_of_stock = not any(v.get("available") for v in product.get("variants", []))
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "roast_hint": roast_note,
        "roast_selectable": False,  # 実データ確認済み: 焙煎度は商品ごとに固定(選択式UIは精製方法等の表示用途)
        "variety": variety,
        "flavor_notes": flavor_notes,
        "price": int(float(variant["price"])) if variant else None,
        "weight_g": parse_weight_from_variant_title(variant.get("title")) if variant else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_raw = []
    page = 1
    while True:
        batch = fetch_products_page(page)
        if not batch:
            break
        all_raw.extend(batch)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    target_products = [p for p in all_raw if is_target_product(p)]

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in target_products:
        product_url = f"{BASE_URL}/products/{product.get('handle')}"
        variant = pick_canonical_variant(product.get("variants", []))
        current_price = int(float(variant["price"])) if variant else None
        current_out_of_stock = not any(v.get("available") for v in product.get("variants", []))

        prev = previous.get(product_url)
        if is_unchanged(
            prev,
            raw_name=product.get("title", ""),
            price=current_price,
            out_of_stock=current_out_of_stock,
        ):
            records.append(prev)
            continue

        record = build_record(product)
        if record.get("is_flavored"):
            flavored_records.append(record)
        else:
            records.append(record)

    return records, flavored_records


def debug_one_product():
    resp = requests.get(f"{BASE_URL}/products/ethiopia-washed.json", headers=REQUEST_HEADERS, timeout=15)
    body_html = resp.json()["product"]["body_html"]
    soup = BeautifulSoup(body_html, "html.parser")
    for h2 in soup.find_all("h2"):
        label = h2.get_text(strip=True).lstrip("■").strip()
        nodes = collect_section_nodes(h2)
        print(f"[DEBUG] label={label!r} node_count={len(nodes)} node_names={[getattr(n, 'name', None) for n in nodes]}")
        if label in ("ロースト", "プロセス"):
            print(f"[DEBUG]   on_text={extract_on_text(nodes)!r}")
        if label == "カッピングコメント":
            first_p = next((n for n in nodes if n.name == "p"), None)
            print(f"[DEBUG]   first_p={first_p!r}")
    sections, content_list, flavor_notes = parse_body_sections(body_html)
    print(f"[DEBUG] sections={sections!r}")
    print(f"[DEBUG] content_list={content_list!r}")
    print(f"[DEBUG] flavor_notes={flavor_notes!r}")


def main():
    debug_one_product()
    records, flavored_records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_27coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_27coffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
