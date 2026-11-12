# -*- coding: utf-8 -*-
"""
scrape_cafetierhayama.py

Cafetier (カフェティエ葉山)(神奈川県三浦郡葉山町下山口1538-3、販売業者 Cafetier 水牧孝郎。
オンラインショップ cafeteir.shop-pro.jp、カラーミーショップ)の自家焙煎コーヒー豆を取得する。

【対象】商品カテゴリ「中南米産」「アフリカ産」「アジア大洋州産」「オリジナルブレンド」
「デカフェ」「その他の商品」(cbid=1608942〜1608946,1608948)の全商品。ドリップバッグ・ギフトセット・
いぬグッズ・音楽CDのカテゴリは対象外。
【重量】この店は重量(200g/250g/300g/400g/500g)ごとに別商品ページ(商品名末尾「／200g」)。
同一銘柄は最小重量の商品を代表とし、豆のまま(選択肢の先頭「0.豆のまま」)の価格を採用する。
【価格】商品ページの Colorme JSON の税込価格(sales_price_including_tax。サイトは税抜・税込併記)。
【焙煎度】商品が属するグループ「軽めな焙煎(ハイロースト)」「マイルド(シティロースト)」「ややコクあり
(シティロースト)」「深いコク(シティ〜フルシティ)」「コクと苦み(フルシティ〜イタリアン)」から取得。
単一値のものは roast_level、範囲表記のものは roast_hint に入れる。
【在庫】stock_num が 0 以下なら品切れ(None は無制限)。
【文字コード】EUC-JP。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method, detect_processing_method,
)

SHOP_INFO = {
    "name": "Cafetier (カフェティエ葉山)",
    "url": "https://cafeteir.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県三浦郡葉山町下山口1538-3",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-10-21確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ cafeteir.shop-pro.jp のカテゴリ一覧と各商品ページを2026-10-21に確認。"
                   "特定商取引法表記(販売業者 Cafetier 水牧孝郎、神奈川県三浦郡葉山町下山口1538-3)、"
                   "ショップ紹介「葉山町で小さな焙煎機を改造した釜で1回600g程度の仕上がりで焙煎しています」、"
                   "トップに営業日(月曜定休)の案内。重量別に別商品ページ(最小重量を代表に採用)。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://cafeteir.shop-pro.jp/"
CATEGORIES = {
    1608942: "中南米産", 1608943: "アフリカ産", 1608944: "アジア大洋州産",
    1608945: "オリジナルブレンド", 1608946: "デカフェ", 1608948: "その他の商品",
}
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
EXCLUDE = ["ドリップバッグ", "ギフト", "セット", "詰め合わせ", "詰合せ", "お試し", "飲み比べ", "CD", "グッズ"]
WEIGHT_RE = re.compile(r"[／/\s]*(\d+)\s*[gｇ]\s*$")
ROAST_GROUPS = {
    721281: (None, "ハイロースト"),
    721284: (None, "シティロースト"),
    721286: (None, "シティロースト(ややコクあり)"),
    721288: (None, "シティロースト〜フルシティロースト"),
    721290: (None, "フルシティロースト〜イタリアンロースト"),
}
ROAST_LEVEL_FROM_GROUP = {721281: "ハイロースト", 721284: "シティロースト", 721286: "シティロースト"}
LABEL_RE = re.compile(r"(原産国|地域|標高|精選方法|栽培品種|品種|農園)[：:]\s*([^\n]+)")


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(html, "html.parser"), html


def list_items():
    items = {}
    for cb, cname in CATEGORIES.items():
        page = 1
        while True:
            soup, _ = fetch(f"{BASE_URL}?mode=cate&cbid={cb}&csid=0&page={page}")
            for it in soup.select("div.product_item"):
                a = it.select_one('a[href^="?pid="]')
                nm = it.select_one("div.name")
                if not a or not nm:
                    continue
                pid = re.search(r"pid=(\d+)", a["href"]).group(1)
                items.setdefault(pid, (re.sub(r"\s+", " ", nm.get_text(" ", strip=True)), cname))
            time.sleep(DELAY)
            if not soup.find("a", string=re.compile("次のページ")):
                break
            page += 1
    return items


def pick_representatives(items):
    best = {}
    for pid, (name, cname) in items.items():
        if any(k in name for k in EXCLUDE):
            continue
        m = WEIGHT_RE.search(unicodedata.normalize("NFKC", name))
        if not m:
            print(f"[warn] 重量不明: {name}")
            continue
        weight = int(m.group(1))
        base = unicodedata.normalize("NFKC", WEIGHT_RE.sub("", unicodedata.normalize("NFKC", name))).replace(" ", "")
        key = (cname, base)
        if key not in best or weight < best[key][2]:
            best[key] = (pid, name, weight, cname)
    return list(best.values())


def build(pid, list_name, weight, cname):
    url = f"{BASE_URL}?pid={pid}"
    soup, html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    name = p["name"].strip()
    base = WEIGHT_RE.sub("", unicodedata.normalize("NFKC", name)).strip()
    variants = p.get("variants") or []
    whole = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")] or variants
    price = whole[0]["option_price_including_tax"] if whole else p["sales_price_including_tax"]

    expl = soup.select_one("div.expl")
    body = ""
    if expl:
        for br in expl.find_all("br"):
            br.replace_with("\n")
        body = expl.get_text("\n", strip=True)
    labels = {k: v.strip() for k, v in LABEL_RE.findall(body)}
    text_lines = [l for l in body.split("\n") if l and not LABEL_RE.match(l) and "脱酸素剤" not in l and "荷姿" not in l]
    desc = " ".join(text_lines)[:300] or None

    group_ids = [g["id"] for g in (p.get("groups") or [])]
    roast_level, roast_hint = None, None
    for g in group_ids:
        if g in ROAST_GROUPS:
            roast_level = ROAST_LEVEL_FROM_GROUP.get(g)
            roast_hint = ROAST_GROUPS[g][1]
            break

    is_blend = cname == "オリジナルブレンド" or "ブレンド" in base
    parsed = parse_product(base)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"] and labels.get("原産国"):
            c = detect_country_name(labels["原産国"])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        if not parsed["origin_country"]:
            c = detect_country_name(body[:300])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, base)
        if not parsed["origin_country"] and "カッファ" in (base + body):
            # カッファ地方(エチオピア南西部)。商品説明に「カッファ地方、シェカ地区」とある
            parsed["origin_country"] = "エチオピア"
            parsed["origin_source"] = "region_name"
        if labels.get("精選方法") and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(labels["精選方法"])
        if not parsed["processing_method"]:
            parsed["processing_method"] = detect_processing_method(body[:300])

    # 商品名に焙煎度の記載があれば優先(例「深煎り」「ダークロースト」「ライト」)
    for kw, lv in (("ダークロースト", "深煎り"), ("深煎り", "深煎り"), ("中深煎り", "中深煎り")):
        if kw in base:
            roast_hint = (roast_hint + "/" if roast_hint else "") + kw
            break

    stock = p.get("stock_num")
    out = isinstance(stock, int) and stock <= 0
    farm = "、".join(f"{k}: {labels[k]}" for k in ("地域", "標高", "栽培品種", "品種", "精選方法") if labels.get(k)) or None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def main():
    items = list_items()
    reps = pick_representatives(items)
    print(f"[info] 一覧 {len(items)}件 / 代表 {len(reps)}銘柄")
    records = []
    for pid, name, weight, cname in reps:
        time.sleep(DELAY)
        try:
            rec = build(pid, name, weight, cname)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {pid} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_cafetierhayama.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafetierhayama.json に出力しました")


if __name__ == "__main__":
    main()
