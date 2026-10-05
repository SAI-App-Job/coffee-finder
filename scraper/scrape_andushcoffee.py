# -*- coding: utf-8 -*-
"""
scrape_andushcoffee.py

京の珈琲豆処 アンダッシュコーヒー(グルメ館 &'coffee、京都府京都市西京区桂下豆田町41-23)の
楽天市場店(www.rakuten.co.jp/andushcoffee)の商品情報を取得する。
楽天市場(item.rakuten.co.jp、UTF-8)。公式サイト(gurumekan.jp)ではなく楽天店の商品
ページから取得する(依頼の方針どおり)。

【取得方法】
楽天市場のrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止で、店舗カテゴリ・商品ページは
通常のGETで取得できる。「グラム数から探す」カテゴリ(200g=0000000242、400g=243、
800g=244、1200g=245。各カテゴリは1ページに全件が載る)から商品コードを集め、各商品ページの
itemprop="price"(税込)・itemprop="availability"・title・説明文(span.item_desc)を読む。
サーバーが遅く、一時的に503を返すことがあるため、リトライと待機を入れる。

【対象商品について】
商品名は「<銘柄> 200g <焙煎度> 送料込み 珈琲豆…」の形式で、同一銘柄が200g/400g/800g/
1200g(一部300g)の別商品として並ぶため、銘柄ごとに最小重量の商品を代表とする。
除外: セット・福袋・お試し・アソート・トリオ・ドリップバッグ・ギフト・ラッピング。
価格は税込で、送料込み(メール便)の表記。焙煎度は商品名の「中煎り」「中深煎り」「深煎り」
「ハイロースト」「シティロースト」等から取る(「やや深煎り」はroast_hintのみ保持しroast_levelはnull)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (parse_product, apply_category_hint_fallback, detect_country_name,
                           detect_processing_method)

SHOP_INFO = {
    "name": "アンダッシュコーヒー",
    "url": "https://www.rakuten.co.jp/andushcoffee/",
    "platform": "楽天市場",
    "address": "京都府京都市西京区桂下豆田町41-23",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
}

SHOP_ID = "andushcoffee"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
CATEGORY_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/c/" + "{cid}/"
CATEGORY_IDS = ["0000000242", "0000000243", "0000000244", "0000000245"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 0.5
EXCLUDE_KEYWORDS = ("セット", "福袋", "お試し", "アソート", "トリオ", "ドリップバッグ", "ドリップバック",
                    "ギフト", "ラッピング", "詰め合わせ", "詰合せ")
EXCLUDE_CODE_PREFIXES = ("gift", "dripbag", "monthlyset", "otameshi", "andush-assort", "organic-assort")

WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", re.I)
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')
AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
COARSE_ROASTS = (
    ("極深煎り", re.compile(r"極深煎り")),
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り")),
    ("中煎り", re.compile(r"中煎り")),
    ("深煎り", re.compile(r"(?<!やや)深煎り")),
)


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(5 * (attempt + 1))
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp


def list_codes() -> list[str]:
    codes: list[str] = []
    for cid in CATEGORY_IDS:
        resp = fetch(CATEGORY_URL.format(cid=cid))
        for c in dict.fromkeys(re.findall(rf"item\.rakuten\.co\.jp/{SHOP_ID}/([\w-]+)/", resp.text)):
            if c != "c" and c not in codes and not c.startswith(EXCLUDE_CODE_PREFIXES):
                codes.append(c)
        time.sleep(REQUEST_INTERVAL)
    return codes


def parse_item(code: str) -> dict | None:
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    title = unicodedata.normalize("NFKC", soup.title.get_text(strip=True)) if soup.title else ""
    title = title.replace("【楽天市場】", "")
    title = title.split("：京の珈琲豆処")[0].strip()
    wm = WEIGHT_PATTERN.search(title)
    # 商品名末尾の宣伝文句(「プレゼント ギフト」等)で誤除外しないよう、重量表記までを判定対象にする
    if not title or not wm or any(k in title[:wm.end()] for k in EXCLUDE_KEYWORDS):
        return None
    weight = int(round(float(wm.group(1)) * (1000 if wm.group(2).lower() == "kg" else 1)))
    name = title[:wm.start()]
    name = re.sub(r"^[&＆´́'’\s]+", "", name)
    name = re.sub(r"^(残僅か|残りわずか|数量限定)\s*", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return None
    after = title[wm.end():]
    desc_el = soup.select_one("span.item_desc") or soup.select_one(".item_desc")
    desc = unicodedata.normalize("NFKC", desc_el.get_text("\n", strip=True)) if desc_el else ""
    price_m = PRICE_PATTERN.search(html_text)
    avail_m = AVAIL_PATTERN.search(html_text)
    return {
        "code": code, "title": title, "name": name, "weight": weight, "after": after, "desc": desc,
        "price": int(price_m.group(1)) if price_m else None,
        "sold_out": bool(avail_m) and avail_m.group(1) != "InStock",
    }


def build_record(it: dict) -> dict:
    name, desc, after = it["name"], it["desc"], it["after"]
    is_blend = "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        c = detect_country_name(name)
        if c:
            parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_level, roast_hint = None, None
    for label, pat in COARSE_ROASTS:
        m = pat.search(after)
        if m:
            roast_level, roast_hint = label, m.group(0)
            break
    if not roast_level:
        rl = parse_product(after)["roast_level"]
        if rl:
            roast_level, roast_hint = rl, rl
    if not roast_level and "やや深煎り" in after:
        roast_hint = "やや深煎り"

    lines = [ln.strip() for ln in desc.split("\n") if ln.strip()]
    flavor = re.sub(r"\s+", " ", " ".join(lines))[:300] or None
    processing = None if is_blend else (parsed["processing_method"] or detect_processing_method(f"{it['title']} {desc[:300]}"))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": ITEM_URL.format(code=it["code"]),
    }


def scrape_all_products() -> list[dict]:
    items = []
    for code in list_codes():
        try:
            it = parse_item(code)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {code} ({e})")
            continue
        if it:
            items.append(it)
        time.sleep(REQUEST_INTERVAL)
    best = {}
    for it in items:
        k = re.sub(r"\s+", "", it["name"])
        if k not in best or it["weight"] < best[k]["weight"]:
            best[k] = it
    return [build_record(it) for it in best.values()]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_andushcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_andushcoffee.json に出力しました")


if __name__ == "__main__":
    main()
