# -*- coding: utf-8 -*-
"""
scrape_goshcoffee.py

GOSH(自家焙煎珈琲店 GOSH。北海道上川郡美瑛町美馬牛北3丁目4-21、カラーミーショップ gosh-coffee.shop-pro.jp)の
自家焙煎コーヒー豆を取得する。

【対象】カテゴリ「珈琲豆」(cbid=2118578、全22商品)。パン・お菓子・ギフト・頒布会(定期)カテゴリは対象外。
【価格】オプション「珈琲豆の状態」の先頭「豆のまま」の税込価格。
【重量】商品名の「(100g)」「(200g)」表記から取得。名称に重量表記が無い4商品
(イブラヒム モカ ブレンド/ブラジル パライーソ No,2/ルワンダ スカイヒル/ブラジル ボンジャルディン農園)は
商品ページにも内容量の記載が無いため None。
【焙煎度】商品名に含まれるもの(シティ/フレンチ/深煎り等)と、商品説明文に明示された3商品(ROAST_OVERRIDE)のみ。
【文字コード】EUC-JP。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "GOSH",
    "url": "https://gosh-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道上川郡美瑛町美馬牛北3丁目4-21",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ gosh-coffee.shop-pro.jp のカテゴリ「珈琲豆」と各商品ページを2026-10-26に確認。"
                   "特定商取引法表記(自家焙煎珈琲店GOSH、運営統括責任者 阪井雄介)。"
                   "公式サイト gosh-coffee.com/coffee/ に「直火式の小型焙煎機を使ってゆっくり火を入れ焙煎しています」、"
                   "gosh-coffee.com/access/ に所在地・営業時間・定休日(火水)の記載。"
                   "ショップのお知らせは2026-09-26(GOSH NEWS Vol.289)まで更新、11月のブレンドを掲載(10月のブレンドは掲載終了)。"
                   "名称に重量表記が無い4商品は内容量不明のため重量 None。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://gosh-coffee.shop-pro.jp/"
CAT_URL = BASE_URL + "?mode=cate&cbid=2118578&csid=0&page={page}"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
ROAST_RE = re.compile(r"(極深煎|中深煎|中浅煎|深煎|浅煎|中煎)")
# 商品名に焙煎度が無く、商品説明文に明示されているもの(説明文の引用は SHOP_INFO ではなく報告書に記載)
ROAST_OVERRIDE = {
    "101295723": "中深煎り",  # メキシコ クステペック農園「中深煎りに仕上げます」
    "185661456": "深煎り",    # ブラジル ボンジャルディン農園「ブラジルの深煎りを楽しんで」
    "101295768": "深煎り",    # ブラジル パライーソ No,2「GOSHの深煎りでお楽しみ」
}
# coffee_parser が産地を判定できない銘柄名の補完(商品名・商品説明文に明記されているもの)
ORIGIN_OVERRIDE = {
    "101295382": "イエメン",  # イブラヒム モカ(説明文「イエメンの奥地より」)
    "193160743": "タイ",      # タイランド ブルームーン
}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.content.decode("euc-jp", errors="replace")


def list_pids():
    pids = []
    for page in range(1, 6):
        html = fetch(CAT_URL.format(page=page))
        time.sleep(DELAY)
        soup = BeautifulSoup(html, "html.parser")
        new = 0
        for li in soup.select("li.product-list__unit"):
            a = li.select_one("a[href*='pid=']")
            m = re.search(r"pid=(\d+)", a["href"]) if a else None
            if m and m.group(1) not in pids:
                pids.append(m.group(1))
                new += 1
        if new == 0 or "page=%d" % (page + 1) not in html:
            break
    return pids


def norm(s):
    s = unicodedata.normalize("NFKC", s.replace("　", " "))
    return re.sub(r"\s+", " ", s).strip()


def get_desc(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l]
    try:
        i = lines.index("オプションの値段詳細")
    except ValueError:
        return None
    # 説明文は「ショッピングを続ける」(カート追加ダイアログ)の次の行から「オプションの値段詳細」の手前まで
    j = max(k for k, l in enumerate(lines[:i]) if l == "ショッピングを続ける")
    txt = " ".join(lines[j + 1:i])
    return norm(txt)[:300] or None


def build(pid):
    url = BASE_URL + "?pid=" + pid
    html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    raw = norm(p["name"])
    variants = p.get("variants") or []
    beans = [v for v in variants if (v.get("option1_value") or "").strip() == "豆のまま"] or variants
    price = beans[0]["option_price_including_tax"] if beans else p["sales_price_including_tax"]
    stock = p.get("stock_num")
    out = isinstance(stock, int) and stock <= 0
    wm = re.search(r"(\d+)\s*g", raw, re.I)
    weight = int(wm.group(1)) if wm else None
    rm = ROAST_RE.search(raw)
    parsed = parse_product(raw)
    roast = (rm.group(1) + "り") if rm else (ROAST_OVERRIDE.get(pid) or parsed["roast_level"])
    if "ブレンド" in raw:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, raw)
    if pid in ORIGIN_OVERRIDE and not parsed["origin_country"]:
        parsed["origin_country"] = ORIGIN_OVERRIDE[pid]
        parsed["origin_source"] = "manual"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": get_desc(html),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def main():
    pids = list_pids()
    print(f"[info] 対象 {len(pids)}件")
    records = []
    for pid in pids:
        time.sleep(DELAY)
        try:
            rec = build(pid)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {pid} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_goshcoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_goshcoffee.json に出力しました")


if __name__ == "__main__":
    main()
