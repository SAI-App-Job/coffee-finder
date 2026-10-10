# -*- coding: utf-8 -*-
"""
scrape_hakubacoffeestand.py

HAKUBA COFFEE STAND(hakubacoffeestand.com、運営: 合同会社白馬珈琲研究所、
長野県北安曇郡白馬村北城6360-2)のオンラインショップの商品情報を取得する。
カラーミーショップ(独自ドメイン、EUC-JP。var Colorme が出力される)。

【対象商品】カテゴリ「自家焙煎珈琲豆」(gid=2916336)の23点(ストレート・ブレンド・カフェインレス)。
ディップバッグ、器具、タオル、コラボ商品、お土産、飲料、おまかせ豆の定期便は除外
(カテゴリ自体を取得しないため混入しないが、セット/定期便/ディップのキーワードでも念のため除外)。
【重量・価格】商品名末尾の「150g」と、税込価格(var Colorme の sales_price_including_tax)。
バリエーションなし(単一重量150g)。
【産地・焙煎度】商品名の国名と「（中深煎り）」表記から取得。ブレンドは説明文から補完。
【在庫】構造化された在庫情報は無い。「カートに入れる」ボタンが無い/SOLD OUT表記で品切れ判定。

robots.txt確認済み(2026-10): /secure/と/cart/のみDisallow(User-agent: *)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "HAKUBA COFFEE STAND",
    "url": "https://hakubacoffeestand.com/",
    "platform": "カラーミーショップ(独自ドメイン)",
    "address": "長野県北安曇郡白馬村北城6360-2",
    "prefecture": "長野県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE = "https://hakubacoffeestand.com/"
GROUP_URL = BASE + "?mode=grp&gid=2916336&page=%d"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN = ["ディップ", "ドリップバッグ", "定期便", "セット", "ギフト", "タオル"]
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*")
SOLD_RE = re.compile(r"SOLD\s*OUT|売り切れ|品切れ|在庫切れ|入荷待ち", re.I)
ROAST_RE = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
ORIGIN_OVERRIDES = {"インディア": "インド"}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "euc-jp"
    return r.text


def list_pids():
    pids = []
    for pg in range(1, 6):
        s = BeautifulSoup(get(GROUP_URL % pg), "html.parser")
        n = 0
        for a in s.find_all("a", href=True):
            m = re.search(r"\?pid=(\d+)", a["href"])
            if m and m.group(1) not in pids:
                pids.append(m.group(1))
                n += 1
        if not n:
            break
        time.sleep(1)
    return pids


def clean_name(title):
    n = title.replace("　", " ")
    n = re.sub(r"[（(]\s*(?:中浅煎り|中深煎り|浅煎り|中煎り|深煎り)\s*[）)]", " ", n)
    n = re.sub(r"\d+\s*g", " ", n)
    n = re.sub(r"\s*[A-Za-z][A-Za-z.\s]*$", "", n.strip())
    n = re.sub(r"\s+", " ", n).strip()
    return n


def build_record(pid):
    url = BASE + "?pid=" + pid
    h = get(url)
    m = COLORME_RE.search(h)
    prod = json.JSONDecoder().raw_decode(h[m.end():])[0]["product"]
    title = re.sub(r"\s+", " ", (prod.get("name") or "").replace("　", " ")).strip()
    if any(k in title for k in NON_BEAN):
        return None
    price = prod.get("sales_price_including_tax")
    wm = re.search(r"(\d+)\s*g", title)
    weight = int(wm.group(1)) if wm else None
    soup = BeautifulSoup(h, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    i = text.find("商品説明")
    j = text.find("おすすめ商品", i)
    desc = text[i + 4:j].strip() if i >= 0 and j > i else ""
    desc = re.sub(r"\s+", " ", desc)
    main = text[: i if i >= 0 else len(text)]
    sold = bool(SOLD_RE.search(main)) or "カートに入れる" not in main

    name = clean_name(title)
    rm = ROAST_RE.search(title)
    roast = rm.group(1) if rm else None
    if not roast:
        rm = re.search(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)", desc)
        roast = rm.group(1) if rm else None

    is_blend = "ブレンド" in title or "blend" in title.lower()
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        c = detect_country_name(title)
        if not c:
            for kw, cc in ORIGIN_OVERRIDES.items():
                if kw in title:
                    c = cc
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc[:300] or None,
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
    with open("data_hakubacoffeestand.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hakubacoffeestand.json に出力しました")


if __name__ == "__main__":
    main()
