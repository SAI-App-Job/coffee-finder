# -*- coding: utf-8 -*-
"""
scrape_yamawaraucoffee.py

山笑う珈琲(yamawarau coffee roaster、www.yamawaraucoffee.com、長野県伊那市富県1777-988)の
オンラインショップの商品情報を取得する。カラーミーショップ(独自ドメイン)。EUC-JP。
(STORES側にも併存するが、カラーミー側を使う)

【対象商品】カテゴリ「コーヒー豆」(cbid=2869083)の商品のうち、ドリップバッグ・ギフト・
お試しセット等のセット商品を除いた自家焙煎豆のみ。
【重量・価格】var Colorme の variants(重量×挽き方)のうち「豆のまま」の最小重量(100g)の
税込価格(option_price_including_tax)を採用。
【産地・焙煎度】商品説明の「生産国：」「精製方法：」「焙煎度：」「フレーバー：」から取得。
商品名は【深煎り】等の焙煎度が先頭に付く。同一ロットの焙煎度違いは別商品として別pid。
【在庫】inventory_control=none のため構造化在庫なし。ページ内の「SOLD OUT/売り切れ」表記で判定。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "山笑う珈琲",
    "url": "https://www.yamawaraucoffee.com/",
    "platform": "カラーミーショップ(独自ドメイン)",
    "address": "長野県伊那市富県1777-988",
    "prefecture": "長野県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE = "https://www.yamawaraucoffee.com/"
CATEGORY_URL = BASE + "?mode=cate&cbid=2869083&csid=0&page=%d"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN = ["ドリップバッグ", "ギフト", "セット", "詰め合わせ", "詰合せ"]
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*")
SOLD_RE = re.compile(r"SOLD\s*OUT|売り切れ|品切れ|在庫切れ", re.I)


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "euc-jp"
    return r.text


def list_pids():
    pids = []
    for pg in range(1, 6):
        s = BeautifulSoup(get(CATEGORY_URL % pg), "html.parser")
        found = 0
        for a in s.find_all("a", href=True):
            m = re.search(r"\?pid=(\d+)", a["href"])
            if m and m.group(1) not in pids:
                pids.append(m.group(1))
                found += 1
        if not found:
            break
        time.sleep(1)
    return pids


def build_record(pid):
    url = BASE + "?pid=" + pid
    h = get(url)
    m = COLORME_RE.search(h)
    prod = json.JSONDecoder().raw_decode(h[m.end():])[0]["product"]
    title = re.sub(r"\s+", " ", (prod.get("name") or "").replace("　", " ")).strip()
    if any(k in title for k in NON_BEAN):
        return None
    variants = prod.get("variants") or []
    whole = [v for v in variants if "豆のまま" in (v.get("option2_value") or "") + (v.get("option1_value") or "")] or variants

    def w_of(v):
        mm = re.search(r"(\d+)\s*[gｇ]", (v.get("option1_value") or "") + (v.get("option2_value") or ""))
        return int(mm.group(1)) if mm else 10 ** 9

    v = min(whole, key=w_of) if whole else None
    weight = w_of(v) if v and w_of(v) < 10 ** 9 else None
    price = v.get("option_price_including_tax") if v else prod.get("sales_price_including_tax")

    soup = BeautifulSoup(h, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    i = text.find("商品説明")
    body = text[i:] if i >= 0 else text
    body = body.split("商品一覧")[0]
    head = text[: i if i >= 0 else len(text)]
    sold = bool(SOLD_RE.search(head.split("コーヒー豆の量")[0][-600:] if "コーヒー豆の量" in head else head[-600:]))

    def lab(label):
        mm = re.search(label + r"：\s*([^\n]+)", body)
        return mm.group(1).strip() if mm else None

    country = lab("生産国")
    process = lab("精製方法")
    roast = lab("焙煎度")
    flavor = lab("フレーバー")
    if not roast and "ブレンド" in title:
        # ブレンドは説明文中の「浅煎り〜中煎りの」「深煎りブレンド」から取得
        mm = re.search(r"((?:中浅|中深|浅|中|深)煎り(?:[〜~～](?:中浅|中深|浅|中|深)煎り)?)", body)
        roast = mm.group(1) if mm else None
    if not flavor and "ブレンド" in title:
        paras = [x for x in body.split(chr(10))[1:] if x.strip()]
        flavor = paras[1] if len(paras) > 1 else (paras[0] if paras else None)
        flavor = flavor[:300] if flavor else None
    if not roast:
        mm = re.match(r"【([^】]*煎り)】", title)
        roast = mm.group(1) if mm else None
    name = title

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        c = detect_country_name(country) if country else None
        c = c or detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)
    proc = parsed["processing_method"] or (normalize_processing_method(process) if process else None)
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
        "stock_status": "完売" if sold else "販売中",
        "out_of_stock": sold,
        "product_url": url,
    }


def scrape_all_products():
    out = []
    for pid in list_pids():
        rec = build_record(pid)
        if rec:
            out.append(rec)
        time.sleep(1)
    return out


def main():
    records = scrape_all_products()
    with open("data_yamawaraucoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamawaraucoffee.json に出力しました")


if __name__ == "__main__":
    main()
