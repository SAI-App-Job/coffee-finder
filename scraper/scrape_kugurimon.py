# -*- coding: utf-8 -*-
"""
scrape_kugurimon.py

くぐり門珈琲店(kugurimon.com、広島県東広島市西条本町17-1、運営は瀬戸内焙煎倶楽部合同会社の
自家焙煎珈琲店)の商品情報を取得する。カラーミーショップ(独自ドメイン、文字コードEUC-JP)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【住所について】
特定商取引法に基づく表記(?mode=sk)で実データ確認済み(2026-10時点): 「瀬戸内焙煎倶楽部合同会社
住所 広島県東広島市西条本町17-1」。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「レギュラー珈琲豆」(cbid=1619257、全2ページ)の商品のうち、
ペットボトル入り珈琲豆(重量150g/170g表記、13商品=ブレンド5・ストレート8)のみを対象とする。
同カテゴリに含まれる酒スイーツBOX・ピザ・シチュー・セット・冷珈琲(ボトル飲料)等は除外。
ギフト・セットカテゴリの商品も対象外。粉は同一商品の選択肢(購入時に「粉/豆のまま」を選択)。
1銘柄1商品で、重量違いの重複は無い。

【文字コードについて】
サイトはEUC-JP。requestsのencodingを明示的にeuc-jpに指定している。商品名の全角英数字
(「ＳＨＢ」「Ｇ１」等)はNFKCで半角に正規化する。

【在庫・価格について】
価格は税込(「1,380円(税込)」表記)。在庫は一覧の「SOLD OUT」表示で判定する。
商品説明は一部の商品(ブレンド等)のみ記載があり、無い商品はNone。焙煎度の記載はないためNone。

【robots.txtについて】
User-agent: *はDisallow: /secure/・/cart/のみ(実データ確認済み、2026-10)。商品ページは許可。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "くぐり門珈琲店",
    "url": "https://kugurimon.com/",
    "platform": "カラーミーショップ(shop-pro、独自ドメイン)",
    "address": "広島県東広島市西条本町17-1",
    "prefecture": "広島県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/secure/・/cart/のみDisallow)",
}

BASE_URL = "https://kugurimon.com"
CATEGORY_URL = BASE_URL + "/?mode=cate&cbid=1619257&csid=0&page={page}"
MAX_PAGES = 5
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ITEM_PATTERN = re.compile(r'<p class="itemName"><a href="\?pid=(\d+)">(.*?)</a></p>(.*?)</div>', re.S)
BOTTLE_PATTERN = re.compile(r"[（(]\s*ペットボトル\s*[:：]?\s*(\d+)\s*g\s*[）)]")
PRICE_PATTERN = re.compile(r"([\d,]+)円\(税込\)")
BOILERPLATE_PATTERN = re.compile(r"※ペーパー用以外の粉をご希望の場合は.*?エスプレッソなど\)")

# coffee_parser.pyの国名辞書で検出できない銘柄・表記の産地
ORIGIN_OVERRIDES = {
    "モカマタリ": "イエメン",
    "モカナチュラル": "エチオピア",
    "エメラルドマウンテン": "コロンビア",
    "キボ": "タンザニア",
}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return re.sub(r"<!--.*?-->", "", resp.text, flags=re.S)


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        html_text = fetch_html(CATEGORY_URL.format(page=page))
        new = 0
        for m in ITEM_PATTERN.finditer(html_text):
            pid = m.group(1)
            if pid in items:
                continue
            new += 1
            name = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", m.group(2))).strip()
            block = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", " ", m.group(3)))
            price_m = PRICE_PATTERN.search(block)
            items[pid] = {
                "pid": pid,
                "name": name,
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "sold_out": "SOLD OUT" in block.upper(),
            }
        if new == 0:
            break
        time.sleep(0.5)
    return list(items.values())


def fetch_description(pid: str) -> str | None:
    html_text = fetch_html(f"{BASE_URL}/?pid={pid}")
    html_text = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text))
    text = unicodedata.normalize("NFKC", text.replace("&#160;", " ").replace("&nbsp;", " "))
    start = text.find("ツイート")
    end = text.find("■ご案内")
    if start < 0 or end < 0:
        return None
    desc = text[start + len("ツイート"):end]
    desc = BOILERPLATE_PATTERN.sub("", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc[:400] or None


def build_record(item: dict) -> dict | None:
    name = item["name"]
    bottle_m = BOTTLE_PATTERN.search(name)
    if not bottle_m:
        return None  # ペットボトル入り珈琲豆以外(セット・BOX・飲料等)は対象外
    weight_g = int(bottle_m.group(1))
    base_name = re.sub(r"\s+", " ", BOTTLE_PATTERN.sub("", name)).strip()

    parsed = parse_product(base_name)
    if parsed["is_flavored"]:
        return None
    if parsed["category"] == "ブレンド" or "九重の蔵" in base_name:
        # 「九重の蔵」は商品説明に「スペシャルブレンド」と明記されている
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(base_name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, base_name)
        if not parsed["origin_country"]:
            for kw, country in ORIGIN_OVERRIDES.items():
                if kw in base_name:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break

    desc = fetch_description(item["pid"])

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "roast_selectable": False,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if item["sold_out"] else "販売中",
        "out_of_stock": item["sold_out"],
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if not BOTTLE_PATTERN.search(item["name"]):
            continue
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kugurimon.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kugurimon.json に出力しました")


if __name__ == "__main__":
    main()
