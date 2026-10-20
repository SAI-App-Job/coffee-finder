# -*- coding: utf-8 -*-
"""
scrape_imaginecoffee.py

IMAGINE COFFEE(イマジンコーヒー、北海道旭川市忠和5条4丁目11-15、運営 有限会社チックタック企画、2025-03開店の
コーヒースタンド)のBASE(imaginecafe.base.shop)の商品情報を取得する。

【販売先について】
BASE(imaginecafe.base.shop)は全24商品がすべてコーヒー豆(100g〜)。楽天市場店(imaginecoffee)は品数が少ないため、
品目が揃っているBASEを採用した。公式サイト imaginecoffee.shop はタイトルのみの簡易ページ。

【対象商品について】
全24商品が「100g〜」(100g/200g/300g/400gのバリエーション)の豆単品。各商品の最小重量=100gの価格
(`product:price:amount`)を代表とする。焙煎度は購入時に選択式(おすすめ焙煎のほか5段階)で、商品ページ記載の
「おすすめの焙煎度」を roast_level に入れ、roast_selectable=True とした。
 - 「【ブランデー熟成樽】」2商品(アカテナンゴ・オカパ)は、ブランデー樽で熟成した生豆(グレード表記「バレルエイジド」)。
   果実・ハーブ・香料を加える製法ではないため登録対象としたが、post_processing_tags に反映する。
 - 産地国は商品説明に明記があるものを採用。説明に国名が無い銘柄(エル・ススピロ農園/エル・ロブラル農園/スカイヒル コプロカWS)は null。
   ンゴロンゴロ(タンザニア北部の地区名)のみ地名からタンザニアとした。

【robots.txtについて】
User-Agent: * は Allow: /(Disallow は /cart/ /web_cart/ /shops/ 等)。python-requests/curl 等は個別にDisallowのため、
識別可能な独自User-Agentを使い、5秒間隔で取得する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "イマジンコーヒー",
    "url": "https://imaginecafe.base.shop/",
    "platform": "BASE",
    "address": "北海道旭川市忠和5条4丁目11-15",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(User-agent: * は Allow: /、/cart/ 等のみDisallow。python-requests/curl は名指しで禁止のため識別可能なUser-Agentを使用)",
    "source_note": "BASE(https://imaginecafe.base.shop/)の全商品(24点)と各商品ページを2026-10-20に確認。"
                   "ショップトップに「発送当日に焙煎した豆をお届け」、特商法(有限会社チックタック企画)・食べログ(2025-03-21開店、旭川市忠和5条4丁目11-15、営業10:00-18:00)で実店舗を確認",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://imaginecafe.base.shop"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 5

# (商品ID, 産地国(説明に明記なしはNone))
ITEMS = [
    ("117733512", "タンザニア"),
    ("117733058", "コスタリカ"),
    ("117595330", "パプアニューギニア"),
    ("117595235", "グアテマラ"),
    ("117595088", "パナマ"),
    ("117594743", "ケニア"),
    ("117594631", "ケニア"),
    ("117594488", "エチオピア"),
    ("117594374", "グアテマラ"),
    ("117594202", "東ティモール"),
    ("117594110", "ブラジル"),
    ("117593998", "エチオピア"),
    ("117593860", "エチオピア"),
    ("117589244", "コスタリカ"),
    ("117589135", "コスタリカ"),
    ("117588428", "タイ"),
    ("117588263", "パプアニューギニア"),
    ("117273235", "ペルー"),
    ("109750456", "インドネシア"),
    ("109751452", None),
    ("109751415", "タンザニア"),
    ("103119888", "コスタリカ"),
    ("109750198", None),
    ("109750143", None),
]

PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"おすすめの焙煎度：(\S+)")
BREW_NOISE = ("※画像はイメージです。",)


def build_record(item_id: str, origin: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=HEADERS, timeout=60)
    if resp.status_code != 200:
        print(f"[warn] 取得失敗 {item_id} HTTP {resp.status_code}")
        return None
    html_text = resp.content.decode("utf-8")
    soup = BeautifulSoup(html_text, "html.parser")
    title = re.sub(r"\s*\|\s*IMAGINE COFFEE$", "", soup.title.get_text().strip())
    name = re.sub(r"\s*100g〜$", "", re.sub(r"\s+", " ", title.replace("　", " "))).strip()
    price_m = PRICE_PATTERN.search(html_text)
    if not price_m:
        print(f"[warn] 価格取得失敗 {item_id} {name}")
        return None
    pu = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(pu) and pu.group(1) == "unpurchasable"

    txt = soup.get_text("\n", strip=True)
    gm = re.search(r"Grade\n(.+?)\nFlavor\n(.+?)\n(?:おすすめの焙煎度|※|ー PROFILE)", txt, re.S)
    grade_label = gm.group(1).strip() if gm else None
    flavor = re.sub(r"\s+", "", gm.group(2)) if gm else None
    rm = ROAST_PATTERN.search(txt)
    roast = rm.group(1) if rm else None
    pm = re.search(r"ー PROFILE ー\n(.*?)\n※", txt, re.S)
    profile = re.sub(r"\s+", " ", pm.group(1)).strip() if pm else None
    notes = "、".join(x for x in (flavor,) if x)
    if profile:
        notes = (notes + " / " if notes else "") + profile
    notes = notes[:400] or None

    parsed = parse_product(name)
    parsed = apply_category_hint_fallback(parsed, name)
    parsed["category"] = "ストレート"
    parsed["origin_country"] = origin
    parsed["origin_source"] = "description" if origin else None
    tags = list(parsed["post_processing_tags"])
    if grade_label == "バレルエイジド" and "バレルエイジド" not in tags:
        tags.append("バレルエイジド")
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
        "roast_selectable": True,
        "roast_hint": None,
        "flavor_notes": notes,
        "farm_note": None,
        "post_processing_tags": tags,
        "blend_components": [],
        "price": int(price_m.group(1)),
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list:
    records = []
    for i, (item_id, origin) in enumerate(ITEMS):
        if i:
            time.sleep(INTERVAL)
        try:
            rec = build_record(item_id, origin)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_id} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_imaginecoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_imaginecoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["stock_status"], r["post_processing_tags"])


if __name__ == "__main__":
    main()
