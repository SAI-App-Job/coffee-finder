# -*- coding: utf-8 -*-
"""
scrape_hakubabaisen.py

白馬焙煎工房(www.hakubabaisen.com、長野県北安曇郡白馬村北城3335-1)のオンラインショップの
商品情報を取得する。独自カート(商品ページ /item/{ID}/、カテゴリ /category/{ID}/、
フォーム項目 hidGoodsCode / dealId 等を持つ国産ショップ構築システム。既存スクリプトに同種なし)。UTF-8。

【対象商品】カテゴリ「旨み(91)」「マイルド(92)」「フルーティ(93)」「苦味(94)」「デカフェ(80)」の
商品ページ(重複除去、14点)。ドリップバッグ・ギフトのアソートセット(カテゴリ56/87)は除外。
【重量・価格】各商品ページの「購入数 袋×100g」表記(100g/袋)と「販売価格(税込)」。
ゲイシャ(商品319)は「1袋/50gからの販売」の記載から50g。
【産地・焙煎度】ページ内「原産国」欄・商品名の国名、焙煎度は商品名の「＊中深煎り」表記。
ブレンドは商品が属するカテゴリ「工房のぶれんど珈琲」や名称から判定。
【在庫】ページ内「在庫あり」/「在庫切れ」表記。

robots.txt確認済み(2026-10): Disallow は /default/error/ と /preview/ のみ。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "白馬焙煎工房",
    "url": "https://www.hakubabaisen.com/",
    "platform": "独自カート(ショップ構築システム。商品URL /item/ID/)",
    "address": "長野県北安曇郡白馬村北城3335-1",
    "prefecture": "長野県",
    "robots_txt_status": "許可(2026-10確認。/default/error/と/preview/のみDisallow)",
}

BASE = "https://www.hakubabaisen.com"
CATEGORY_IDS = [91, 92, 93, 94, 80]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_RE = re.compile(r"(極深煎り|中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
NON_BEAN = ["ドリップバッグ", "ギフト", "アソート", "セット"]


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def list_item_urls():
    urls = []
    for cid in CATEGORY_IDS:
        s = BeautifulSoup(get("%s/category/%d/" % (BASE, cid)), "html.parser")
        for a in s.find_all("a", href=True):
            m = re.search(r"/item/(\d+)/?$", a["href"])
            if m:
                u = "%s/item/%s/" % (BASE, m.group(1))
                if u not in urls:
                    urls.append(u)
        time.sleep(1)
    return urls


def build_record(url):
    h = get(url)
    soup = BeautifulSoup(h, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    lines = [unicodedata.normalize("NFKC", x) for x in soup.get_text("\n", strip=True).split("\n")]
    text = "\n".join(lines)
    i = text.find("CATEGORY\nHOME")
    body = text[i:] if i >= 0 else text
    bl = body.split("\n")
    # パンくず: HOME / » / カテゴリ名 / » 商品名
    cat_name = bl[3] if len(bl) > 3 else ""
    title = ""
    for ln in bl[4:8]:
        if ln.startswith("»"):
            title = ln.lstrip("» ").strip()
            break
    if not title or any(k in title for k in NON_BEAN):
        return None
    pm = re.search(r"販売価格\n([\d,]+)円", body)
    price = int(pm.group(1).replace(",", "")) if pm else None
    stock_m = re.search(r"在庫を確認する\n(在庫あり|在庫切れ|[^\n]+)", body)
    in_stock = bool(stock_m and stock_m.group(1) == "在庫あり")
    wm = re.search(r"袋×\s*(\d+)\s*g", body)
    if wm:
        weight = int(wm.group(1))
    else:
        wm2 = re.search(r"(\d+)\s*g\s*から", body)
        weight = int(wm2.group(1)) if wm2 else None
    # 商品説明(最初の見出し行以降〜型番まで)
    j = body.find(title, body.find(title) + len(title))
    k = body.find("型番")
    desc_block = body[j + len(title): k] if 0 <= j < k else ""
    desc = re.sub(r"\s+", " ", desc_block).strip()

    def field(label):
        mm = re.search(label + r"\n([^\n]+)", desc_block)
        return mm.group(1).strip() if mm else None

    country_raw = field("原産国")
    process_raw = (field("精製方法") or "").lstrip("*＊ ") or None
    rm = ROAST_RE.search(title)
    roast = rm.group(1) if rm else None

    name = re.sub(r"[＊*※]\s*(?:極深煎り|中浅煎り|中深煎り|浅煎り|中煎り|深煎り)[^\n]*$", "", title).strip()
    name = re.sub(r"^[＊*※\s]+", "", name)
    name = re.sub(r"\s*[＊*]\s*", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    is_blend = "ぶれんど" in cat_name or "ブレンド" in cat_name or "ぶれんど" in title or "ブレンド" in title
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        c = detect_country_name(country_raw) if country_raw else None
        c = c or detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description" if country_raw and detect_country_name(country_raw) == c else "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    proc = parsed["processing_method"]
    if process_raw and not proc:
        proc = normalize_processing_method(process_raw)
    flavor = None
    fm = (re.search(r"CUP FEATURE[\]】]?\n([^\n]+)", desc_block)
          or re.search(r"カッピング・?プロファイル/Cupping Profile】\n([^\n]+)", desc_block)
          or re.search(r"Cupping Profile[\]】]?\n(?!\[|【)([^\n]+)", desc_block))
    if fm:
        flavor = fm.group(1).strip()[:300]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": proc,
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products():
    out = []
    for u in list_item_urls():
        rec = build_record(u)
        if rec:
            out.append(rec)
        time.sleep(1)
    return out


def main():
    records = scrape_all_products()
    with open("data_hakubabaisen.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hakubabaisen.json に出力しました")


if __name__ == "__main__":
    main()
