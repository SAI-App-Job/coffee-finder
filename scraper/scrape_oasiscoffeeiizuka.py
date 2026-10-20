# -*- coding: utf-8 -*-
"""
scrape_oasiscoffeeiizuka.py

オアシス珈琲(オアシス珈琲有限会社、福岡県飯塚市堀池133-9)の公式EC(https://oasiscoffee.co.jp/、ショップサーブ)から
レギュラーコーヒー豆(ブレンド・ストレート)の商品情報を取得する。
(大阪の「SPECIALTY COFFEE OASIS」= scrape_oasiscoffee.py とは別店舗のため slug は oasiscoffeeiizuka)

【実店舗・自家焙煎の根拠】
会社概要 https://oasiscoffee.co.jp/hpgen/HPB/entries/5.html に「オアシス珈琲有限会社 〒820-0070 福岡県飯塚市堀池133-9」
(営業時間9:00-18:00、土日祝休)。トップページに「世界の産地から届いた珈琲生豆を先ず、独自の洗浄技術(特許第6528231)できれいに洗浄してから焙煎」、
「焙煎し立ての珈琲をできるだけ早くお客様のお手元にお届け」、沿革ページ(entries/2.html)に「焙煎仕立ての珈琲をお届け」。
筑豊情報マガジンWING(https://wing-r.com/oasis-coffee/ 2024.03.11)に「飯塚市堀池に本社を構える創業35年のオアシス珈琲」、
「『きれいなコーヒー』は本店ではもちろん、こちらのイオン穂波店でも販売」(本店+イオン穂波店の2店舗の記述)。

【対象商品】
カテゴリ「コーヒー(豆・粉)」(250565、全45件・5ページ)のうちブレンド(RB-*)12件・ストレート(RS-*)25件の計37件。全て1袋200g、
「豆」「粉」の選択は同価格のため豆のままの価格。除外: レギュラー珈琲セット(TS-*)・セレクトコース(SS-*)・ドリップバッグ・エキス・ビーンズバッグ・
お菓子・生豆・ギフト・定期購入。在庫は商品ページの「在庫:」記号で判定(○=販売中)。
注意: アイスコーヒー(RS-070)・フレンチロースト(RS-061)・イタリアンロースト(RS-060)は店のカテゴリ上「ストレート」だが産地の表記がなく、産地はnullにしている。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "オアシス珈琲",
    "url": "https://oasiscoffee.co.jp/",
    "platform": "ショップサーブ",
    "address": "福岡県飯塚市堀池133-9",
    "prefecture": "福岡県",
    "robots_txt_status": "robots.txtなし(404、2026-10-20確認。制限の記載なし)",
    "source_note": "公式EC(https://oasiscoffee.co.jp/SHOP/250565/list.html ほか5ページと各商品ページ)を2026-10-20に取得。会社概要 https://oasiscoffee.co.jp/hpgen/HPB/entries/5.html と WING(https://wing-r.com/oasis-coffee/)で本店・イオン穂波店を確認。EC内に更新日の記載は見当たらない",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://oasiscoffee.co.jp"
LIST_URL = BASE_URL + "/SHOP/250565/list{n}.html"
PAGES = [""] + [str(n) for n in range(2, 6)]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 1.6


def fetch(url: str) -> BeautifulSoup:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[dict]:
    """説明付き一覧(1ページ10件・全5ページ)から RB-*/RS-* の豆を集める。"""
    items = []
    for n in PAGES:
        soup = fetch(LIST_URL.format(n=n))
        time.sleep(REQUEST_INTERVAL)
        for a in soup.select('a[href^="/SHOP/R"]'):
            m = re.match(r"/SHOP/(R[BS]-\d+)\.html$", a["href"])
            title = a.get_text(strip=True)
            if not m or not title:
                continue
            code = m.group(1)
            if any(i["code"] == code for i in items):
                continue
            # 同じ商品のブロックから価格と説明を取る(a の親を遡って「¥」を含む要素)
            blk = a
            for _ in range(5):
                blk = blk.parent
                if blk is not None and "¥" in blk.get_text() and len(blk.select('a[href^="/SHOP/R"]')) == 1:
                    break
            text = blk.get_text("\n", strip=True).split("\n")
            pm = re.search(r"¥([\d,]+)", "\n".join(text))
            desc = None
            for ln in text:
                if re.search(r"1袋\s*\d+\s*g", ln):
                    desc = ln
            items.append({"code": code, "title": title, "price": int(pm.group(1).replace(",", "")) if pm else None, "desc": desc})
    return items


def stock_ok(code: str) -> bool:
    soup = fetch(f"{BASE_URL}/SHOP/{code}.html")
    th = soup.find("th", string=re.compile(r"在庫"))
    if not th:
        return True
    td = th.find_next("td")
    mark = td.get_text(strip=True) if td else ""
    return mark.startswith("○") or mark.startswith("◎") or mark.startswith("△")


def clean(title: str, code: str):
    t = unicodedata.normalize("NFKC", title)
    tags = re.findall(r"【([^】]*)】", t)
    t = re.sub(r"【[^】]*】", "", t).strip()
    roast_hint = next((x for x in tags if "煎り" in x), None)
    if "有機" in tags:
        t = f"{t} 有機"
    if "カフェインレス" in tags:
        t = f"{t} カフェインレス"
    if "月替わりブレンド" in tags:
        t = f"月替わりブレンド {t}".replace("/", " ")
    return re.sub(r"\s+", " ", t).strip(), roast_hint, tags


def scrape_all_products() -> list:
    records = []
    for it in list_items():
        name, roast_hint, tags = clean(it["title"], it["code"])
        time.sleep(REQUEST_INTERVAL)
        in_stock = stock_ok(it["code"])
        is_blend = it["code"].startswith("RB-")
        is_decaf = "カフェインレス" in tags
        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "デカフェ" if is_decaf else "ストレート"
        if not is_blend and not parsed["origin_country"] and "エチオピアモカ" in (it["desc"] or ""):
            parsed["origin_country"] = "エチオピア"       # 「モカ」「ゴールドモカ」は説明文に「エチオピアモカ」と明記
            parsed["origin_source"] = "shop_attribute"
        wm = re.search(r"1袋\s*(\d+)\s*g", it["desc"] or "")
        desc = re.sub(r"[(（]\s*1袋\s*\d+\s*g\s*[)）]\s*$", "", it["desc"] or "").strip() or None
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": roast_hint,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": it["price"],
            "weight_g": int(wm.group(1)) if wm else None,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": f"{BASE_URL}/SHOP/{it['code']}.html",
        })
    return records


def main():
    records = scrape_all_products()
    with open("data_oasiscoffeeiizuka.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_oasiscoffeeiizuka.json に出力しました")


if __name__ == "__main__":
    main()
