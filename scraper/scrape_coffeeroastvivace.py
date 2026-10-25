# -*- coding: utf-8 -*-
"""
scrape_coffeeroastvivace.py

Coffee Roast Vivace(https://store.vivace.gift/、東京都目黒区八雲3-6-22 小倉マンション101)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-25時点): BASE全130件のうち、同銘柄が約200g/約500g/約1kgで並ぶ焙煎豆の最小規格(約200g=生豆240g焙煎)35銘柄(ブレンド4・デカフェ3)。スイーツ・リキッド・ドリップ・ナッツ・コーヒーパウダー・焙煎機・おまとめセットは除外。焙煎度は購入時に2〜12から選択式のため未設定。公式ドメイン coffeevivace.official.ec は store.vivace.gift へ301転送される。
商品名・重量・分類・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上空ける。
"""

import json
import re
import time
import html as htmllib

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "Coffee Roast Vivace",
    "url": "https://store.vivace.gift/",
    "platform": "BASE",
    "address": "東京都目黒区八雲3-6-22 小倉マンション101",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASE(https://store.vivace.gift/ 旧 coffeevivace.official.ec)の商品一覧と各商品ページ、/about(住所・営業時間10:00-18:00・水曜定休)を2026-10-25に確認。自家焙煎の根拠はプレスリリース https://www.value-press.com/pressrelease/306593 の「60種類以上のコーヒー豆を…独自に開発した直火1kg釜で焙煎」。公式サイト自体に「自家焙煎」の語はない。楽天市場店(https://www.rakuten.co.jp/coffeeroastvivace/)は採用せず。",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://store.vivace.gift"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.0
DEFAULT_WEIGHT_G = 200

# (商品ID, 商品名, 分類(None=自動判定), 産地の上書き(None=商品名から判定), 焙煎度(None=商品ページから判定))
ITEMS = [
    ('163680312', 'ジャガーハニー', None, None, None),
    ('158113501', 'ハロウィンブレンド', 'ブレンド', None, None),
    ('142414408', 'ンベサンベサピーベリー', None, None, None),
    ('54605263', 'グアテマラシャルロット', None, None, None),
    ('131978857', 'コピ・ジェルク オランジット', None, None, None),
    ('127713156', 'オーロラ・ドゥ・チェルベサ', None, None, None),
    ('120504134', 'クブルコ・ラ・モレナ', None, None, None),
    ('94965488', 'マタリクラシック', None, None, None),
    ('74958116', 'ニカラグアウィークエンド', None, None, None),
    ('59560482', 'カスティージョ', None, None, None),
    ('59559771', 'ルイス・コロンビア', None, None, None),
    ('54610935', 'ハワイコナEXファンシー', None, 'アメリカ(ハワイ)', None),
    ('54610960', 'ブルーマウンテンNo.1', None, None, None),
    ('54609557', 'ゴリゲシャ', None, None, None),
    ('54610926', 'ゲシャの花束', 'ブレンド', None, None),
    ('54610861', '深沢シティロースト', 'ブレンド', None, None),
    ('54610841', 'ビバーチェスペシャル', 'ブレンド', None, None),
    ('54610817', 'デカフェメキシコ（オーガニック）', 'デカフェ', 'メキシコ', None),
    ('54610785', 'デカフェエチオピア（オーガニック）', 'デカフェ', 'エチオピア', None),
    ('54610762', 'デカフェコロンビア（オーガニック）', 'デカフェ', 'コロンビア', None),
    ('54610546', 'オーガニックペルー', None, None, None),
    ('54610498', 'オーガニックブラジル', None, None, None),
    ('54610407', 'オーガニックグアテマラ', None, None, None),
    ('54610198', 'キリマンジャロ', None, None, None),
    ('54609938', 'アフリカンスノー', None, None, None),
    ('54609837', 'ライオンハート', None, None, None),
    ('54609612', 'イルガチェフナチュラル', None, None, None),
    ('54609372', '修道院のコーヒー', None, None, None),
    ('54609135', 'マンデリンG-1', None, None, None),
    ('54607227', 'キャラメラード', None, None, None),
    ('54607180', 'クラシコアマレロ', None, None, None),
    ('54607028', 'フルッタメルカド', None, None, None),
    ('54606053', 'コロンビアレインボー', None, None, None),
    ('54604640', 'エルサルバドル マラカラ・ブルボン', None, None, None),
    ('54604303', 'カリビアンチェリー', None, None, None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_WORDS = ["中浅煎り", "中深煎り", "浅煎り", "深煎り", "中煎り"]


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("　", " ")).strip()


def page_text(html_text: str) -> str:
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", txt)))


def extract(html_text: str, name: str) -> dict:
    txt = page_text(html_text)
    k = txt.rfind("ポスト シェア")
    e = txt.find("通報する", k)
    body = txt[k + len("ポスト シェア"):e].strip() if k >= 0 and e > k else ""
    para = re.split(r"【(?:コーヒー豆|ブレンド)の基本情報】", body)[0].strip()
    imp = re.search(r"印象\s*：\s*(.+?)\s*内容量", body)
    out = {}
    desc = (f"印象: {imp.group(1)}。" if imp else "") + para
    out["desc"] = desc[:400] or None
    area = re.search(r"原産国 / Area\s*：\s*(.+?)\s*(?:規格 / 製法|内容量)", body)
    if area and "・" not in area.group(1):
        out["origin"] = detect_country_name(area.group(1).split("/")[0])
    meth = re.search(r"規格 / 製法\s*：\s*(.+?)\s*(?:印象|内容量)", body)
    if meth:
        out["processing"] = detect_processing_method(meth.group(1))
    return out


def build_record(item_id: str, name: str, category_override, origin_override, roast_level) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"
    extra = extract(html_text, name)

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
        if origin_override:
            parsed["origin_country"] = origin_override
            parsed["origin_source"] = "raw_name"
        elif not parsed["origin_country"] and extra.get("origin"):
            parsed["origin_country"] = extra["origin"]
            parsed["origin_source"] = "description"

    processing = parsed["processing_method"] or extra.get("processing")
    # 焙煎度は購入時に2〜12から選択する方式のため商品としては未設定(商品名の「シティロースト」はブレンド名の一部)
    roast = roast_level

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": extra.get("desc"),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": DEFAULT_WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, category_override, origin_override, roast_level in ITEMS:
        record = None
        for attempt in range(2):  # 一時的な接続切断に備え、間隔を空けて1回だけ再試行する
            try:
                record = build_record(item_id, name, category_override, origin_override, roast_level)
                break
            except requests.RequestException as e:
                print(f"[warn] 詳細ページ取得失敗: item_id={item_id} attempt={attempt + 1} ({e})")
                time.sleep(REQUEST_INTERVAL_SEC * 2)
        time.sleep(REQUEST_INTERVAL_SEC)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeeroastvivace.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeroastvivace.json に出力しました")


if __name__ == "__main__":
    main()
