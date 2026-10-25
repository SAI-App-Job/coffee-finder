# -*- coding: utf-8 -*-
"""
scrape_glaubellcoffee.py

GLAUBELL COFFEE(グラウベルコーヒー、東京都世田谷区代田5-7-9 1F、店主 狩野知代氏の焙煎店)の
ネットショップ(glaubell.shop-pro.jp、カラーミーショップ・EUC-JP)から商品情報を取得する。

【対象商品について】
商品カテゴリのうち「ストレート」(22件)・「ブレンド」(8件)・「スペシャルセレクション」(11件)の豆を対象にする。
除外: ●お買い得商品(「お任せ」の毎回内容が変わる詰め合わせ)、ドリップバッグ、定期便、コーヒー器具&グッズ、書籍&CD、
自家焙煎倶楽部(生豆販売)、セットもの。
同じ銘柄が 100g/200g/250g/500g の重量違いで別商品として並ぶため、重量表記を除いた商品名(焙煎度表記を含む)で
まとめ、最小重量の商品を代表1件とする(エチオピア ニグセ・ゲメダは100g、ブレンド代田深煎は200g、その他は250g)。
商品名の末尾に焙煎度(浅煎/中浅煎/中煎/中深煎/深煎)が付いている。名前中の「SOLD OUT」表示は一覧のSOLD OUTで判定する
(代表の最小重量商品がSOLD OUTなら品切れ)。一覧に商品名・税込価格・SOLD OUTが出るため詳細ページは取得しない。

robots.txt(https://glaubell.shop-pro.jp/robots.txt): User-agent:* で /secure/ と /cart/ のみ Disallow(2026-10-25確認)。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "GLAUBELL COFFEE",
    "url": "https://glaubell.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "東京都世田谷区代田5-7-9 1F",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-25確認。/secure/ と /cart/ のみ禁止)",
    "source_note": "ネットショップのカテゴリ(ストレート・ブレンド・スペシャルセレクション)を2026-10-25に確認。住所は公式 https://glaubell.net/ のACCESS(〒155-0033)。公式サイトに『自家焙煎』の語は無く、自家焙煎の根拠はウォーカープラス記事(https://www.walkerplus.com/article/1308415/)ほかの外部記事。公式トップのお品書きは2026/10/16〜18、価格改定は2024.9.1〜",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://glaubell.shop-pro.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
CATEGORIES = ["863995", "863996", "1731037"]  # ストレート / ブレンド / スペシャルセレクション

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
ROAST_PATTERN = re.compile(r"(中浅煎|中深煎|浅煎|中煎|深煎)り?")
ROAST_MAP = {"浅煎": "浅煎り", "中浅煎": "中浅煎り", "中煎": "中煎り", "中深煎": "中深煎り", "深煎": "深煎り"}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    time.sleep(REQUEST_INTERVAL)
    return resp.text


def fetch_listing() -> list[dict]:
    items, seen = [], set()
    for cbid in CATEGORIES:
        page = 1
        while True:
            url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0" + (f"&page={page}" if page > 1 else "")
            html = fetch(url)
            for b in re.split(r'<div class="item_box', html)[1:]:
                n = re.search(r'class="item_name">\s*<a[^>]*pid=(\d+)[^>]*>(.*?)</a>', b, flags=re.S)
                p = re.search(r'class="item_price">(.*?)</p>', b, flags=re.S)
                pm = re.search(r"([\d,]+)円", p.group(1)) if p else None
                if not n or not pm or n.group(1) in seen:
                    continue
                seen.add(n.group(1))
                items.append({
                    "pid": n.group(1),
                    "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", n.group(2))).strip(),
                    "price": int(pm.group(1).replace(",", "")),
                    "sold_out": bool(re.search(r"SOLD OUT", b)),
                })
            if f"page={page + 1}" in html:
                page += 1
            else:
                break
    return items


def clean_name(title: str):
    """(重量g, 焙煎度, 重量を除いた商品名, 同一銘柄判定キー) を返す。"""
    wm = WEIGHT_PATTERN.search(title)
    weight = int(wm.group(1)) if wm else None
    rm = ROAST_PATTERN.search(title)
    roast = ROAST_MAP.get(rm.group(1)) if rm else None
    name = WEIGHT_PATTERN.sub(" ", title)
    name = re.sub(r"[　\s]+", " ", name).strip()
    key = re.sub(r"[\s　【】\[\]]+", "", name)
    key = re.sub(r"深煎り$", "深煎", key)
    return weight, roast, name, key


def build_record(group: list[dict]) -> dict:
    group.sort(key=lambda x: x["weight"])
    it = group[0]
    name = it["name"]
    # 商品名の末尾の焙煎度表記は roast_level に分けるが、同名で焙煎度違いの銘柄を区別するため名前にも残す
    parsed = parse_product(name)
    is_blend = "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": it["roast"],
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "一時的に品切れ" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": f"{BASE_URL}/?pid={it['pid']}",
    }


def scrape_all_products() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for it in fetch_listing():
        weight, roast, name, key = clean_name(it["title"])
        if weight is None:
            continue
        it = dict(it, weight=weight, roast=roast, name=name)
        groups.setdefault(key, []).append(it)
    return [build_record(g) for g in groups.values()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_glaubellcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_glaubellcoffee.json に出力しました")


if __name__ == "__main__":
    main()
