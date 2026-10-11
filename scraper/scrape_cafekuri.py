# -*- coding: utf-8 -*-
"""
scrape_cafekuri.py

カフェくーり(https://cafedecoulis.shopselect.net/、茨城県つくば市大1988)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(茨城県)の新規発掘。

【対象商品について】
実データ確認済み(2026-10時点): 全55商品のうち、豆単品28銘柄(ストレート・ブレンド・decaf)を「豆のまま100g」のバリエーション価格で収録。100g×3種・250g×4種の飲み比べセット、ドリップバッグ、定期便、カレンダー・雑貨は対象外。焙煎度は商品名の括弧内(中煎り〜深煎り)に従う(「ありがとうブレンド」のみ表記なし)。shopselect.netはBASEのショップ向けドメインで、商品ページはBASEと同形式。
商品名・重量は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)・焙煎度(未指定の場合は説明文から)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔を空ける。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "カフェくーり",
    "url": "https://cafedecoulis.shopselect.net/",
    "platform": "BASE",
    "address": "茨城県つくば市大1988",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cafedecoulis.shopselect.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 1.0

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら説明文から判定))
ITEMS = [
    ('2127318', 'くーりブレンド', 100, 'ブレンド', '中深煎り'),
    ('86093358', 'ありがとうブレンド', 100, 'ブレンド', None),
    ('56996338', 'エチオピア ゲイシャ ナチュラル', 100, None, '中煎り'),
    ('87264588', 'エチオピア ウォッシュ', 100, None, '中煎り'),
    ('145588456', 'ルワンダ ブンガWS ハイドロハニープロセス', 100, None, '中煎り'),
    ('73052880', 'グアテマラ オリエンテ ナチュラル', 100, None, '中煎り'),
    ('117417024', 'ホンジュラス マルデン・ロペス', 100, None, '中煎り'),
    ('161163604', 'ドミニカ ワイニーナチュラル', 100, None, '中煎り'),
    ('73230279', 'メキシコ チアパス サンクリストバル', 100, None, '中深煎り'),
    ('109379646', 'ブラジル オレンジショコラ ピーベリー', 100, None, '中深煎り'),
    ('162181533', 'グアテマラ ピーベリー', 100, None, '中深煎り'),
    ('73053164', 'エルサルバドル サンタアナ ナチュラル', 100, None, '中深煎り'),
    ('36425629', 'タイ サイアム ブルームーン', 100, None, '中深煎り'),
    ('88554830', 'エチオピア イルガチェフェ ウォッシュ', 100, None, '中深煎り'),
    ('161164109', 'インド モンスーン AA', 100, None, '中深煎り'),
    ('123498242', 'コロンビア サウスウィラ スプレモ', 100, None, '深煎り'),
    ('106872211', 'グアテマラ アティトラン ウォッシュト', 100, None, '深煎り'),
    ('45053585', 'パプアニューギニア', 100, None, '深煎り'),
    ('151138353', 'ブルンジ カジャブレCWS レッドブルボン ウォッシュト', 100, None, '深煎り'),
    ('151141356', 'インドネシア マンデリンG1 リントン ジョネル', 100, None, '深煎り'),
    ('44909936', 'decaf くーりブレンド', 100, 'ブレンド', '中深煎り'),
    ('61927828', 'decafほっこりブレンド', 100, 'ブレンド', '中深煎り'),
    ('42662212', 'decaf エチオピア H2O処理', 100, None, '中煎り'),
    ('68614661', 'decaf メキシコ H2O処理', 100, None, '中深煎り'),
    ('37329784', 'decaf ブラジル H2O処理', 100, None, '中深煎り'),
    ('58906348', 'decaf コロンビア H2O処理', 100, None, '中深煎り'),
    ('72158811', 'decaf マンデリン H2O処理', 100, None, '深煎り'),
    ('16490609', 'decaf グアテマラ H2O処理', 100, None, '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {"36425629": "タイ"}  # 「タイ サイアム ブルームーン」(辞書の国名検出で拾えない「タイ」表記)

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_NAME_PATTERN = re.compile(r"(フルシティ|シティ|ハイ|フレンチ|イタリアン|ミディアム|ライト|シナモン)ー?ロースト")
ROAST_WORD_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ROAST_LABEL_PATTERN = re.compile(r"焙煎度(?:合い?)?\s*[：:]\s*([^◆※\s]{1,25})")
FLAVOR_SECTION_PATTERN = re.compile(r"◆特徴[：:]?\s*(.*?)(?=◆|$)")
FLAVOR_CUT_MARKERS = ("賞味期限", "※豆の状態について", "◆容量", "＜商品詳細＞")


def roast_from_desc(desc: str) -> str | None:
    """説明文の「焙煎度合い：X」から焙煎度を取得する(ラベルが無い場合は説明文全体の「〜ロースト」表記)。"""
    m = ROAST_LABEL_PATTERN.search(desc)
    seg = m.group(1) if m else desc
    n = ROAST_NAME_PATTERN.search(seg)
    if n:
        return n.group(1) + "ロースト"
    w = ROAST_WORD_PATTERN.search(seg) if m else None
    return w.group(1) if w else None


def flavor_from_desc(desc: str) -> str | None:
    m = FLAVOR_SECTION_PATTERN.search(desc)
    if m and m.group(1).strip():
        text = m.group(1)
    else:
        text = desc
        for marker in FLAVOR_CUT_MARKERS:
            idx = text.find(marker)
            if idx > 0:
                text = text[:idx]
    text = re.sub(r"[□■―]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400] or None


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    raw_desc = html_lib.unescape(desc_m.group(1)) if desc_m else ""
    desc = flavor_from_desc(raw_desc) if raw_desc else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

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
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

    roast = roast_level or (roast_from_desc(raw_desc) if raw_desc else None) or parsed["roast_level"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        finally:
            time.sleep(REQUEST_INTERVAL_SEC)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafekuri.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafekuri.json に出力しました")


if __name__ == "__main__":
    main()
