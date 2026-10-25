# -*- coding: utf-8 -*-
"""
scrape_archecoffee.py

ARCHE COFFEE(アルケーコーヒー、https://archecoffee.com/、愛知県岡崎市福岡町東後田25-9)の
商品情報を取得する。Shopify。

【店舗発見の経緯】
愛知県の未登録店発掘(disc3)で発見。2024年5月に岡崎市で実店舗オープン(アクセスページで
確認)。公式に「自家焙煎」の語はないが、「焙煎を探求する」「発送の直前に焙煎をした新鮮な
コーヒー」(FAQ)「ROAST DATE=焙煎日」と記載。焙煎機の機種・店内焙煎の第三者根拠は未確認。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json` 全16〜17商品のうち、コーヒー豆13〜14品を候補とし、
次を除外した。
- ドリップバッグセット、コーヒー定期便(セット・サブスク)
- コロンビア ロスパティオス ゲイシャピーチハニー(説明文に「インフューズドコーヒー」と明記)
- フルーツミックスブレンド【復刻】、コロンビア ラ・フロリダ ハイビスカスウォッシュド(2026-10-26追加。
  桃やハイビスカスの強い風味で、インフューズド豆の可能性があるが説明文では確認できないため、安全側で除外)
各商品は「豆 / 粉」×重量の組合せ。豆のままの最小重量(100gまたは150g)の価格を代表とする。
焙煎度は説明文に明記のある商品のみ設定(他はNone)。

【robots.txtについて】
User-agent: * は /cart /checkout /account 等のみ制限(2026-10確認)。/products.json は禁止されていない。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ARCHE COFFEE",
    "url": "https://archecoffee.com/",
    "platform": "Shopify",
    "address": "愛知県岡崎市福岡町東後田25-9",
    "prefecture": "愛知県",
    "robots_txt_status": "許可(2026-10確認。/cart・/checkout・/account等以外は制限なし)",
    "source_note": "Shopify /products.json を2026-10-21に取得(updated_at 2026-10-21)。住所は特商法表記(/policies/legal-notice)とアクセスページ(2024年5月オープン、営業10:00-17:00・月火定休)で確認。自家焙煎の明文なし(FAQ「発送の直前に焙煎」・ROAST DATE表記・about「焙煎を探求する」のみ。焙煎機は未確認)",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://archecoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")

# 除外するhandle(セット・定期便・インフューズド等)
EXCLUDE_HANDLES = {
    "ドリップバッグセット",
    "コーヒー",
    "コロンビア-ロスパティオス-ゲイシャピーチハニー",
    "フルーツミックスブレンド-復刻",
    "コロンビア-ラ-フロリダ-ハイビスカスウォッシュド",
}
# 産地を商品名から判定できない商品
ORIGIN_OVERRIDES = {"ネパール-カーブレパランチョーク-ナチュラル": "ネパール"}
# ブレンドとして扱う商品(説明文・タグに基づく)
BLEND_HANDLES = {"イエヤス", "三河ブラック"}
# 説明文に焙煎度の明記がある商品のみ
ROASTS = {
    "デカフェ-エチオピア-イルガチェフ-マウンテンウォーター-ウォッシュド-g2": "中浅煎り",
    "ブラジル-ボンジャルディン-パルプドナチュラル-ダークロースト": "深煎り",
    "三河ブラック": "深煎り",
    "イエヤス": "深煎り",
    "メキシコ-coe-687-94モモコモ-ウォッシュド": "極浅煎り",
}


def clean_desc(html: str) -> str | None:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    text = text.split("※ポスト投函商品")[0]
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400] or None


def scrape_all_products() -> list[dict]:
    resp = None
    for attempt in range(6):
        resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code != 429:
            break
        # 429は回避せず、Retry-After(秒)だけ待って間隔を空けて再試行する
        time.sleep(int(resp.headers.get("Retry-After", "60")) + 30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p["handle"] in EXCLUDE_HANDLES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        is_decaf = title.startswith("【デカフェ】")
        if is_decaf:
            title = "デカフェ " + title.replace("【デカフェ】", "").strip()

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            if not vt.startswith("豆"):
                continue
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        parsed = parse_product(title)
        if p["handle"] in BLEND_HANDLES or "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if not parsed["origin_country"] and p["handle"] in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[p["handle"]]
                parsed["origin_source"] = "raw_name"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": ROASTS.get(p["handle"]) or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": clean_desc(p.get("body_html")),
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_archecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_archecoffee.json に出力しました")


if __name__ == "__main__":
    main()
