# -*- coding: utf-8 -*-
"""
scrape_hokkoukan.py

自家焙煎珈琲 旭川北珈館(北海道旭川市北門町17丁目2159-155、楽天市場店
www.rakuten.co.jp/hokkoukan)の商品情報を取得する。楽天市場(item.rakuten.co.jp)。

【住所について】
楽天市場の会社概要(www.rakuten.co.jp/hokkoukan/info.html)で実データ確認済み(2026-10時点):
「〒070-0825 北海道旭川市北門町17-2159-155」。

【文字コードについて】
店舗トップ(www.rakuten.co.jp)はUTF-8だが、商品・カテゴリページ(item.rakuten.co.jp)は
Content-Typeで「charset=EUC-JP」と宣言され、実際にEUC-JPで返る(UTF-8として読むと文字化け
する)。そのため宣言された文字コードに従って復号する。

【対象商品について】
実データ確認済み(2026-10時点): ショップカテゴリ「ストレートCOFFEE一覧」(c/0000000101)・
「【北珈館ブレンド】」(100)・「季節の北珈館ブレンド」(141)・「デカフェ」(117)・
「アイスコーヒー豆」(109)の商品。タイトルが「<銘柄名> 100g/シティロースト/…【自家焙煎珈琲】」
形式の100g袋が対象で、「【500g】…(250g×2袋)」のお得用パック・お試しセット・ペーパー
フィルター等は除外し、銘柄ごとに最小重量(100g)を代表とする。「アイスコーヒー豆」(フレンチ
ロースト)は焙煎豆のため対象に含める(商品名に「【アイスコーヒー豆】」を残して区別する)。

【商品データの取得元について】
商品ページ・カテゴリページには`<script type="application/json">`のJSON(api.data.itemInfoSku)が
埋め込まれ、タイトル・税込価格(taxIncludedPrice。期間限定の特別価格はその価格を採用)・在庫数
(purchaseInfo.newPurchaseSku.quantity。0なら完売)・商品説明(newProductDescription)が入っている。
北珈館ブレンドK/S等は1つのページに複数商品(各々別のJSON)が載る形式のため、ページ内の全JSONを
読み、取得済みの商品番号は再取得しない。商品説明末尾のスペック表(原産国・産地名・農園・規格・
精選方法等)から精選方法・農園情報を補う。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "自家焙煎珈琲 旭川北珈館",
    "url": "https://www.rakuten.co.jp/hokkoukan/",
    "platform": "楽天市場",
    "address": "北海道旭川市北門町17丁目2159-155",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
}

SHOP_ID = "hokkoukan"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
CATEGORY_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/c/" + "{cid}/"
CATEGORY_IDS = ["0000000101", "0000000100", "0000000141", "0000000117", "0000000109"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 0.5
EXCLUDE_KEYWORDS = ("セット", "福袋", "お試し", "フィルター", "ドリップバッグ", "ドリップバック", "ギフト",
                    "×2袋", "x2袋", "各250g", "【500g】", "【1kg】", "まとめ買い")

JSON_BLOCK_PATTERN = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.S)
LINK_PATTERN = re.compile(rf"item\.rakuten\.co\.jp/{SHOP_ID}/([\w-]+)/")
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.I)
LOCAL_ORIGINS = {"ネパール": "ネパール", "マラウィ": "マラウイ", "マラウイ": "マラウイ", "キューバ": "キューバ", "バリ": "インドネシア"}
SPEC_LABELS = ("名称", "原産国", "産地名", "農園", "業態", "規格", "品種", "標高", "収穫期", "精選方法")


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(5 * (attempt + 1))
    # 宣言された文字コード(EUC-JP)に従う。宣言が無い場合のみ推定
    if "charset" not in resp.headers.get("content-type", "").lower():
        resp.encoding = resp.apparent_encoding
    return resp


def parse_page(html_text: str) -> dict[str, dict]:
    """ページ内のJSON(itemInfoSku)をすべて読み、商品番号->itemInfoSkuの辞書を返す。"""
    found: dict[str, dict] = {}
    for m in JSON_BLOCK_PATTERN.finditer(html_text):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        sku = ((data.get("api") or {}).get("data") or {}).get("itemInfoSku")
        if sku and sku.get("manageNumber") and sku["manageNumber"] not in found:
            found[sku["manageNumber"]] = sku
    return found


def collect_items() -> dict[str, dict]:
    items: dict[str, dict] = {}
    codes: list[str] = []
    for cid in CATEGORY_IDS:
        resp = fetch(CATEGORY_URL.format(cid=cid))
        if resp.status_code != 200:
            print(f"[warn] カテゴリ取得失敗: {cid} (HTTP {resp.status_code})")
            continue
        items.update({k: v for k, v in parse_page(resp.text).items() if k not in items})
        for c in dict.fromkeys(LINK_PATTERN.findall(resp.text)):
            if c not in ("c", "s") and c not in codes:
                codes.append(c)
        time.sleep(REQUEST_INTERVAL)
    for code in codes:
        if code in items:
            continue
        try:
            resp = fetch(ITEM_URL.format(code=code))
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {code} ({e})")
            continue
        found = parse_page(resp.text) if resp.status_code == 200 else {}
        if code not in found:
            print(f"[warn] 商品情報なし(エラーページ等): {code}")
        for k, v in found.items():
            items.setdefault(k, v)
        time.sleep(REQUEST_INTERVAL)
    return items


def clean_description(html_text: str) -> tuple[str, dict]:
    """説明HTMLから、本文テキストとスペック表(原産国・精選方法等)の辞書を作る。"""
    html_text = re.sub(r"<!--▼▼今月のコーヒーinfo▼▼-->.*?<!--▲▲今月のコーヒーinfo▲▲-->", "", html_text, flags=re.S)
    text = BeautifulSoup(html_text, "html.parser").get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    spec: dict[str, str] = {}
    for i, ln in enumerate(lines[:-1]):
        if ln in SPEC_LABELS and ln not in spec:
            spec[ln] = lines[i + 1]
    body_lines = []
    for ln in lines:
        if ln == "名称":
            break
        body_lines.append(ln)
    return " ".join(body_lines), spec


def build_record(code: str, sku: dict) -> dict | None:
    raw_title = unicodedata.normalize("NFKC", sku.get("title") or "")
    if not raw_title or any(k in raw_title for k in EXCLUDE_KEYWORDS):
        return None
    wm = WEIGHT_PATTERN.search(raw_title)
    if not wm:
        return None
    weight = int(round(float(wm.group(1)) * (1000 if wm.group(2).lower() == "kg" else 1)))
    name = re.sub(r"\s+", " ", raw_title[:wm.start()]).strip()
    after = raw_title[wm.end():]
    if not name or "自家焙煎珈琲" not in raw_title:
        return None

    desc_html = (sku.get("pcFields") or {}).get("newProductDescription") or sku.get("newProductDescription") or ""
    body, spec = clean_description(desc_html)
    flavor = re.sub(r"\s+", " ", body)[:400] or None

    parsed = parse_product(name)
    crumbs = [b.get("name", "") for b in (sku.get("breadcrumbs") or {}).get("shopCategoryBreadcrumbs", [])]
    is_blend = "ブレンド" in name or any("ブレンド" in c for c in crumbs)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(name) or detect_country_name(spec.get("原産国", ""))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name" if detect_country_name(name) else "description"
        parsed = apply_category_hint_fallback(parsed, " ".join(crumbs))
        if not parsed["origin_country"]:
            # coffee_parserの国名辞書に無い産地(ネパール・マラウィ・キューバ・バリ島)を、商品名→
            # スペック表の原産国→最初のカテゴリ名(国名)の順に補う
            for src, text in (("raw_name", name), ("description", spec.get("原産国", "")),
                              ("category_hint", crumbs[0] if crumbs else "")):
                hit = next((c for kw, c in LOCAL_ORIGINS.items() if kw in text), None)
                if hit:
                    parsed["origin_country"], parsed["origin_source"] = hit, src
                    break
    processing = parsed["processing_method"]
    if not processing and not is_blend and spec.get("精選方法"):
        processing = detect_processing_method(spec["精選方法"])

    roast = parse_product(after)["roast_level"]
    farm = " ".join(v for v in (spec.get("産地名"), spec.get("農園")) if v) or None

    qty = (sku.get("purchaseInfo") or {}).get("newPurchaseSku", {}).get("quantity")
    sold_out = (qty is not None and qty <= 0 and not sku.get("unlimitedInventoryFlag")) or bool(sku.get("hideItem"))
    price = sku.get("taxIncludedPrice")
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
        "roast_hint": roast,
        "flavor_notes": flavor,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(round(price)) if price else None,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list[dict]:
    best: dict[str, dict] = {}
    for code, sku in collect_items().items():
        rec = build_record(code, sku)
        if not rec or rec["price"] is None:
            continue
        k = re.sub(r"\s+", "", rec["raw_name"])
        if k not in best or rec["weight_g"] < best[k]["weight_g"]:
            best[k] = rec
    return list(best.values())


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hokkoukan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hokkoukan.json に出力しました")


if __name__ == "__main__":
    main()
