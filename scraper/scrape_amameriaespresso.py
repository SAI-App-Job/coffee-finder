# -*- coding: utf-8 -*-
"""
scrape_amameriaespresso.py

AMAMERIA ESPRESSO(アマメリアエスプレッソ、東京都品川区小山3-6-15 パークホームズ武蔵小山1F、
目黒区碑文谷・品川区西五反田にも店舗がある計3店のロースタリーカフェ)のオンラインショップ
(amameria.cart.fc2.com、FC2カート・UTF-8)から自家焙煎コーヒー豆の商品情報を取得する。

【対象商品について】
全件表示(/?ca=all、41件、30件/ページで2ページ。ページ番号は0始まりで /?ca=all&page=1 が2ページ目)のうち、
ダンクコーヒーバッグ(コーヒーバッグ)2件を除く豆を対象にする。同じ銘柄が 250g/500g(250g×2袋)/1000g(250g×4袋)の
重量違いで別商品として並ぶので、重量表記を除いた商品名でまとめ、最小重量の商品を代表1件とする
(ペニャス・ブランカス ゲイシャは100g、ラスフローレス ジャバは50g、それ以外は250g)。
商品名に「国名 ／ 農園名 …」の形があるものはシングルオリジン、国名の無いもの(グラッセ・ノワール・マロン・ルージュ・
シーズナルブレンド・ムーンリバーブレンド)はブレンド。
焙煎度は商品説明の【中深煎り】等の記載(同じ銘柄の別重量ページに書かれている場合はそれを利用)。記載が無い場合は null。
一覧に在庫切れ表示は無い(売り切れ表記があれば品切れとして扱う)。

robots.txt(amameria.cart.fc2.com): User-Agent:* で /cancel/ /setup/ /tools/ のみ Disallow(2026-10-25確認)。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "AMAMERIA ESPRESSO",
    "url": "https://amameria.cart.fc2.com/",
    "platform": "FC2カート",
    "address": "東京都品川区小山3-6-15 パークホームズ武蔵小山1F",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-25確認。/cancel/ /setup/ /tools/ のみ禁止)",
    "source_note": "オンラインショップの全件表示(https://amameria.cart.fc2.com/?ca=all、2ページ)を2026-10-25に確認。公式 https://www.amameria.com/about/ に『SmartRoaster/完全熱風式(Loring社)の焙煎機を使用』『ロースタリーカフェです』、/location/ に武蔵小山店(コーヒー豆販売)・碑文谷店・五反田食堂店の3店舗の所在地。住所は武蔵小山店。商品に日付表記は無く更新時期は不明(2024年に五反田食堂店開店の記載あり)",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://amameria.cart.fc2.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2

EXCLUDE_KEYWORDS = ["コーヒーバッグ", "ドリップバッグ", "セット", "ギフト"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ](?!\s*×)")
STRIP_PATTERN = re.compile(r"[　\s]*\d+\s*[gｇ][　\s]*(?:[（(][^）)]*[）)])?[　\s]*$")
ROAST_PATTERN = re.compile(r"【([^】]*煎り)】")
ROAST_IN_TEXT = re.compile(r"ローストは[^。]*?(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_listing() -> list[dict]:
    items, seen = [], set()
    for page in range(0, 10):
        if page:
            time.sleep(REQUEST_INTERVAL)
        html = fetch(f"{BASE_URL}/?ca=all&page={page}")
        blocks = re.findall(r'<li class="item_inner">(.*?)</li>', html, flags=re.S)
        found = False
        for li in blocks:
            m = re.search(r'class="name"><a href="(/ca\d+/(\d+)/)[^"]*">([^<]*)', li)
            if not m or m.group(2) in seen:
                continue
            seen.add(m.group(2))
            found = True
            price_m = re.search(r'class="price">\s*([\d,]+)\s*円', li)
            d = re.search(r'class="item_comment">(.*?)</dd>', li, flags=re.S)
            desc = re.sub(r"<[^>]+>", "", d.group(1)).strip() if d else ""
            items.append({
                "pid": m.group(2),
                "path": m.group(1),
                "title": re.sub(r"\s+", " ", m.group(3)).strip(),
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "desc": desc,
                "sold_out": bool(re.search(r"売り切れ|SOLD ?OUT|在庫切れ|品切れ", li, re.I)),
            })
        if not found:
            break
    return items


def build_record(group: list[dict]) -> dict:
    group.sort(key=lambda x: x["weight"])
    item = group[0]
    name = item["base"]
    is_blend = "／" not in name and "/" not in name
    parsed = parse_product(name)
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

    roast = None
    for g in [item] + group[1:]:
        m = ROAST_PATTERN.search(g["desc"]) or ROAST_IN_TEXT.search(g["desc"])
        if m:
            roast = m.group(1)
            break
    desc = ROAST_PATTERN.sub("", item["desc"]).strip() or None
    sold_out = item["sold_out"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight"],
        "stock_status": "一時的に品切れ" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}{item['path']}p-r-s/",
    }


def scrape_all_products() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for it in fetch_listing():
        title = it["title"]
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue
        wm = WEIGHT_PATTERN.search(title)
        if not wm:
            continue
        base = STRIP_PATTERN.sub("", title).strip()
        key = re.sub(r"[\s　,，､、]+", "", base).replace("二グセゲメダ", "ニグセゲメダ")
        it = dict(it, weight=int(wm.group(1)), base=re.sub(r"[　\s]+", " ", base))
        groups.setdefault(key, []).append(it)
    return [build_record(g) for g in groups.values()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_amameriaespresso.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_amameriaespresso.json に出力しました")


if __name__ == "__main__":
    main()
