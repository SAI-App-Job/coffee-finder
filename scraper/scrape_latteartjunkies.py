# -*- coding: utf-8 -*-
"""
scrape_latteartjunkies.py

Latteart Junkies Roastingshop(ラテアート・ジャンキーズ ロースティングショップ、京都府京都市上京区西堀川通り下立売上る
四町目55番地 堀川下立売団地101号)のオンラインショップ(https://junkies-cafe.com/onlineshop.html、
ec-sites.jp カートの独自HTML)から焙煎豆の商品情報を取得する。

【ページ構造】onlineshop.html の「珈琲豆」節に `div.goodsbox`(商品名・商品コード・価格)が並び、各商品に
onlineshop/C-xxx.html の個別ページ(特徴欄に生産地・品種・精製・焙煎度合・フレーバー)がある。
【対象】ブレンド3種(200g/400g/2kg)は最小の200g、デカフェブレンド、シングルオリジンは商品名末尾の重量(100g/200g)。
除外: 三種のブレンド味比べセット、ギフトセット(箱のみ)、ドリップバッグ、リキッド、定期便、ポスト投函商品の重複掲載、
コメントアウトされた商品(販売終了)。
在庫: ページに在庫表示は無いため、一覧に載っている商品は販売中とする(個別ページに売り切れ表記があれば完売)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "Latteart Junkies Roastingshop",
    "url": "https://junkies-cafe.com/onlineshop.html",
    "platform": "ec-sites.jp カート(独自HTML)",
    "address": "京都府京都市上京区西堀川通り下立売上る四町目55番地 堀川下立売団地101号",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(2026-10確認。robots.txtは404=制限なし)",
    "source_note": "オンラインショップ https://junkies-cafe.com/onlineshop.html の「珈琲豆」節と各商品ページ(onlineshop/C-xxx.html)を2026-10-21に確認。「10月末まで3,000円(税抜)以上送料無料」の告知あり(2026年10月)",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://junkies-cafe.com"
LIST_URL = BASE_URL + "/onlineshop.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 1.6
EXCLUDE = ("セット", "ドリップ", "リキッド", "ギフト", "ジュース", "ベース", "ColdBrew", "ゼリー", "定期")
ROAST_MAP = {
    "ライト": "浅煎り", "シナモン": "浅煎り", "ミディアムライト": "中浅煎り", "ミディアム": "中浅煎り",
    "ハイ": "中煎り", "シティ": "中深煎り", "フルシティ": "深煎り", "フレンチ": "深煎り", "イタリアン": "深煎り",
}
JP_ROAST = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
COUNTRIES = ["エチオピア", "ケニア", "ブラジル", "パナマ", "カメルーン", "コロンビア", "コスタリカ", "グアテマラ", "インドネシア"]
ENG_COUNTRY = {"Ethiopia": "エチオピア", "Kenya": "ケニア", "Brazil": "ブラジル", "Panama": "パナマ",
               "Cameroun": "カメルーン", "Cameroon": "カメルーン", "Columbia": "コロンビア", "Colombia": "コロンビア",
               "Costa Rica": "コスタリカ", "Guatemala": "グアテマラ"}

_last = [0.0]


def fetch(url):
    wait = INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    _last[0] = time.time()
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def scrape_list():
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")
    h3 = next((h for h in soup.find_all("h3") if h.get_text(strip=True) == "珈琲豆"), None)
    ul = h3.find_next("ul") if h3 else None
    items = []
    for box in (ul.select("div.goodsbox") if ul else []):
        a = box.find("a")
        p = box.find("p")
        if not a or not p:
            continue
        name = unicodedata.normalize("NFKC", p.get_text(" ", strip=True))
        name = re.sub(r"\s*C-[\d/]+\s*$", "", name).strip()
        if any(k in name for k in EXCLUDE):
            continue
        kakaku = box.select_one("p.kakaku")
        ktext = unicodedata.normalize("NFKC", kakaku.get_text(" ", strip=True)) if kakaku else ""
        # 「200g \ 2,200 400g \ 3,600 ...」または「\ 2,900」
        pairs = re.findall(r"(\d+)\s*(kg|g)\s*\\?\s*([\d,]+)", ktext)
        options = []
        for w, unit, pr in pairs:
            options.append((int(w) * (1000 if unit == "kg" else 1), int(pr.replace(",", ""))))
        if not options:
            pm = re.search(r"\\?\s*([\d,]+)", ktext)
            wm = re.search(r"(\d+)\s*g\b", name)
            if pm and wm:
                options.append((int(wm.group(1)), int(pm.group(1).replace(",", ""))))
        if not options:
            continue
        w, price = min(options)
        items.append({"name": name, "href": a["href"], "weight": w, "price": price})
    return items


def fetch_detail(href):
    soup = BeautifulSoup(fetch(f"{BASE_URL}/{href}"), "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    t = soup.get_text("\n", strip=True)
    a = t.find("特徴")
    b = t.find("会員ログイン", a)
    block = t[a + 2:b].strip() if a >= 0 and b > a else ""
    sold = bool(re.search(r"SOLD\s*OUT|売り切れ|在庫切れ|完売", t))
    return block, sold


def parse_block(block):
    """特徴欄から (焙煎度, 生産地, 説明文) を取り出す。"""
    roast = None
    m = re.search(r"焙煎度合い?\s*[:：]\s*([^\n]+)", block)
    if m:
        v = unicodedata.normalize("NFKC", m.group(1)).strip()
        jp = JP_ROAST.search(v)
        roast = ROAST_MAP.get(v) or (jp.group(1) if jp else None)
    else:
        first = block.split("\n")[0]
        if JP_ROAST.fullmatch(first.strip()):
            roast = first.strip()
    origin_m = re.search(r"生産地\s*[:：]\s*([^\n]+)", block)
    kv = re.compile(r"^(生産地|品\s*種|標\s*高|サイズ|精製方法|乾燥方法|焙煎度合い?|フレーバー|規格)\s*[:：]")
    desc_lines = [l for l in block.split("\n") if not kv.match(l) and not JP_ROAST.fullmatch(l.strip())]
    flavor_m = re.search(r"フレーバー\s*[:：]\s*([^\n]+)", block)
    if roast is None:  # 説明文が「深煎りでシッカリと…」「中煎甘さが…」のように焙煎度で始まる商品
        for l in desc_lines:
            lm = re.match(r"(中深煎|中浅煎|浅煎|中煎|深煎)", l.strip())
            if lm:
                roast = lm.group(1) + "り"
                break
    desc = "\n".join(desc_lines).strip()
    if flavor_m:
        desc = "フレーバー: " + flavor_m.group(1).strip() + ("\n" + desc if desc else "")
    return roast, (origin_m.group(1).strip() if origin_m else None), desc or None


def clean_name(name):
    n = re.sub(r"\s*/\s*\d+\s*g$", "", name).strip()
    n = n.replace("Junkies・blend", "Junkies Blend").replace("・", " ")
    n = re.sub(r"(?i)chocolate\s*blend", "Chocolate Blend", n)
    n = re.sub(r"(?i)dark\s*roast\s*blend", "Dark Roast Blend", n)
    n = re.sub(r"(?i)decaf\s*blend", "DeCaf Blend", n)
    return re.sub(r"\s+", " ", n).strip()


def build_record(it, roast, origin_text, desc, sold):
    name = clean_name(it["name"])
    is_blend = "Blend" in name
    parsed = parse_product(name)
    if is_blend:
        category, origin, origin_source, brand = "ブレンド", None, None, None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        category = "ストレート"
        origin, origin_source = None, None
        for en, jp in ENG_COUNTRY.items():
            if name.startswith(en):
                origin, origin_source = jp, "raw_name"
                break
        if origin is None and origin_text:
            for jp in COUNTRIES:
                if jp in origin_text:
                    origin, origin_source = jp, "shop_attribute"
                    break
        brand = parsed["designated_brand"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": origin_source,
        "designated_brand": brand,
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": origin_text if not is_blend else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "完売" if sold else "販売中",
        "out_of_stock": sold,
        "product_url": f"{BASE_URL}/{it['href']}",
    }


def scrape_all_products():
    records = []
    for it in scrape_list():
        block, sold = fetch_detail(it["href"])
        roast, origin_text, desc = parse_block(block)
        records.append(build_record(it, roast, origin_text, desc, sold))
    return records


def main():
    records = scrape_all_products()
    with open("data_latteartjunkies.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_latteartjunkies.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_level"], r["stock_status"], r["farm_note"])


if __name__ == "__main__":
    main()
