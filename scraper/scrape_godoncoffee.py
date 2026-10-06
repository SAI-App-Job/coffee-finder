# -*- coding: utf-8 -*-
"""
scrape_godoncoffee.py

ゴードンこーひー(通販: futabandrum.shop-pro.jp、カラーミーショップ。公式: https://godoncoffee.com/)
の商品情報を取得する。静岡県静岡市駿河区小黒1-10-37(特定商取引法表記で確認)。

【店舗発見の経緯】
全国再調査(静岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全91商品(一覧8ページ)のうち、焙煎豆(「(豆)」表記の商品)の
27銘柄を対象とする。粉(「(粉)」)・ドリップバッグ/コーヒーバッグ・各種セット(おすすめ/旬な/
深煎り/クオリティ/飲み比べ)・水出しコーヒーバック・カフェオレベースは除外した。
同一銘柄が重量違いの別商品で並ぶもの(カフェ・ノアール、デカフェ・コロンビア、グアテマラ・
ラスロサス、トリオ、健三郎、サッチモ、モーニン: 200g/250gと500g)は、最小重量の商品を代表とし
500gパックは除外した。ブレンドかストレートかは商品説明で確認済み(下のBLEND_PIDS)。

【文字コード】EUC-JP(実データ確認済み)。

【価格・重量・在庫】
バリアントは無く、商品名に重量(200g/250g/150g)が入っている。価格は税込価格
(var Colorme の sales_price_including_tax)を採用する。在庫は stock_num が 0 の場合に完売と
する(例: ゲイシャビレッジ・ディマ・ナチュラル)。None は在庫管理なし(販売中)。

【焙煎度・精製方法について】
焙煎度は商品名に「深煎り」とある商品のみ取得する(それ以外は説明文に焙煎度の明確な記載が
無いためNone)。精製方法は商品名(ナチュラル)または説明文に明記されているもののみ
(FW=水洗式、スマトラ式)ITEMSの上書きで指定している。

【robots.txtについて】
shop-pro.jp の他店舗と同一の記述(/secure/ 等のみ制限)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
)

SHOP_INFO = {
    "name": "ゴードンこーひー",
    "url": "https://godoncoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "静岡県静岡市駿河区小黒1-10-37",
    "prefecture": "静岡県",
    "robots_txt_status": "許可(shop-pro.jp共通。/secure/等以外は制限なし。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://futabandrum.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# 対象の焙煎豆(商品ID)。同一銘柄は最小重量の商品を代表にしている。
TARGET_PIDS = [
    "127866757",  # サッチモ(豆)250g
    "127866761",  # モーニン(豆)250g
    "141238589",  # トリオ(豆)250g
    "129654429",  # 健三郎(豆)200g
    "131169525",  # カフェ・ノアール(豆)200g
    "180388961",  # カフェ・プルート(豆)200g
    "173017205",  # 33coffee(豆)200g
    "170355194",  # ぺーパームーン(豆)200g
    "146131411",  # ムーンリバー 200g(豆)
    "145770340",  # モカジャバ 200g(豆)
    "139284274",  # Cafe Sana「サナ」(豆)200g
    "133237877",  # カフェ・バーガンディ(豆)200g
    "131169377",  # カフェ・オペラ(豆)200g
    "129655216",  # カフェ・ボッサ(豆)200g
    "145918463",  # デカフェ・コロンビア 200g(豆)
    "171067100",  # グアテマラ・ラスロサス(豆)200g
    "165866232",  # ニカラグア・アパナス(豆)200g
    "159811575",  # 深煎りエチオピア・モカ(豆)200g
    "136694821",  # ブラジル・トラディション(豆)200g
    "132768198",  # エチオピア・モカナチュラル(豆)200g
    "131244303",  # ケニヤ・タトゥ農園(豆)200g
    "129655162",  # マンデリン・タノバタック(豆)200g
    "129655075",  # 深煎りコロンビア(豆)200g
    "129655048",  # 深煎りグアテマラ(豆)200g
    "129655000",  # 深煎りブラジル(豆)200g
    "129654905",  # エチオピア・イルガチェフェ・チェレレクツFW(豆)200g
    "165755931",  # ゲイシャビレッジ・ディマ・ナチュラル(豆)150g
]

# 商品説明でブレンドと確認できた商品(商品名に「ブレンド」を含まないものが多いため明示する)
BLEND_PIDS = {
    "127866757", "127866761", "141238589", "129654429", "131169525", "180388961", "173017205",
    "170355194", "146131411", "145770340", "139284274", "133237877", "131169377", "129655216",
}

# 産地の上書き(商品名の表記が coffee_parser の辞書にない/国名が名前に無いもの)
ORIGIN_OVERRIDES = {
    "131244303": "ケニア",    # ケニヤ・タトゥ農園
    "165755931": "エチオピア",  # ゲイシャビレッジ(説明文「エチオピア南西部のベンチマジゾーン」)
}

# 精製方法の上書き(商品名・説明文に明記されているもの)
PROCESS_OVERRIDES = {
    "129654905": "ウォッシュド",  # 商品名「FW」、説明文「水洗式のコーヒー」
    "129655048": "ウォッシュド",  # 説明文「生産処理: 水洗方式(FW)、天日乾燥」
    "129655162": "スマトラ式",   # 説明文「伝統的なスマトラ式での精選方法」
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch(url: str) -> str:
    last = None
    for _ in range(4):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=40)
            resp.raise_for_status()
            resp.encoding = "euc-jp"
            return resp.text
        except requests.RequestException as e:
            last = e
            time.sleep(3)
    raise last


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html_text = fetch(url)
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = re.sub(r"\s+", " ", (product.get("name") or "")).strip()

    soup = BeautifulSoup(html_text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    desc_el = soup.select_one("div.product_description")
    desc = re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True)).strip()[:400] if desc_el else None

    # 商品名の「(豆)」と重量表記を除いた銘柄名にする
    name = re.sub(r"[（(]豆[）)]", "", title)
    name = re.sub(r"\s*\d+\s*[gｇ]\s*$", "", name).strip()
    name = re.sub(r"\s+", " ", name)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if pid in BLEND_PIDS:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if pid in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
            parsed["origin_source"] = "raw_name" if pid == "131244303" else "product_description"
        elif not parsed["origin_country"]:
            country = detect_country_name(name)
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, None)
    if pid in PROCESS_OVERRIDES:
        parsed["processing_method"] = normalize_processing_method(PROCESS_OVERRIDES[pid])

    weight_m = WEIGHT_PATTERN.search(title)
    stock_num = product.get("stock_num")
    sold_out = isinstance(stock_num, int) and stock_num <= 0
    roast_level = "深煎り" if "深煎り" in name else parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": product.get("sales_price_including_tax"),
        "weight_g": int(weight_m.group(1)) if weight_m else None,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in TARGET_PIDS:
        try:
            record = build_record(pid)
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
    with open("data_godoncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_godoncoffee.json に出力しました")


if __name__ == "__main__":
    main()
