# -*- coding: utf-8 -*-
"""
scrape_baisen106.py

京都焙煎珈琲106(baisen106.com、京都府向日市物集女町クヅ子5 グレースメイト1F)の商品情報を
取得する。Jimdo(Jimdoショップ機能)。

【robots.txtについて】
実データ確認済み(2026-10時点): `Disallow: /app/`・`/j/`(ただし`/app/module/webproduct/goto/`は
許可)、`Crawl-Delay: 5`。商品を載せた公開ページ(通常URL)のみを取得し、リクエスト間に
5秒の待機を入れる。

【商品一覧の取得方法について】
sitemap.xmlの「/オンラインショッピング/」配下のカテゴリページ(産地国別・ハウスブレンド・
カフェインレス・オーガニック・おすすめ・希少種等、支払い方法/配送方法/特商法ページを除く)を
巡回し、各ページに埋め込まれた商品モジュール(div#cc-m-product-*)を読む。同じ商品が
複数のカテゴリページに載るため、商品モジュールIDで重複排除する。

【バリエーションと重量・価格・在庫について】
実データ確認済み: 1商品に「生豆100g〜500g」「ロースト豆100g〜500g」「ロースト粉100g〜500g」
(100g刻み)の15バリエーションがある(店頭は「¥〜より」表記)。生豆は対象外のため
「生豆」を含むバリエーションは使わず、焙煎済み(ロースト豆・ロースト粉)の最小重量(通常
100g)を代表とする。内容量(Ng)の記載が無いバリエーションは使わず、生豆のみ・内容量の
記載が無い商品は除外する。価格・在庫は「ロースト豆」バリエーション(存在しない場合は
ロースト粉)のもの。**価格は税別表示**(ページに「税別 / 送料別途」と明記)のため、
そのまま税別価格を格納し、unit_noteに「税別」と明記する。

【product_urlについて】
1ページに複数商品が載るため、`ページURL#` + quote(商品名) を product_url とする
(商品モジュールIDが異なるのに同名で衝突する場合のみIDを付ける)。
"""

import html
import json
import re
import time
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "京都焙煎珈琲106",
    "url": "https://www.baisen106.com/",
    "platform": "Jimdo",
    "address": "京都府向日市物集女町クヅ子5 グレースメイト1F",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10確認。/app/・/j/はDisallow、Crawl-Delay: 5)",
}

BASE_URL = "https://www.baisen106.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
CRAWL_DELAY = 5
SHOP_PREFIX = "/オンラインショッピング/"
SKIP_PATH_KEYWORDS = ("お支払い", "配送方法", "特定商取引")
# 国別ページを先に処理して、product_urlを国別ページ基準にする
PRIORITY_PAGES = ("おすすめ", "最高級品種", "高級品種", "希少種")
EXCLUDE_KEYWORDS = ("ドリップバッグ", "ドリップバック", "セット", "ギフト", "詰合せ", "詰め合わせ")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り")),
    ("中煎り", re.compile(r"中煎り")),
    ("深煎り", re.compile(r"深煎り")),
)
UNIT_NOTE = "税別価格(ロースト豆)"


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    time.sleep(CRAWL_DELAY)
    return resp.text


def shop_page_paths() -> list[str]:
    xml = fetch(f"{BASE_URL}/sitemap.xml")
    paths = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
        path = urllib.parse.unquote(urllib.parse.urlparse(loc).path)
        if not path.startswith(SHOP_PREFIX) or path == SHOP_PREFIX:
            continue
        if any(k in path for k in SKIP_PATH_KEYWORDS):
            continue
        paths.append(path)
    country_pages = [p for p in paths if not any(k in p for k in PRIORITY_PAGES)]
    other_pages = [p for p in paths if any(k in p for k in PRIORITY_PAGES)]
    return country_pages + other_pages


