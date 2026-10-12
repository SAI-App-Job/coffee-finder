# -*- coding: utf-8 -*-
"""
scrape_wabisuke.py

wabisuke(ワビスケ。珈琲司ゆだ屋。栃木県大田原市本町1-2691、https://coffee-tukasa-yudaya.com/)の
自家焙煎コーヒー豆の商品情報を取得する。ECは WordPress + Welcart。
「プレウォッシュド(自家水洗)後に自家焙煎」が特徴。

【店舗発見の経緯】
全国再調査(栃木県)の新規発掘で発見。

【取得方法】
カテゴリページ「Single Coffee」「Blend Coffee」(/category/item/singlecoffee/、blendcoffee/)の
商品一覧(`<a itemprop="url">`)から商品ページを集め、各商品ページの h1 / 価格 / 内容量 /
在庫(豆)/ 【生産国】等の説明を読む。

【対象】Single Coffee / Blend Coffee のコーヒー豆(豆/粉を選べる商品は豆の在庫を採用)。
COFFEE BAG(ドリップバッグ)、お試しブレンドセット、お酒に漬け込んだ Sake/Vino/Scotch di caffe
(生豆をお酒に漬けるインフューズド系)、講習・器具・焼き菓子・店舗様用は除外。
Welcartの商品説明に豆/粉の別があるが、価格・内容量(通常100g)は同一。
【焙煎度】サイト内「当店の焙煎度合いは全て同じ…一般的に中煎りと呼ばれる所で…(絶対焙煎)」と明記
されているため、全商品「中煎り」とする。

【robots.txt】User-agent: * で /wp-admin/ のみDisallow(商品ページはクロール可)。
"""

import json
import re
import time
import html

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "wabisuke",
    "url": "https://coffee-tukasa-yudaya.com/",
    "platform": "WordPress + Welcart",
    "address": "栃木県大田原市本町1-2691",
    "prefecture": "栃木県",
    "robots_txt_status": "許可(User-agent: * は /wp-admin/ のみDisallow)",
}

BASE_URL = "https://coffee-tukasa-yudaya.com"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORIES = ["singlecoffee", "blendcoffee"]


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return None
    r.encoding = "utf-8"
    return r.text


def collect_urls():
    urls = []
    for cat in CATEGORIES:
        for pg in range(1, 10):
            u = f"{BASE_URL}/category/item/{cat}/" + (f"page/{pg}/" if pg > 1 else "")
            t = get(u)
            if t is None:
                break
            found = re.findall(r'<a itemprop="url" href="([^"]+)"', t)
            for f in found:
                if f not in urls:
                    urls.append(f)
            time.sleep(0.3)
    return urls


def clean(s):
    return re.sub(r"\s+", " ", s.replace("　", " ")).strip()


def parse_page(url):
    t = get(url)
    if t is None:
        return None
    m = re.search(r"<title>([^<|]*)", t)
    title = clean(html.unescape(m.group(1))) if m else None
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    body = re.sub(r"<(br|/p|/div|/li|/h\d|/tr|/td|/th|/option)[^>]*>", "\n", body)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", body))
    txt = re.sub(r"[ \t　]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    pm = re.search(r"¥\s*([\d,]+)\s*\n\s*\(税込\)", txt)
    price = int(pm.group(1).replace(",", "")) if pm else None
    # 内容量は「(税込)」以降で最初に単独行で現れる「100g」(業務パック割引の「10100g以上」を避ける)
    after = txt[pm.end():] if pm else txt
    wm = re.search(r"^\s*(\d+)\s*[gｇ]\s*$", after, flags=re.M)
    weight = int(wm.group(1)) if wm else None
    # 在庫表: 「購入」の下に「豆 / 在庫有り / 粉 / 在庫有り」、または豆/粉の別なしで「在庫有り」のみ
    bean_stock = None
    sm = re.search(r"購入\s*\n\s*([^\n]+)\n(?:\s*([^\n]+)\n)?", txt)
    if sm:
        bean_stock = (sm.group(2) if sm.group(1).strip() == "豆" else sm.group(1)).strip()
    # 説明: 「商品説明を開く」の後ろ〜共有ボタンの前
    d = re.search(r"商品説明を開く\s*\n(.*?)\n\s*X で共有", txt, flags=re.S)
    desc_raw = d.group(1) if d else ""
    desc_raw = re.sub(r"※ネコポスはトータル400gまで.*?\n", "", desc_raw)
    desc_raw = re.sub(r"※当店の焙煎度合い.*?絶対焙煎と呼んでおります。", "", desc_raw, flags=re.S)
    desc_raw = re.sub(r"各、豆と粉の画像は.*?ご了承下さい。", "", desc_raw, flags=re.S)
    desc = clean(desc_raw) or None
    bc = re.search(r"Home\s*\n\s*([^\n]+)\n\s*([^\n]+)\n(?:\s*([^\n]+)\n)?", txt)
    category = clean(bc.group(1)) if bc else None
    name = clean(bc.group(2)) if bc else title
    # パンくず(2行目)とh1(3行目)で表記が異なる商品がある。エスプレッソブレンドはh1の「Espresso blend【銘柄名】」を採用
    if bc and bc.group(3) and "【" in bc.group(3):
        name = clean(bc.group(3))
    return {"url": url, "title": title, "name": name, "price": price, "weight": weight, "bean_stock": bean_stock,
            "desc": desc, "category": category, "raw_txt": txt}


EXCLUDE_WORDS = ["COFFEE BAG", "セット", "di caff", "ドリップバッグ", "ギフト"]
ROAST = "中煎り"  # サイト記載: 全商品同一焙煎度合い「一般的に中煎りと呼ばれる所」(絶対焙煎)
PROCESS_RE = re.compile(r"【精製(?:工程|方法)】\s*([^\s【]+)")
ORIGIN_RE = re.compile(r"【生産国】\s*([^\s【]+)")


def build_record(p):
    name = p["name"]
    if any(w.lower() in name.lower() for w in EXCLUDE_WORDS):
        return None
    desc = p["desc"] or ""
    is_blend = p["category"] == "Blend Coffee" or "blend" in name.lower() or "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        c = detect_country_name(name)
        if c and not parsed["origin_country"]:
            parsed["origin_country"] = c
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"]:
            om = ORIGIN_RE.search(desc)
            c = detect_country_name(om.group(1)) if om else None
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        if not parsed["processing_method"]:
            pm = PROCESS_RE.search(desc)
            if pm:
                from coffee_parser import detect_processing_method
                parsed["processing_method"] = detect_processing_method(pm.group(1))
    st = p["bean_stock"] or ""
    in_stock = ("在庫有り" in st) or st == ""
    if any(w in st for w in ["売り切れ", "売切", "品切", "完売", "なし"]):
        in_stock = False
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": ROAST,
        "roast_hint": None,
        "flavor_notes": clean(desc)[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": p["price"],
        "weight_g": p["weight"],
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": p["url"],
    }


def scrape_all_products():
    records = []
    for u in collect_urls():
        p = parse_page(u)
        time.sleep(0.4)
        if not p:
            continue
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_wabisuke.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_wabisuke.json に出力しました")


if __name__ == "__main__":
    main()
