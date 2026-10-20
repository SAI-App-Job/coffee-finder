# -*- coding: utf-8 -*-
"""
scrape_yabucoffee.py

やぶ珈琲(株式会社やぶ珈琲、大阪市平野区喜連東3-13-4の喜連瓜破本店と東住吉区駒川の駒川店の2店舗、
ご注文後に生豆から少量焙煎する珈琲豆専門店)の公式オンラインショップ
(onlineshop.yabucoffee.com、Shopify)のコーヒー豆の商品情報を取得する。

【販売先について】
楽天市場店(www.rakuten.co.jp/yabucoffee/)にも出店しているが、公式オンラインショップは
スペシャルティ・期間限定ロット・デカフェ・ブレンド約40銘柄の豆(200g)が揃っているため、
こちらを採用(楽天はドリップバッグ・ギフトが中心)。

【実店舗・自家焙煎の根拠】
https://www.yabucoffee.com/aboutyabucoffee/ に「ご注文後に生豆から焙煎」「当店ではガス火による直火型
ロースターで240gの少量から丁寧に焙煎しております」、https://www.yabucoffee.com/access/ に店舗
(喜連瓜破本店・駒川店)の住所・営業時間、https://www.yabucoffee.com/ourcompany/ に所在地
「大阪府大阪市平野区喜連東3-13-4 薮内マンション1階」「2014年10月 珈琲豆専門店やぶ珈琲として創業」と記載。

【対象商品について】
Shopifyの`/products.json`のうち、バリエーションに「豆」(豆のまま。他は「粉」「生豆」)がある単品を対象とする。
全商品の内容量は「200グラム」(商品ページの商品情報欄)で、バリエーションに重量選択は無い。
価格は「豆」バリエーション(税込)。焙煎度は商品情報に記載がないため None とする。
除外: ドリップバッグ・セット・ギフト・お試し・缶・ボトル(リキッド)・カフェオレベース・水出しパック等。
robots.txt は Disallow が /admin・/cart・/checkout 等のみ(/products.json は禁止されていない)。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "やぶ珈琲",
    "url": "https://onlineshop.yabucoffee.com/",
    "platform": "Shopify",
    "address": "大阪府大阪市平野区喜連東3-13-4",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-20確認。Disallowは/admin・/cart・/checkout等のみ。/products.jsonは禁止されていない)",
    "source_note": "公式オンラインショップ(https://onlineshop.yabucoffee.com/)の/products.jsonを2026-10-20に確認。"
                   "実店舗(喜連瓜破本店・駒川店の2店舗)・ご注文後の少量自家焙煎は https://www.yabucoffee.com/aboutyabucoffee/ ・/access/ ・/ourcompany/ で確認。"
                   "楽天市場店(https://www.rakuten.co.jp/yabucoffee/)にも出店しているが、豆の品目が揃う公式ショップを採用",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://onlineshop.yabucoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

EXCLUDE_KEYWORDS = ["セット", "ギフト", "お試し", "ドリップ", "缶", "ボトル", "カフェオレベース", "水出し"]
ORIGIN_OVERRIDE = {"yabucoffee14": "アメリカ(ハワイ)"}  # ハワイコナ
DECAF_PATTERNS = [
    (re.compile(r"マウンテンウォーター"), "マウンテンウォータープロセス"),
    (re.compile(r"スイスウォーター"), "スイスウォータープロセス"),
    (re.compile(r"ウォータープロセス|水抽出"), "ウォータープロセス"),
]


def body_text(p: dict) -> str:
    b = re.sub(r"<style.*?</style>", "", p.get("body_html") or "", flags=re.DOTALL)
    b = re.sub(r"<br\s*/?>|</p>|</tr>|</li>|</h\d>|</div>", "\n", b)
    b = re.sub(r"<[^>]+>", "", b)
    return re.sub(r"\n\s*\n+", "\n", html.unescape(b)).strip()


def parse_weight(text: str) -> int | None:
    m = re.search(r"内容量\s*\n?\s*(\d+)\s*(?:グラム|g)", text)
    return int(m.group(1)) if m else None


def flavor_notes(text: str) -> str | None:
    head = text.split("名称")[0]
    lines = [ln.strip() for ln in head.split("\n") if ln.strip()]
    good = [ln for ln in lines if "。" in ln and len(ln) >= 12]
    return " ".join(good[:2])[:200] or None


def build_record(p: dict) -> dict | None:
    handle = p["handle"]
    bean = [v for v in p["variants"] if (v.get("title") or "").strip() == "豆"]
    if not bean:
        return None
    title = re.sub(r"\s+", " ", p["title"]).strip()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    name = re.sub(r"^期間限定\s*", "", title)
    text = body_text(p)
    weight = parse_weight(text)
    v = bean[0]

    is_blend = "ブレンド" in name
    is_decaf = "カフェインレス" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        origin = ORIGIN_OVERRIDE.get(handle)
        if not origin:
            m = re.search(r"[（(]\s*([^（()）]+?)産?\s*[）)]", name)
            origin = detect_country_name(m.group(1)) if m else None
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "shop_attribute"
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
    decaf_process = None
    if is_decaf:
        for pat, canonical in DECAF_PATTERNS:
            if pat.search(text):
                decaf_process = canonical
                break
    available = bool(v.get("available"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "decaf_process": decaf_process,
        "flavor_notes": flavor_notes(text),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(float(v["price"])),
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE_URL}/products/{handle}",
    }


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=60)
    resp.raise_for_status()
    records = []
    for p in resp.json().get("products", []):
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_yabucoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yabucoffee.json に出力しました")


if __name__ == "__main__":
    main()
