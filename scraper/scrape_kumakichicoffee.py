# -*- coding: utf-8 -*-
"""
scrape_kumakichicoffee.py

自家焙煎コーヒーくまきち(公式 https://kumakichicoffee.wixsite.com/kumakichicoffee 、
通販 https://kumakichicoffee.square.site/、大阪府大阪市中央区上町1-26-14)の
商品情報を取得する。Square Online。

【店舗発見の経緯】
全国再調査(大阪府)の新規発掘で発見。公式サイトはWix、通販はSquare Online
(旧ネットショップ kumakichi.theshop.jp は「新ネットショップ(移転)」の告知のみで
商品なし)。

【取得方法について】
実データ確認済み(2026-10時点): Square Onlineの店頭ページ(SPA)はHTMLに価格を含まないが、
ストアフロントが内部で使う公開API
  /app/store/api/v28/editor/users/{user_id}/sites/{site_id}/products
がログイン不要でJSON(商品名・説明・価格・在庫・SKU)を返す。user_id/site_idは
トップページHTMLの `_W.Analytics` から取得する。商品詳細
(?include=skus,options)のSKUに「１００ｇ, 豆」のような重量×挽き方の組み合わせが
入っているため、最小重量(100g)のSKUの価格・在庫を採用する。

【robots.txtについて】
確認済み(2026-10時点): User-agent: * で /s/search・/s/cart/・/s/checkout/・
/store/checkout・/store/status・レビュー投稿ページのみDisallow、Crawl-delay: 5。
上記APIパスは対象外。本スクレイパーは識別可能な独自User-Agentを使用し、
Crawl-delayに従って5秒間隔でリクエストする。

【対象商品について】
全24商品(公開中)のうち、焙煎豆は「くまきちの『みちくさ』(ブレンド)」「ジワカ ナチュラル
(パプアニューギニア)」「イルガチェフェ ゲデブ(エチオピア)」の3商品のみ。
コーヒーバッグ(ドリップバッグ類)・おまかせ詰め合わせ(銘柄をお任せにするセット)・
器具(フレンチプレス・ミル)・洗剤・ボトル・紙袋・ステッカー・ギフト箱は除外。
商品ID(site_product_id)で対象を明示している。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "自家焙煎コーヒーくまきち",
    "url": "https://kumakichicoffee.square.site/",
    "platform": "Square Online",
    "address": "大阪府大阪市中央区上町1-26-14",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-10確認。決済・検索・レビュー投稿ページのみDisallow、"
                         "Crawl-delay: 5に従い5秒間隔。識別可能なUser-Agentを使用)",
}

STORE_URL = "https://kumakichicoffee.square.site"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SEC = 5

# 対象商品(site_product_id → (表示名, 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定)))
TARGET_PRODUCTS = {
    "8": ("くまきちの「みちくさ」 中煎り ver.38", "ブレンド", "中煎り"),
    "U3EDARA7C72XRF3T6DMNZK2O": ("ジワカ ナチュラル 中煎り パプアニューギニア", None, "中煎り"),
    "VX6WXFZXYO5SJINZ6ZNIDXCW": ("イルガチェフェ ゲデブ エチオピア 中煎り", None, "中煎り"),
}

USER_ID_PATTERN = re.compile(r"user_id:\s*'(\d+)'")
SITE_ID_PATTERN = re.compile(r"site_id:\s*'(\d+)'")
PROCESSING_PATTERN = re.compile(r"(?:精製方法|精選方法|生産処理|精製処理)\s*[:：]\s*([^\s、。]+)")


def get_json(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def html_to_text(html_text: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>|</div>", " ", html_text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def weight_from_sku_name(sku_name: str) -> int | None:
    m = re.search(r"(\d+)\s*g", unicodedata.normalize("NFKC", sku_name).lower())
    return int(m.group(1)) if m else None


def fetch_api_base() -> str:
    resp = requests.get(STORE_URL + "/", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    user_m = USER_ID_PATTERN.search(resp.text)
    site_m = SITE_ID_PATTERN.search(resp.text)
    if not user_m or not site_m:
        raise RuntimeError("user_id/site_idを取得できません(Square Online側の仕様変更の可能性)")
    return f"{STORE_URL}/app/store/api/v28/editor/users/{user_m.group(1)}/sites/{site_m.group(1)}/products"


def build_record(product: dict, sku_data: dict) -> dict | None:
    site_product_id = product["site_product_id"]
    name, category_override, roast_level = TARGET_PRODUCTS[site_product_id]

    # 最小重量のSKU(同一重量で複数ある場合は挽き方違いなので最初のもの=豆のまま)を採用
    skus = [(weight_from_sku_name(s["name"]), s) for s in sku_data["skus"]["data"]]
    skus = [(w, s) for w, s in skus if w is not None]
    min_weight = min(w for w, _ in skus) if skus else None
    chosen = [s for w, s in skus if w == min_weight] if skus else sku_data["skus"]["data"][:1]
    price = min(s["price"]["current"] for s in chosen)
    sold_out = all(s["sold_out"] for s in chosen)

    desc_text = html_to_text(product.get("short_description"))
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["grade"] = None
    elif not parsed["origin_country"]:
        detected = detect_country_name(name)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"

    processing = parsed["processing_method"]
    if not processing:
        pm = PROCESSING_PATTERN.search(desc_text)
        if pm:
            processing = normalize_processing_method(pm.group(1))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc_text[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": min_weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": product["absolute_site_link"],
    }


def scrape_all_products() -> list[dict]:
    api_base = fetch_api_base()
    time.sleep(CRAWL_DELAY_SEC)
    listing = get_json(f"{api_base}?page=1&per_page=200")["data"]
    by_site_id = {p["site_product_id"]: p for p in listing if p.get("visibility") == "visible"}

    records = []
    for site_product_id in TARGET_PRODUCTS:
        product = by_site_id.get(site_product_id)
        if not product:
            print(f"[warn] 対象商品が一覧に見つかりません(販売終了の可能性): {site_product_id}")
            continue
        time.sleep(CRAWL_DELAY_SEC)
        try:
            sku_data = get_json(f"{api_base}/{product['id']}?include=skus,options")["data"]
        except requests.RequestException as e:
            print(f"[warn] 商品詳細取得失敗: {site_product_id} ({e})")
            continue
        record = build_record(product, sku_data)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kumakichicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kumakichicoffee.json に出力しました")


if __name__ == "__main__":
    main()
