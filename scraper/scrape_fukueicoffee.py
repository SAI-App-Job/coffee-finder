# -*- coding: utf-8 -*-
"""
scrape_fukueicoffee.py

富久栄珈琲(fukuei coffee、item.rakuten.co.jp/fukueicoffee/、福島県郡山市
亀田1丁目51-19、世界的なコーヒー審査員の店主が営む自家焙煎スペシャルティ
コーヒー専門店)の商品情報を取得する。楽天市場(Rakuten Ichiba)出店。

【店舗発見の経緯】
全国再調査(福島県)でtohokukanko.jp記事から発見。

【対象商品について】
実データ確認済み(2026-09時点): ショップカテゴリ「スペシャリティ　ブレンド
コーヒー」(c/0000000101)全8件・「スペシャリティ　ストレートコーヒー」
(c/0000000102)全9件、計17件を対象とする(南米・中米・アフリカ・アジア等の
地域別サブカテゴリや「世界の頂点COE」カテゴリも確認したが、この2カテゴリに
含まれる商品と重複するのみで新規商品は無かった)。お試しセット・月替わり
セット・選べるセット・ドリップパック・ギフト・リキッドコーヒー等は対象外。

【商品データの取得元について】
実データ確認済み: 楽天市場の商品ページはReactアプリとしてレンダリングされ、
`<script type="application/json" id="item-page-app-data">`内のJSONに
価格・バリアント・商品説明が構造化されている。「容量」(100g/200g/
400g(200g×2)/1kg(500g×2))と「挽き目」(豆のまま/各種挽き方)の2軸バリアント
から「100g」×「豆のまま」の組み合わせのtaxIncludedPriceを代表価格として
採用。newProductDescription内のスペック表(HTMLテーブル)に「原材料（原産国）」
「商品特徴」等がラベル付きで構造化されている。

【商品名について】
実データ確認済み: `<title>`相当のtitleフィールドはSEO用キーワードが大量に
付加された長い文字列(例:「エチオピア モカ グジ G1　ウラガ　100g 、200g、
400g、1kg浅煎り / スペシャルティ コーヒー 豆 ドリップ...」)のため、
最初の「数字+g」の手前までを商品名として抽出する。

robots.txt確認済み(2026-09): item.rakuten.co.jpは`?i=`等クエリパラメータ
付きURLのみ制限しており、本スクレイパーが使う素のitem URLは制限対象外。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "富久栄珈琲",
    "url": "https://www.rakuten.co.jp/fukueicoffee/",
    "platform": "楽天市場(Rakuten Ichiba)",
    "address": "福島県郡山市亀田1丁目51-19",
    "prefecture": "福島県",
    "tel": "024-953-7035",
    "robots_txt_status": "許可(2026-09確認。item.rakuten.co.jpのrobots.txtは"
                          "?i=等クエリパラメータ付きURLのみDisallow。本スクレイパーが使う"
                          "素のitem URLは制限対象外)",
}

BASE_URL = "https://item.rakuten.co.jp/fukueicoffee"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

SLUGS = [
    # ブレンド(c/0000000101)
    "ble-afr-100", "ble-bit-100", "ble-cho-100", "ble-fuk-100",
    "ble-hon-100", "ble-moc-100", "ble-ric-100", "ble-roy-100",
    # ストレート(c/0000000102)
    "bra-kaq-100", "eti-uraga-100", "gua-ixban-100", "hon-agua-100",
    "ind-dol-100", "ken-kiawa-100", "kny-wachuri-100", "mex-decaf-100",
    "rwn-sakefunky-100",
]

NAME_PATTERN = re.compile(r"^(.+?)\s*\d+g")
LABEL_PATTERN = re.compile(r"\|(原材料（原産国）|商品特徴)\|([^|]*)")


def fetch_item(slug: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/{slug}/", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    html = resp.text
    idx = html.find('id="item-page-app-data">')
    if idx == -1:
        return None
    start = idx + len('id="item-page-app-data">')
    end = html.find("</script>", start)
    return json.loads(html[start:end].strip())


def build_record(slug: str) -> dict | None:
    data = fetch_item(slug)
    if not data:
        return None
    sku = data["api"]["data"]["itemInfoSku"]
    raw_title = sku.get("title") or ""
    m = NAME_PATTERN.match(raw_title)
    title = (m.group(1) if m else raw_title).strip()
    if not title:
        return None

    price = None
    sold_out = True
    for variant in sku.get("sku", []):
        vals = variant.get("selectorValues", [])
        if "100g" in vals and "豆のまま" in vals:
            price = int(round(variant.get("taxIncludedPrice") or 0)) or None
            sold_out = bool(variant.get("hidden"))
            break

    desc_html = sku.get("newProductDescription") or ""
    text = re.sub(r"<[^>]+>", "|", desc_html)
    text = re.sub(r"\|+", "|", text)
    labels = dict(LABEL_PATTERN.findall(text))

    parsed = parse_product(title)
    url = f"{BASE_URL}/{slug}/"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    origin_note = labels.get("原材料（原産国）")
    if parsed["category"] != "ブレンド":
        # 実データ確認済み: 「ケニア　ワチュリ」で商品名・商品特徴文が
        # いずれもケニアと明記しているにもかかわらず、「原材料（原産国）」欄
        # だけ「ルワンダ」という誤記(他商品からのコピペミスとみられる)が
        # あった。タイトルは全銘柄で国名から始まる一貫した命名規則のため、
        # タイトルを優先し、原産国欄はタイトルで判定できなかった場合の
        # フォールバックとして扱う(逆順だと今回のような誤記に弱い)。
        detected = detect_country_name(title) or (origin_note and detect_country_name(origin_note))
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    flavor_notes = (labels.get("商品特徴") or "").strip() or None
    stock_status = "完売" if sold_out else "販売中"

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
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for slug in SLUGS:
        try:
            detail = build_record(slug)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: slug={slug} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_fukueicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fukueicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