def coarse_roast(text):
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def parse_variants(module) -> list[dict]:
    variants = []
    for o in module.select("option.j-product__variants__item"):
        label = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", o.get_text(" ", strip=True)))
        if "送料" in label or "生豆" in label:
            continue
        wm = WEIGHT_PATTERN.search(label)
        if not wm:
            continue
        try:
            params = json.loads(html.unescape(o["data-params"]))
        except (KeyError, ValueError):
            continue
        variants.append({
            "label": label,
            "weight": int(wm.group(1)),
            "price": int(params["price"]),
            "available": params.get("availability") == 1,
            "is_beans": "豆" in label and "粉" not in label,
        })
    return variants


def clean_name(name: str) -> str:
    n = re.sub(r"[＊*★☆]+[^＊*★☆]*[＊*★☆]+", "", name)  # 「＊希少種＊」「★有機栽培★」等の装飾
    return re.sub(r"\s+", " ", n).strip()


def build_record(page_path: str, page_title: str, module) -> dict | None:
    name_el = module.select_one("[itemprop=name]")
    raw_title = re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip() if name_el else None
    if not raw_title or any(k in raw_title for k in EXCLUDE_KEYWORDS):
        return None
    name = clean_name(raw_title) or raw_title
    variants = parse_variants(module)
    if not variants:
        return None
    min_weight = min(v["weight"] for v in variants)
    rep = [v for v in variants if v["weight"] == min_weight]
    beans = [v for v in rep if v["is_beans"]] or rep
    price = beans[0]["price"]
    available = any(v["available"] for v in beans)

    desc_el = module.select_one("div.description")
    desc = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True))).strip() if desc_el else ""
    tags = " ".join(re.findall(r"[＊*★]([^＊*★]+)[＊*★]", raw_title))

    if re.search(r"カフェインレス|デカフェ", desc + raw_title) and not re.search(r"カフェインレス|デカフェ", name):
        name = f"{name}(カフェインレス)"  # 同名の通常品と区別するため(商品名の注記)

    is_blend = "ブレンド" in name
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
        if not parsed["origin_country"]:
            bm = re.search(r"【([^】]+)】", desc)
            c = detect_country_name(bm.group(1)) if bm else None
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "description"
        if not parsed["origin_country"] and page_title:
            parsed = apply_category_hint_fallback(parsed, page_title)

    roast_level, roast_hint = coarse_roast(name)
    if not roast_level:
        roast_level, roast_hint = coarse_roast(desc)
    processing = parsed["processing_method"] or (None if is_blend else detect_processing_method(desc))

    flavor = re.sub(r"【[^】]*】", "", desc).strip()
    if tags:
        flavor = f"{tags} {flavor}".strip()

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
        "flavor_notes": flavor[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": min_weight,
        "unit_note": UNIT_NOTE,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE_URL}{urllib.parse.quote(page_path)}#{urllib.parse.quote(name)}",
    }


def scrape_all_products() -> list[dict]:
    records, seen_modules, seen_urls, seen_content = [], set(), set(), set()
    for path in shop_page_paths():
        soup = BeautifulSoup(fetch(BASE_URL + urllib.parse.quote(path)), "html.parser")
        page_title = path.rstrip("/").split("/")[-1]
        for module in soup.select("div[id^=cc-m-product-]"):
            mid = module.get("id")
            url_meta = module.select_one("meta[itemprop=url]")
            pid = url_meta.get("content") if url_meta else mid
            if pid in seen_modules:  # 同一商品は複数カテゴリページに載るため商品IDで重複排除
                continue
            seen_modules.add(pid)
            rec = build_record(path, page_title, module)
            if not rec:
                continue
            # 商品IDが異なるが名称・価格・説明が完全に同一の重複登録(インドパパチ等)は1件にまとめる
            content_key = (rec["raw_name"], rec["price"], rec["flavor_notes"])
            if content_key in seen_content:
                continue
            seen_content.add(content_key)
            if rec["product_url"] in seen_urls:
                rec["product_url"] += "-" + mid.replace("cc-m-product-", "")
            seen_urls.add(rec["product_url"])
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_baisen106.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_baisen106.json に出力しました")


if __name__ == "__main__":
    main()
