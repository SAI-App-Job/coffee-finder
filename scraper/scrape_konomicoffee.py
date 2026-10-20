# -*- coding: utf-8 -*-
"""
scrape_konomicoffee.py

このみ珈琲(福岡県直方市殿町2-9)の公式EC(https://shop.konomi-coffee.biz/、カラーミーショップ、EUC-JP)から
自家焙煎コーヒー豆の商品情報を取得する。

【実店舗・自家焙煎の根拠】
公式サイト https://konomi-coffee.biz/ トップのACCESSに「〒822-0017 福岡県直方市殿町 2-9」(営業時間・定休日木曜日あり)、
「1995年1月にスタートしたスペシャルティコーヒー専門店」「店内の奥には、小さなカフェスペースがあり」、
https://konomi-coffee.biz/features/ に「当店では、焙煎機は直火式焙煎機を使用しています」「焙煎してから３日以内のものを発送」。

【対象商品について】
ショップのカテゴリ(ブレンド・各産地・カフェインレス)に出る豆の商品を対象とし、全商品200g(「豆のまま」を選択可、
粉の挽き分けは同価格)。除外: お試し＆特別おすすめセット、コーヒーバッグ、リキッドアイスコーヒー、コーヒーグッズ、
ギフトセット、ドリップバッグ(いずれも対象カテゴリ外)。商品が登録されていない産地カテゴリ(エルサルバトル等)はHTTP 404。
在庫は「カゴに入れる」ボタンの有無で判定(ボタンが無ければ品切れ)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "このみ珈琲",
    "url": "https://shop.konomi-coffee.biz/",
    "platform": "カラーミーショップ",
    "address": "福岡県直方市殿町2-9",
    "prefecture": "福岡県",
    "robots_txt_status": "許可(2026-10-20確認。shop.konomi-coffee.biz は /secure/ と /cart/ のみDisallow、AhrefsBot等のSEO系ボットのみ全面禁止。konomi-coffee.biz は /wp-admin/ のみ)",
    "source_note": "公式EC(https://shop.konomi-coffee.biz/ のカテゴリ一覧と各商品ページ)を2026-10-20に取得。店舗情報は公式サイト https://konomi-coffee.biz/ と /features/(直火式焙煎機で焙煎)で確認。最新の入荷お知らせは2026/10/17(グアテマラ)で更新は新しい",
    "last_verified_at": "2026-10-20",
}

BASE = "https://shop.konomi-coffee.biz/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 1.6
# 豆が登録されているカテゴリ(ブレンド・産地別・カフェインレス)。cbid -> カテゴリ名
CATEGORIES = {
    2887346: "ブレンドコーヒー", 2887347: "ブラジル", 2887348: "コロンビア", 2887349: "グアテマラ",
    2887350: "タンザニア", 2887351: "ケニア", 2887352: "エチオピア", 2887353: "インドネシア",
    2887362: "コスタリカ", 2887367: "カフェインレスコーヒー",
}
ROAST_PATTERN = re.compile(r"[〔\[]([^〕\]]*ロースト)[〕\]]")


def fetch(url: str):
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.encoding = "euc-jp"
    return resp


def collect_pids() -> list[tuple[str, str]]:
    pids, seen = [], set()
    for cbid, cname in CATEGORIES.items():
        resp = fetch(f"{BASE}?mode=cate&cbid={cbid}&csid=0")
        time.sleep(REQUEST_INTERVAL)
        if resp.status_code != 200:
            print(f"[warn] カテゴリ取得失敗 {cname} HTTP {resp.status_code}")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select('a[href*="?pid="]'):
            pid = re.search(r"pid=(\d+)", a["href"]).group(1)
            if pid not in seen:
                seen.add(pid)
                pids.append((pid, cname))
    return pids


def parse_page(pid: str, cname: str):
    resp = fetch(f"{BASE}?pid={pid}")
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗 pid={pid} HTTP {resp.status_code}")
        return None
    raw = resp.text
    soup = BeautifulSoup(raw, "html.parser")
    lines = soup.get_text("\n", strip=True).split("\n")
    k = lines.index("カゴの中身を見る")
    k2 = next(i for i in range(k + 1, len(lines)) if lines[i] != "ショッピングを続ける")
    title = unicodedata.normalize("NFKC", lines[k2])
    pm = re.search(r"([\d,]+)円\(税込\)", "\n".join(lines[k:k + 12]))
    price = int(pm.group(1).replace(",", "")) if pm else None
    # 説明文: DETAIL 直後〜区切り線(---)または「コーヒーの焙煎」の手前の冒頭数行
    d = lines.index("DETAIL")
    desc_lines = []
    for ln in lines[d + 1:]:
        if ln.startswith("---") or ln.startswith("コーヒーの焙煎") or ln.startswith("▼Staff") or ln.startswith("※画像"):
            break
        desc_lines.append(ln)
    desc = unicodedata.normalize("NFKC", " ".join(desc_lines)).strip() or None
    if desc and len(desc) > 300:
        desc = desc[:300].rstrip() + "…"
    in_stock = "カゴに入れる" in raw
    return title, price, desc, in_stock


def build(pid: str, cname: str):
    got = parse_page(pid, cname)
    if not got:
        return None
    title, price, desc, in_stock = got
    wm = re.search(r"[（(]\s*(\d+)\s*g\s*[）)]", title)
    weight = int(wm.group(1)) if wm else None
    name = re.sub(r"[（(]\s*\d+\s*g\s*[）)]", " ", title)
    rm = ROAST_PATTERN.search(name)
    bracket_roast = rm.group(1) if rm else None
    if bracket_roast and cname == "ブレンドコーヒー":
        name = ROAST_PATTERN.sub(" ", name)   # ブレンドは〔ハイロースト〕を焙煎度に回す
    name = re.sub(r"\s+", " ", name).strip()
    is_decaf = "カフェインレス" in name
    parsed = parse_product(name + (f" {bracket_roast}" if bracket_roast and cname == "ブレンドコーヒー" else ""))
    if cname == "ブレンドコーヒー":
        # 商品名末尾の〔ハイロースト〕等が公式の焙煎度表記(「ブライト」の「ライト」等の部分一致誤爆を避けて直接採用)
        if bracket_roast:
            parsed["roast_level"] = bracket_roast
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, cname)
        parsed["category"] = "デカフェ" if is_decaf else "ストレート"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": f"{BASE}?pid={pid}",
    }


def scrape_all_products() -> list:
    records = []
    for pid, cname in collect_pids():
        rec = build(pid, cname)
        time.sleep(REQUEST_INTERVAL)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_konomicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_konomicoffee.json に出力しました")


if __name__ == "__main__":
    main()
