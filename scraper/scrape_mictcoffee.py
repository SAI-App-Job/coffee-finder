# -*- coding: utf-8 -*-
"""
scrape_mictcoffee.py

MicT(Coffee Beans+Cafe MicT、mict-coffee.com、富山県富山市荒川2丁目24-15、
カラーミーショップ)の商品情報を取得する。

【店舗発見の経緯】
全国再調査(富山県)の新規発掘で発見。コーヒーのとみかわとは別ショップ。
住所は特定商取引法ページ(?mode=sk)で確認(2026-10-12)。

【対象商品について】
実データ確認済み(2026-10時点): 全95商品(search一覧)のうち、珈琲豆(ブレンド・
シングル・デカフェ・SELECTION等)の32商品を対象とする。
除外: ドリップバッグ、ギフト、無糖/ボトルコーヒー・カフェオレベース・水出しパック、
珈琲ようかん、マサラチャイ、各種教室・トレーニング、ブレンド「マイルド 1kg」
(事業者向け大容量のみ)。
バリエーションは重量(250g/500g、SELECTIONは50g/100g/200g)×挽き方で構成される
ため、挽き方「豆」で最小重量のバリエーションを代表として採用する。
商品名・焙煎度は商品名の【】表記を確認したうえで下のITEMSに明示している。
価格・重量・在庫(「SOLD OUT」ボタン)・説明は商品ページから取得する。

【robots.txtについて】
User-agent: * は /secure/ と /cart/ のみ制限(他のshop-pro.jp系店舗と同一)。
本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "MicT",
    "url": "https://mict-coffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "富山県富山市荒川2丁目24-15",
    "prefecture": "富山県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://mict-coffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# (商品ID, 商品名, 分類の上書き(Noneなら自動判定), 焙煎度(商品名の【】表記。無ければ説明の明記))
ITEMS = [
    ("188195941", "実りブレンド", "ブレンド", "中深煎り"),
    ("188679534", "アニバーサリーブレンド", "ブレンド", "浅煎り"),
    ("186097027", "ミクトブレンド", "ブレンド", "中煎り"),
    ("186097024", "ショコラブレンド", "ブレンド", "深煎り"),
    ("186097028", "立山ブレンド", "ブレンド", "中煎り"),
    ("186097023", "ハウスブレンド", "ブレンド", "中煎り"),
    ("186097025", "モーニングブレンド", "ブレンド", "中浅煎り"),
    ("186097026", "スイートブレンド", "ブレンド", "中深煎り"),
    ("186097029", "濃厚ブレンド", "ブレンド", "深煎り"),
    ("186097053", "ロイヤルトヤマ", "ブレンド", None),
    ("186097072", "フォレストブレンド", "ブレンド", None),
    ("186097073", "アトリエブレンド", "ブレンド", "深煎り"),
    ("186097070", "タテヤマブレンド TJAR ver. 2026", "ブレンド", "中煎り"),
    ("192612953", "エチオピア イルガチェフェ ゲデブ・チェルチェレ ウォッシュド", None, "浅煎り"),
    ("193322553", "エチオピア グジ アナソラ ナチュラル", None, "浅煎り"),
    ("193706583", "ケニア ケグワ", None, "中浅煎り"),
    ("191564258", "ブラジル カクェンジ イエローカツカイ", None, "中煎り"),
    ("193685744", "ブルンジ ヤンダロ ブルボン", None, "中浅煎り"),
    ("191604192", "インドネシア リントンニフタ", None, "中深煎り"),
    ("186091062", "ブラジル ダテーラ パルプドナチュラル", None, "中深煎り"),
    ("192905942", "コロンビア シエラネバダ", None, "深煎り"),
    ("192261277", "エチオピア シダモ カフェインレス", None, "中深煎り"),
    ("187210484", "コロンビア ファンマルティン ゲイシャ オキシデーション", None, "浅煎り"),
    ("187357750", "コロンビア ファンマルティン シドラ ウォッシュド", None, "浅煎り"),
    ("187357979", "コロンビア ファンマルティン シドラ ナチュラル", None, "浅煎り"),
    ("189403445", "パナマ エスメラルダ ゲイシャ ナチュラル Private Collection", None, "浅煎り"),
    ("188363633", "パナマ ドン エドゥアルド ゲイシャ シンメトリー", None, "浅煎り"),
    ("189734847", "グアテマラ エル・インヘルト パタゴニア パカマラ ナチュラル", None, "浅煎り"),
    ("190718421", "ブラジル カッシャンブー アララ BANGAナチュラル", None, "浅煎り"),
    ("188209502", "ジャマイカ ブルーマウンテンNo.1 ジャーニーズ・エンド", None, "浅煎り"),
    ("188211632", "インドネシア コピルワック ワイルド", None, "浅煎り"),
    ("188204913", "ブラジル シティオ ブラガ", None, "中浅煎り"),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.IGNORECASE)


def fetch_html(pid: str) -> str:
    resp = requests.get(f"{BASE_URL}?pid={pid}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def extract_colorme_product(text: str) -> dict | None:
    m = COLORME_JSON_PATTERN.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("product")
    except json.JSONDecodeError:
        return None


def pick_min_weight_variant(variants: list[dict]) -> tuple[int | None, int | None]:
    """挽き方「豆」のバリエーションのうち最小重量の(重量g, 税込価格)を返す。"""
    best = None
    for v in variants:
        if (v.get("option2_value") or "").strip() != "豆":
            continue
        m = WEIGHT_PATTERN.search(v.get("option1_value") or "")
        if not m:
            continue
        grams = int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
        price = v.get("option_price_including_tax")
        if best is None or grams < best[0]:
            best = (grams, price)
    return best if best else (None, None)


def extract_description(text: str) -> str | None:
    """商品説明(埋め込みHTML)から「First Impression」以降のテキストを抽出する。"""
    i = text.find('p-product-body__description">')
    if i < 0:
        return None
    j = text.find("■ 送料について", i)
    seg = text[i + len('p-product-body__description">'):j if j > 0 else i + 6000]
    seg = re.sub(r"(?s)<style.*?</style>", "", seg)
    seg = re.sub(r"(?s)<title.*?</title>", "", seg)
    seg = re.sub(r"<br\s*/?>", "\n", seg)
    seg = re.sub(r"<[^>]+>", "", seg)
    seg = html.unescape(seg)
    k = seg.find("First Impression")
    if k >= 0:
        seg = seg[k:]
    seg = re.sub(r"\s+", " ", seg).strip()
    return seg[:400] or None


def build_record(pid: str, name: str, category_override: str | None, roast_level: str | None) -> dict | None:
    text = fetch_html(pid)
    product = extract_colorme_product(text)
    if not product:
        return None
    weight_g, price = pick_min_weight_variant(product.get("variants") or [])
    if price is None:
        price = product.get("sales_price_including_tax")
    sold_out = "SOLD OUT" in text

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if pid in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": extract_description(text),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, name, category_override, roast_level in ITEMS:
        try:
            record = build_record(pid, name, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mictcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mictcoffee.json に出力しました")


if __name__ == "__main__":
    main()
