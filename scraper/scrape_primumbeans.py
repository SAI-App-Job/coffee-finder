# -*- coding: utf-8 -*-
"""
scrape_primumbeans.py

プリムビーンズ 八ヶ岳店(PrimumBeans、www.primumbeans.jp)の通販サイト(独自CGIカート)の
商品情報を取得する。注文ごとにその場で焙煎する生豆珈琲焙煎工房。山梨県北杜市。

【robots.txt】404(記載なし。2026-10-26確認)。
【対象】「珈琲豆一覧」(index.cgi?b=9)に並ぶ全銘柄(ブレンド・ストレート)を、各詳細ページ
(index.cgi?b=<番号>&bf=9)で確認する。価格は100gの価格(100g/200g/300gから選択)を採用。
ご購入欄の「生豆」「家庭焙煎」の選択肢は豆の状態の選択肢でありここでは扱わない。
【焙煎度】購入時に通常/浅め/深め/極深めから選ぶ方式(roast_selectable=True、roast_levelはNone)で、
商品ごとの「お勧めの焙煎度」をroast_hintに保持する。
【在庫】詳細ページに「このコーヒー豆のお取り扱いは終了しました」とある銘柄は除外する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
    detect_stock_status,
)

SHOP_INFO = {
    "name": "プリムビーンズ 八ヶ岳店",
    "url": "https://www.primumbeans.jp/",
    "platform": "独自CGIカート",
    "address": "山梨県北杜市大泉町西井出8240-2872",
    "prefecture": "山梨県",
    "robots_txt_status": "記載なし(2026-10-26確認。robots.txtは404)",
    "source_note": "公式サイト(https://www.primumbeans.jp/)の珈琲豆一覧と各商品ページを2026-10-26に確認。"
                   "トップに「ご注文の都度その場で焙煎を行い」と記載。住所は公式サイト表記(大泉町西井出8240-2872(仮))を採用。"
                   "100gの価格を採用し、焙煎度は購入時選択式。取り扱い終了の銘柄は除外。",
    "last_verified_at": "2026-10-26",
}

BASE = "https://www.primumbeans.jp/"
LIST_URL = BASE + "index.cgi?b=9"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
DELAY = 2
ORIGIN_HINTS = {"ニューギニア": "パプアニューギニア", "グァテマラ": "グアテマラ", "マラウィ": "マラウイ", "マラウイ": "マラウイ"}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def clean(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()


def list_items():
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")
    out = []
    for a in soup.select('a[href*="bf=9"]'):
        lines = [l.strip() for l in a.get_text("\n").split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        origin = next((l.split("：", 1)[1] for l in lines if l.startswith("原産国：")), "")
        out.append({"href": a["href"], "list_name": lines[1], "origin_text": origin.rstrip("-")})
    return out


def parse_detail(item, html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    for x in soup(["script", "style"]):
        x.decompose()
    lines = [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]

    def val(label):
        if label in lines:
            i = lines.index(label)
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            return None if nxt in (None, "-") or nxt in ("英語表記", "価格", "規格", "地区", "品種", "標高", "収穫時期", "加工方法", "乾燥方法") else nxt
        return None

    name = clean(val("正式名称") or item["list_name"])
    pm = re.search(r"(\d[\d,]*)円\s*\(100g\)", "\n".join(lines))
    price = int(pm.group(1).replace(",", "")) if pm else None
    rec_roast = next((l.split("：", 1)[1] for l in lines if l.startswith("お勧めの焙煎度：")), None)
    # 先頭の短い説明文(キャッチコピーの次の説明)
    desc = None
    if rec_roast:
        i = next(i for i, l in enumerate(lines) if l.startswith("お勧めの焙煎度："))
        j = lines.index("コーヒー豆の情報") if "コーヒー豆の情報" in lines else i + 3
        body = [l for l in lines[i + 1:j] if l not in ("浅煎り", "中煎り", "深煎り", "中深煎り", "極深煎り")]
        desc = clean("".join(body)) or None
    grade = val("規格")
    discontinued = "お取り扱いは終了" in "\n".join(lines)

    is_blend = "ブレンド" in name or item["origin_text"].endswith("他") or (grade and "ブレンド" in grade) or "エスプレッソ" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        c = detect_country_name(clean(item["origin_text"]))
        if not c:
            for k, v in ORIGIN_HINTS.items():
                if k in item["origin_text"] or k in name:
                    c = v
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)
    proc = val("加工方法")
    if proc:
        parsed["processing_method"] = normalize_processing_method(clean(proc))
    farm = [f"{k}: {clean(val(k))}" for k in ("地区", "品種", "標高") if val(k) and clean(val(k)) != "指定なし"]
    if grade and not is_blend and clean(grade) != "指定なし":
        farm.insert(0, f"規格: {clean(grade)}")
    if discontinued:
        return None  # 取り扱い終了の銘柄は掲載しない
    stock = detect_stock_status(name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": clean(rec_roast) if rec_roast else None,
        "roast_selectable": True,
        "flavor_notes": desc[:300] if desc else None,
        "farm_note": "、".join(farm) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock,
        "out_of_stock": stock != "販売中",
        "product_url": BASE + "index.cgi" + item["href"],
    }


def scrape_all_products():
    records = []
    for item in list_items():
        time.sleep(DELAY)
        rec = parse_detail(item, fetch(BASE + "index.cgi" + item["href"]))
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_primumbeans.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_primumbeans.json に出力しました")


if __name__ == "__main__":
    main()
