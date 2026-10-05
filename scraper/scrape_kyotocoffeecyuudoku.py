# -*- coding: utf-8 -*-
"""
scrape_kyotocoffeecyuudoku.py

京都珈琲中毒製作所(coffeecyuudoku.shop-pro.jp、京都府京都市右京区西院下花田町15-2)の
商品情報を取得する。カラーミーショップ(shop-pro.jp、EUC-JP)。

【対象商品について】
実データ確認済み: サイト内検索(?mode=srh)の全12件はすべて「焙煎コーヒー豆」(ストレート
10・ブレンド2、カフェインレス1含む)で、全件を対象とする。ドリップバッグ・器具等は
掲載なし。

【重量・価格について】
商品名・価格の基準表記は「生豆200g」で、ご注文後に焙煎して発送する(焙煎度は
「おまかせ/浅煎り/中煎り/中深煎り/深煎り」と挽き方をバリエーションで選択)。このため
価格は焙煎前の生豆200g分であり、焙煎後の実重量(通常15〜20%程度目減り)ではない。
weight_gは表記どおり200とし、unit_noteで「生豆200g表記・注文後焙煎」と明示する。
焙煎度は注文時に選ぶため roast_level はnull、roast_selectable=True、
roast_hintに店のおすすめ焙煎度を記録する。

【在庫状態について】
商品ページのカートボタンが無効(sold out表記)の場合のみ完売とする(全件販売中を確認)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (parse_product, apply_category_hint_fallback, detect_country_name,
                           detect_processing_method)

SHOP_INFO = {
    "name": "京都珈琲中毒製作所",
    "url": "https://coffeecyuudoku.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "京都府京都市右京区西院下花田町15-2",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(カラーミーショップ標準構成)",
}

BASE_URL = "https://coffeecyuudoku.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
UNIT_NOTE = "生豆200g表記(ご注文後に焙煎するため、焙煎後の実重量は目減りする)"
RECOMMEND_PATTERN = re.compile(r"おすすめは、?\s*([^\s、。で]*?煎り)")
BOILERPLATE_PREFIXES = ("京都西院に位置する", "ご注文を頂いてから", "ご注文を頂いて")
COUNTRY_LABEL = re.compile(r"(?:原産国|生産国)\s*([^\s\n]+)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "euc-jp"
    return resp.text


def collect_product_ids() -> list[str]:
    ids = []
    for page in range(1, 10):
        html = fetch(f"{BASE_URL}?mode=srh&cid=&keyword=&sort=n&page={page}")
        new = [i for i in dict.fromkeys(re.findall(r"pid=(\d+)", html)) if i not in ids]
        if not new:
            break
        ids += new
    return ids


def clean_name(title: str) -> str:
    t = re.sub(r"<br\s*/?>", " ", title)
    t = t.replace("焙煎コーヒー豆", "")
    t = re.sub(r"/?\s*生豆\s*\d+\s*[gｇ]", "", t, flags=re.I)
    t = re.sub(r"[\s　]+", " ", t).strip(" /")
    return t


def build_record(pid: str) -> dict | None:
    html = fetch(f"{BASE_URL}?pid={pid}")
    m = re.search(r"var\s+Colorme\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = product.get("name") or ""
    if not title or "ドリップ" in title:
        return None
    wm = re.search(r"生豆\s*(\d+)\s*[gｇ]", title)
    weight = int(wm.group(1)) if wm else None
    name = clean_name(title)

    soup = BeautifulSoup(html, "html.parser")
    btn = soup.select_one(".product-order-input button")
    sold_out = bool(btn and "sold out" in btn.get_text().lower())

    exp = soup.select_one("div.product-order-exp")
    desc_raw = ""
    if exp:
        for br in exp.find_all("br"):
            br.replace_with("\n")
        desc_raw = exp.get_text()
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", desc_raw)]
    paragraphs = [p for p in paragraphs if p and not p.startswith(BOILERPLATE_PREFIXES)]
    desc = " ".join(paragraphs)
    desc = re.sub(r"[★⁂]\s*", "", desc).strip()

    rec_m = RECOMMEND_PATTERN.search(desc_raw)
    roast_hint = f"注文時に焙煎度を選択(おすすめ: {rec_m.group(1)})" if rec_m else "注文時に焙煎度を選択"

    is_blend = "ブレンド" in name
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        if not parsed["origin_country"]:
            cm = COUNTRY_LABEL.search(desc)
            c = detect_country_name(cm.group(1)) if cm else None
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "description"
        if not parsed["origin_country"]:
            c = detect_country_name(desc)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "description"
        parsed = apply_category_hint_fallback(parsed, name)

    processing = parsed["processing_method"]
    pm = re.search(r"精製方法\s*([^\s]+)", desc_raw)
    if pm and not is_blend:
        raw = pm.group(1).replace("ウオッシュド", "ウォッシュド")
        processing = detect_processing_method(raw) or raw

    tags = list(parsed["post_processing_tags"])

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_selectable": True,
        "roast_hint": roast_hint,
        "flavor_notes": desc[:400] or None,
        "farm_note": None,
        "post_processing_tags": tags,
        "blend_components": [],
        "price": product.get("sales_price_including_tax"),
        "weight_g": weight,
        "unit_note": UNIT_NOTE,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in collect_product_ids():
        try:
            rec = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kyotocoffeecyuudoku.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kyotocoffeecyuudoku.json に出力しました")


if __name__ == "__main__":
    main()
