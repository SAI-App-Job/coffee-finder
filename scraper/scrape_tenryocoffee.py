# -*- coding: utf-8 -*-
"""
scrape_tenryocoffee.py

天領倉敷珈琲(https://www.tenryo-coffee.com/、岡山県倉敷市阿知2-7-19)の商品情報を取得する。
おちゃのこネット(Ocnk、独自ドメイン運用。tenryo-coffee.ocnk.net)。

【対象商品について】
実データ確認済み(2026-11-02): 全商品一覧(/product-list)21件のうち、ドリップバッグ各種・5個入りカフェバッグ・
ギフト箱・包装代・のし紙は対象外。残りのコーヒー豆11銘柄(ブレンド4・ストレート6・デカフェ1)を対象とする。
商品はすべて注文後焙煎のオーダー焙煎で、重量違いの並びはない。

【重量・価格について】
店の表記は「内容量:生豆重量180g(焙煎後は150g前後※焙煎度により異なる)」で、表示価格(1,500〜1,750円)は
生豆重量180g分の価格。weight_g には商品ページの表記どおり180(生豆基準)を登録する。
焙煎度(8段階)・挽き方は購入時にオプション選択する方式で、商品説明は「おすすめロースト」の内容。
roast_level にはこのおすすめローストを採用する。
在庫は商品ページの「カートに入れる」有無で判定する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "天領倉敷珈琲",
    "url": "https://www.tenryo-coffee.com/",
    "platform": "おちゃのこネット",
    "address": "岡山県倉敷市阿知2-7-19",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-11-02確認。robots.txtはGPTBot・Bytespider・TikTokSpider・meta-externalagentのみ全面禁止で、それ以外は制限なし。識別可能なUser-Agentを使用)",
    "source_note": "販売先 https://www.tenryo-coffee.com/ の全商品一覧(/product-list)と各商品ページ、特商法ページ(/info)を2026-11-02に確認。お知らせ最新は2026-08-30。価格は「生豆重量180g」(焙煎後は150g前後)基準のため、weight_gは生豆基準の180g。100g換算は生豆ベースで約830〜970円。ご注文後に焙煎するオーダー焙煎。実店舗(倉敷駅前商店街)あり",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://www.tenryo-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2
NON_BEAN = ("ドリップバッグ", "カフェバッグ", "ギフト", "包装", "のし", "セット", "詰め合わせ")
BLEND_NAMES = ("ブレンド",)
LIMITED_PREFIX = re.compile(r"^【(?:期間限定|数量限定)】\s*")


def fetch_html(url: str) -> str:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product-list"), "html.parser")
    items = []
    for cell in soup.select("li.list_item_cell"):
        a = cell.select_one("a.item_data_link")
        name_el = cell.select_one(".goods_name")
        price_el = cell.select_one(".selling_price .figure")
        if not (a and name_el and price_el):
            continue
        m = re.search(r"/product/(\d+)", a["href"])
        pm = re.search(r"([\d,]+)", price_el.get_text())
        if not (m and pm):
            continue
        items.append({
            "pid": m.group(1),
            "name": re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name_el.get_text(" ", strip=True))).strip(),
            "price": int(pm.group(1).replace(",", "")),
        })
    return items


def fetch_detail(pid: str) -> tuple[str | None, bool]:
    html_text = fetch_html(f"{BASE_URL}/product/{pid}")
    soup = BeautifulSoup(html_text, "html.parser")
    el = soup.select_one("div.item_desc_text")
    text = unicodedata.normalize("NFKC", el.get_text("\n", strip=True)) if el else None
    return text, "カートに入れる" in html_text


def main():
    records = []
    for item in list_items():
        if any(k in item["name"] for k in NON_BEAN):
            continue
        text, purchasable = fetch_detail(item["pid"])
        base = LIMITED_PREFIX.sub("", item["name"]).strip()
        is_blend = any(k in base for k in BLEND_NAMES)

        # 説明文: 先頭の紹介文のみ(「※商品説明は」以降は定型文)
        desc = None
        roast_level = None
        if text:
            head = text.split("※商品説明は")[0]
            lines = [l for l in head.split("\n") if l.strip()]
            desc = re.sub(r"\s+", " ", " ".join(lines))[:400] or None
            rm = re.search(r"おすすめロースト\(([^)]+)\)", text)
            roast_level = rm.group(1) if rm else None

        parsed = parse_product(base)
        blend_components = []
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
            for sentence in (text or "").split("※商品説明は")[0].split("\n"):
                for c in ("ブラジル", "コロンビア", "エチオピア", "インドネシア", "グアテマラ"):
                    if c in sentence and {"origin_country": c} not in blend_components:
                        blend_components.append({"origin_country": c})
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(base)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, base)
        if is_blend:
            parsed["processing_method"] = None
        elif not parsed["processing_method"] and text:
            pm = re.search(r"精選方法[:：]\s*(ウォッシュド|ナチュラル|スマトラ|ハニー)", text)
            parsed["processing_method"] = pm.group(1) if pm else extract_from_description(text)["processing_method"]
        decaf_process = None
        if "カフェインレス" in base or "デカフェ" in base:
            decaf_process = "マウンテンウォータープロセス(水抽出法)によりカフェインを除去" if "マウンテンウォーター" in (text or "") else None

        sold_out = not purchasable
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": base,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_level,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "decaf_process": decaf_process,
            "roast_selectable": True,
            "blend_components": blend_components,
            "price": item["price"],
            "weight_g": 180,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": f"{BASE_URL}/product/{item['pid']}",
        })

    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tenryocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tenryocoffee.json に出力しました")


if __name__ == "__main__":
    main()
