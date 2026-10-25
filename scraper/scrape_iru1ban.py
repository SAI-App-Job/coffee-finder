# -*- coding: utf-8 -*-
"""
scrape_iru1ban.py

いる1ばん(あつぎ珈琲 いる１ばん、神奈川県厚木市旭町1丁目38-4 コーポごとう101。
オンラインショップ iru1ban.com/ec/、Welcart)の自家焙煎コーヒー豆を取得する。

【対象】/ec/ の商品一覧のうち、商品名に「焙煎豆」「自店舗焙煎コーヒー豆」とあるコーヒー豆。
水出しコーヒー・カップオンコーヒー(ドリップ系)は除外。生豆の販売は確認できない。
【重量・価格】各商品ページに「100ｇ価格：N円」とあり、ECの販売単位は100g。価格はカート側の税込価格(ページ内の¥表示)。
スマトラ・マンデリンのみ本文の「100ｇ価格」(1,050円)とカート価格(1,080円)が食い違うため、カート価格(購入時の実額)を採用。
【産地】本文の「<〇〇原産>」から取得。ブレンドは「配合<…>」のある商品(キリマンブレンド、コクマイルド、
ソフトブレンド、イタリアンロースト、フレンチロースト)。焙煎度は「浅煎or深煎」選択式の2商品を除き商品名に
イタリアン/フレンチとある2商品のみ。他の商品は苦味・酸味スケールのみで roast_level は None。
【月替わり商品】「【10月おすすめコーヒー】」の4商品は投稿日が2025-10-01(アンジェリカのみ2026-03-31)のため、
前年10月の特集の再掲の可能性がある(在庫表示は「在庫有り」)。
【在庫】「在庫状態 : 在庫有り」以外を品切れとする。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "いる1ばん (あつぎ珈琲)",
    "url": "https://iru1ban.com/ec/",
    "platform": "Welcart(WordPress)",
    "address": "神奈川県厚木市旭町1丁目38-4 コーポごとう101",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-10-21確認。/wp-admin/ のみ禁止)",
    "source_note": "Welcart iru1ban.com/ec/ の商品一覧と各商品ページを2026-10-21に確認。"
                   "公式サイト店舗情報 https://iru1ban.com/about/ に「あつぎ珈琲 いる１ばん、神奈川県厚木市旭町1丁目38-4 コーポごとう101、"
                   "店内でコーヒーを飲むことができます、焙煎豆・生豆:100gより販売」、ECの商品名に「自店舗焙煎コーヒー豆」。"
                   "10月おすすめ4商品の投稿日は2025-10-01(1件のみ2026-03-31)で前年の特集の可能性あり。",
    "last_verified_at": "2026-10-21",
}

LIST_URL = "https://iru1ban.com/ec/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
EXCLUDE = ["水出し", "カップオン", "セット", "ギフト", "ドリップ"]
ORIGIN_RE = re.compile(r"[<〈＜]\s*([^<>〈〉＜＞]*?)\s*原産\s*[>〉＞]")
ORIGIN_SPLIT_RE = re.compile(r"[<〈＜]\s*\n?\s*([^<>〈〉＜＞\n]*?)\s*\n?\s*[>〉＞]")


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return BeautifulSoup(r.text, "html.parser")


def list_items():
    soup = fetch(LIST_URL)
    items = []
    for a in soup.select("article"):
        n = a.select_one(".itemname a")
        if not n:
            continue
        name = n.get_text(strip=True)
        if any(k in name for k in EXCLUDE):
            continue
        items.append((n["href"], name))
    return items


def clean_name(name):
    name = re.sub(r"^【[^】]*】", "", name)
    name = re.sub(r"[(（]焙煎豆[)）]", "", name)
    name = re.sub(r"[＜<]浅煎or深煎[＞>]", "", name)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name.replace("　", " "))).strip()


def build(href, list_name):
    soup = fetch(href)
    for t in soup(["script", "style"]):
        t.decompose()
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n", strip=True))
    start = text.find("公式HPに戻る")
    end = text.find("商品カテゴリー", start)
    seg = text[start + len("公式HPに戻る"):end] if start >= 0 and end > start else text
    pm = re.search(r"在庫状態\s*:\s*([^\n]+)\n¥\s*([\d,]+)", seg)
    if not pm:
        return None
    stock_txt, price = pm.group(1).strip(), int(pm.group(2).replace(",", ""))
    out = "在庫有り" not in stock_txt
    wm = re.search(r"([0-9０-９]+)\s*[gｇ]価格", seg)
    weight = int(unicodedata.normalize("NFKC", wm.group(1))) if wm else None

    flat = unicodedata.normalize("NFKC", seg).replace("\n", "")
    om = ORIGIN_RE.search(flat)
    origin_txt = om.group(1) if om else None
    name = clean_name(list_name)
    blend = "配合" in seg or "ブレンド" in name
    # 説明文: 「100ｇ価格」から「※写真の袋」の前まで(価格行と原産行は除く)
    lines = [l for l in seg.split("\n") if l.strip()][1:]  # 先頭行は商品見出し(h1)
    desc_lines = []
    for l in lines:
        if l.startswith("※写真の袋"):
            break
        if (re.search(r"[gｇ]価格", l) or l.startswith("(") or l == name or "【" in l or "●" in l
                or "原産" in l or l.startswith("月替わり") or l == "10月のおすすめ品" or re.fullmatch(r"[<>〈〉＜＞]", l.strip())):
            continue
        desc_lines.append(l)
    desc = " ".join(desc_lines[:12])[:300] or None

    parsed = parse_product(name)
    roast_hint = None
    sm = re.search(r"(●苦味○酸味[^\n]*(?:\n[●○]+)?)", seg)
    if sm:
        roast_hint = "味のスケール " + sm.group(1).replace("\n", " ").strip()
    if "浅煎or深煎" in list_name or "浅煎" in seg and "深煎" in seg:
        roast_hint = (roast_hint + " / " if roast_hint else "") + "購入時に浅煎・深煎を選択"
    if blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if origin_txt:
            c = detect_country_name(origin_txt)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, name)
    processing = parsed["processing_method"]
    if "ナチュラル" in name and not processing:
        processing = "ナチュラル"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": (origin_txt + "原産") if origin_txt else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": href,
    }


def main():
    items = list_items()
    print(f"[info] 対象 {len(items)}件")
    records = []
    for href, name in items:
        time.sleep(DELAY)
        try:
            rec = build(href, name)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {href} ({e})")
            continue
        if rec:
            records.append(rec)
        else:
            print(f"[warn] 価格取得失敗: {name}")
    with open("data_iru1ban.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_iru1ban.json に出力しました")


if __name__ == "__main__":
    main()
