# -*- coding: utf-8 -*-
"""
scrape_passoapasso.py

自家焙煎珈琲 passo a passo(福岡県春日市小倉7丁目1、公式 coffee-passo.com)の商品情報を取得する。
オンラインショップはFC2ショッピングカート(coffeepasso.cart.fc2.com)。

【対象】一覧(ca=all)の【100g】【200g】の2規格が別商品で並ぶ豆商品。同一銘柄は最小重量(100g)の
商品を代表とする。「リキッドアイスコーヒー」「コーヒー友の会(頒布会)」は除外。
「グアテマラ プエルタベルデ」と「…シティロースト」は焙煎度違いの別商品として別銘柄扱い。
焙煎度は商品説明冒頭の「＜中煎り＞」等、産地・品種・精製は説明末尾の[ 生産地域 ]等から取得。
在庫は「再入荷お知らせ希望」リンク(a.arrival_notice_request)が display:none なら販売中、
表示されていれば品切れ。robots.txt(cart.fc2.com)は /cancel/ /setup/ /tools/ のみDisallow。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
)

SHOP_INFO = {
    "name": "自家焙煎珈琲 passo a passo",
    "url": "http://coffeepasso.cart.fc2.com/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "福岡県春日市小倉7丁目1 藤ビル103",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。/cancel/・/setup/・/tools/のみDisallow)",
    "source_note": "FC2カート coffeepasso.cart.fc2.com の商品一覧(ca=all)と各商品ページを2026-10-20に確認。"
                   "公式サイト(http://coffee-passo.com/about/)に「自家焙煎珈琲 passo a passo は福岡県春日市に2003年7月にオープン」「生豆の仕入れ・手作業による選別・焙煎・カップテストを経て店頭に並びます」、所在地「春日市小倉7丁目１ 藤ビル103」、TOPのフッターに「自家焙煎珈琲 passo a passo 福岡県春日市小倉7丁目１」「福岡 春日のコーヒー豆専門店」と記載。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "http://coffeepasso.cart.fc2.com"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
EXCLUDE = ["リキッド", "友の会", "頒布会", "ギフト", "セット", "ドリップバッグ", "水出し"]
WEIGHT_RE = re.compile(r"【\s*(\d+)\s*[gｇ]\s*】")
LABEL_RE = re.compile(r"\[\s*(生産地域|品\s*種|精\s*製)\s*\]\s*([^\[\n]+)")


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.content.decode("utf-8", errors="replace"), "html.parser")


def list_items():
    soup = fetch(f"{BASE_URL}/?ca=all&par_page=100")
    out = {}
    for li in soup.select(".item_inner, li"):
        a = li.select_one('a[href*="/p-r-s"]')
        if not a:
            continue
        name = unicodedata.normalize("NFKC", a.get_text(strip=True))
        if not name or any(k in name for k in EXCLUDE):
            continue
        m = WEIGHT_RE.search(name)
        if not m:
            continue
        base = WEIGHT_RE.sub("", name).strip()
        w = int(m.group(1))
        price_el = li.select_one(".price")
        pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
        cand = (w, a["href"], name, base, int(pm.group(1).replace(",", "")) if pm else None)
        cur = out.get(base)
        if cur is None or w < cur[0]:
            out[base] = cand
    return list(out.values())


def build(cand):
    weight, href, name, base, list_price = cand
    soup = fetch(BASE_URL + href)
    c1 = soup.select_one(".item_comment .comment1")
    c2 = soup.select_one(".item_comment .comment2")
    c1t = c1.get_text("\n", strip=True) if c1 else ""
    c2t = c2.get_text(" ", strip=True) if c2 else ""
    price_el = soup.select_one(".item_price .price_replace")
    pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
    price = int(pm.group(1).replace(",", "")) if pm else list_price

    roast_hint = None
    m = re.search(r"[＜〈<]([^＞〉>]*)[＞〉>]", c1t)
    head = m.group(1) if m else ""
    for kw in ("中深煎り", "中浅煎り", "深煎り", "浅煎り", "中煎り"):
        if kw in head:
            roast_hint = kw
            break
    is_blend = "ブレンド" in head or "ブレンド" in c1t.split("\n")[0]

    labels = {}
    for k, v in LABEL_RE.findall(c2t.replace("\n", " ")):
        labels[re.sub(r"\s+", "", k)] = v.strip()
    # 説明文本体(ラベル行より前)
    body = re.split(r"\[\s*生産地域", c2t)[0].strip()
    desc_parts = [re.sub(r"^[＜〈<][^＞〉>]*[＞〉>]\s*", "", c1t.replace("\n", " ")).strip(), body]
    desc = " ".join(p for p in desc_parts if p)[:300] or None

    title = base
    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if labels.get("生産地域"):
            c = detect_country_name(labels["生産地域"])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        if labels.get("精製"):
            parsed["processing_method"] = normalize_processing_method(labels["精製"])

    notice = soup.select_one("a.arrival_notice_request")
    sold_out = bool(notice) and "display:none" not in (notice.get("style") or "").replace(" ", "")
    farm = "、".join(f"{k}: {labels[k]}" for k in ("生産地域", "品種") if labels.get(k)) or None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}{href}",
    }


def main():
    cands = list_items()
    print(f"[info] 対象 {len(cands)}銘柄")
    records = []
    for cand in cands:
        time.sleep(DELAY)
        try:
            records.append(build(cand))
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {cand[1]} ({e})")
    with open("data_passoapasso.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_passoapasso.json に出力しました")


if __name__ == "__main__":
    main()
