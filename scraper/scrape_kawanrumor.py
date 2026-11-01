# -*- coding: utf-8 -*-
"""
scrape_kawanrumor.py

軽井沢珈琲倶楽部 カワンルマー(kawanrumor.com、株式会社カワンルマー、長野県北佐久郡軽井沢町追分1541-55、
1976年創業。直営の自家焙煎・珈琲専門店「森のカフェテラス・カワンルマー」)のオンラインストア
(カラーミーショップ、独自ドメイン)の商品情報を取得する。

【対象】カテゴリ「シングルオリジン豆」(cbid=2674922)と「ブレンド豆」(cbid=2674917)のみ。
ドリップバッグ・ボトルコーヒー・お試しセット・ギフトのカテゴリは取得しない。
【文字コード】EUC-JP。【robots.txt】Disallow は /secure/ と /cart/ のみ(2026-10-26確認)。
【価格・重量】全商品が200g1種(容量欄「200g」、販売価格は税込)。挽き方は選べるが価格は同一で、
豆のままの価格を採用する。在庫管理は無効(inventory_control: none)で、ページ上の品切れ表記のみで判定。
【産地】シングルは商品名と生産情報の生産地域から。ブレンドは産地なし。
【焙煎度】商品ごとの「焙煎士寸評」に「シティローストで〜」等の推奨焙煎度の記載があるものだけ採用。
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
    "name": "軽井沢珈琲倶楽部 カワンルマー",
    "url": "https://www.kawanrumor.com/",
    "platform": "カラーミーショップ(独自ドメイン)",
    "address": "長野県北佐久郡軽井沢町追分1541-55",
    "prefecture": "長野県",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/のみDisallow)",
    "source_note": "公式オンラインストア(https://www.kawanrumor.com/)のシングルオリジン豆・ブレンド豆カテゴリと各商品ページを2026-10-26に確認。"
                   "会社案内に「自家焙煎・珈琲専門店〈森のカフェテラス・カワンルマー〉直営」、こだわりページに完全熱風式焙煎機を独自開発して使用と記載。"
                   "商品ページの最新追加は2022年頃で、トップの告知(夏季休暇)も年の記載がなく更新は古め。ドリップバッグ・ボトル・お試しセット・ギフトは除外。",
    "last_verified_at": "2026-10-26",
}

BASE = "https://www.kawanrumor.com/"
CATEGORIES = [
    ("シングルオリジン豆", BASE + "?mode=cate&cbid=2674922&csid=0"),
    ("ブレンド豆", BASE + "?mode=cate&cbid=2674917&csid=0"),
]
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
ROAST_RE = re.compile(r"(フルシティ|シティ|ハイ|ミディアム|シナモン|ライト|フレンチ|イタリアン)ロースト(?!より|の少し|の手前)")
ORIGIN_HINTS = {"ガテマラ": "グアテマラ", "ブルーマウンテン": "ジャマイカ"}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "euc-jp"
    return r.text


def list_pids():
    out = []
    for cat, url in CATEGORIES:
        soup = BeautifulSoup(fetch(url), "html.parser")
        for a in soup.select('a[href*="?pid="]'):
            pid = a["href"].split("pid=")[1]
            if (cat, pid) not in out and pid not in [p for _, p in out]:
                out.append((cat, pid))
        time.sleep(DELAY)
    return out


def parse_detail(cat, pid, html_text):
    m = COLORME_RE.search(html_text)
    cm = json.loads(m.group(1))["product"] if m else {}
    name = (cm.get("name") or "").replace("<br>", " ")
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name)).strip()
    soup = BeautifulSoup(html_text, "html.parser")
    for x in soup(["script", "style"]):
        x.decompose()
    for br in soup.find_all("br"):
        br.replace_with(" ")
    txt = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))
    lines = [l.strip() for l in txt.split("\n") if l.strip()]

    def after(label, lines=lines):
        return lines[lines.index(label) + 1] if label in lines and lines.index(label) + 1 < len(lines) else None

    cap = after("容量")
    wm = re.match(r"(\d+)\s*g", cap or "")
    weight = int(wm.group(1)) if wm else None
    pm = re.match(r"([\d,]+)円", after("販売価格") or "")
    price = int(pm.group(1).replace(",", "")) if pm else None

    # 焙煎士寸評(「生産情報」「商品について」の手前まで)
    note_lines = []
    if "焙煎士寸評" in lines:
        for l in lines[lines.index("焙煎士寸評") + 1:]:
            if l in ("生産情報", "商品について", "カフェイン処理", "About"):
                break
            note_lines.append(l)
    note = "".join(note_lines) or None

    info = {}
    if "生産情報" in lines:
        i = lines.index("生産情報") + 1
        while i + 1 < len(lines) and lines[i] != "About":
            info[lines[i]] = lines[i + 1]
            i += 2

    is_blend = cat == "ブレンド豆" or "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            for kw, c in ORIGIN_HINTS.items():
                if kw in name:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
                    break
        parsed = apply_category_hint_fallback(parsed, name)
    if is_blend:
        # ブレンドの商品ページに生産情報が残っている場合(アメリカンブレンド)は、単一産地の
        # 情報の転記と見なして採用しない
        info = {}
    if "ミディアムボディ" in name:  # 「ミディアムボディ」はボディの強さで焙煎度ではない
        parsed["roast_level"] = None
    proc = info.get("生産処理")
    if proc:
        parsed["processing_method"] = normalize_processing_method(proc.split("・")[0])
    grade = info.get("規格") or info.get("グレード") or info.get("グレード・スクリーン")
    roast = parsed["roast_level"]
    hint = None
    if note:
        rm = ROAST_RE.search(note)
        if rm and not roast:
            roast = rm.group(1) + "ロースト"
        found = [kw for kw in ("浅煎り", "深煎り") if kw in note]
        if len(found) == 1 and "中煎り" not in note:  # 浅・中・深のブレンドの説明は除く
            hint = found[0]
    farm = [f"{k}: {info[k]}" for k in ("生産地域", "農園名", "標高", "品種") if info.get(k)]

    sold_out = any(w in txt for w in ("SOLD OUT", "売り切れ", "品切れ", "在庫切れ"))
    stock = detect_stock_status(name, sold_out)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": grade or parsed["grade"],
        "roast_level": roast,
        "roast_hint": hint,
        "flavor_notes": note,
        "farm_note": "、".join(farm) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock,
        "out_of_stock": stock != "販売中",
        "product_url": f"{BASE}?pid={pid}",
    }


def scrape_all_products():
    records = []
    for cat, pid in list_pids():
        records.append(parse_detail(cat, pid, fetch(f"{BASE}?pid={pid}")))
        time.sleep(DELAY)
    return records


def main():
    records = scrape_all_products()
    with open("data_kawanrumor.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kawanrumor.json に出力しました")


if __name__ == "__main__":
    main()
