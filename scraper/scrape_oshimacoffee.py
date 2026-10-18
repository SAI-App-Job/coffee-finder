# -*- coding: utf-8 -*-
"""
scrape_oshimacoffee.py

大島珈琲店(通販 https://oshimacoffee.cart.fc2.com/、公式 http://www.oc-ten.com/、
山口県宇部市新天町2丁目7-1)の焙煎豆の商品情報を取得する。FC2ショッピングカート(fc2.com サブドメイン)。

【店舗発見の経緯】
全国再調査(山口県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-15): 全144点のうち、カテゴリ「焙煎豆」(ca=3、51点、10件/ページ×6ページ)が対象。
51点は全て豆のまま/粗挽き/中挽き/細挽きの選択式の焙煎済み商品(スペシャリティ37・プレミアムストレート1・
スペシャリティーブレンド3・ブレンド3・ストレート4・ロースト3 の各サブカテゴリ)。
除外(収録しない): 生豆(ca=4、44点)、お得なセット(ca=25)、ネコポス送料無料セット(ca=32)、
オリジナルDrip Bag(ca=11)、ギフトセット(ca=10)、保存用袋(ca=24)。
100g単位で注文数を選べる(注文数: 100g〜1000g)ため、価格は100gあたりの税込価格で、100gを代表とする。
完売商品は注文数欄が無く、バリエーション欄が「[完売しました]」「[在庫000g]」表記になるため完売として収録(重量は100gと推定)。
産地は商品説明の【生産国・地域】や農園名から判断し、ページに国名が無い商品は農園情報で補った(下のORIGIN参照)。
ブレンドは商品説明に【ブレンド配合表】があるもの。「フレンチロースト」はマンデリンとコロンビアのミックス(ブレンド扱い)、
「アメリカンロースト」はブラジル産の豆を浅煎りしたもの(ストレート扱い)。
robots.txt: 確認済み(2026-10-15)。/cancel/・/setup/・/tools/ のみDisallow。
特商法(/laws)の販売業者・所在地は 大島珈琲店 / 山口県宇部市新天町2丁目7-1。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "大島珈琲店",
    "url": "http://www.oc-ten.com/",
    "platform": "FC2ショッピングカート(oshimacoffee.cart.fc2.com)",
    "address": "山口県宇部市新天町2丁目7-1",
    "prefecture": "山口県",
    "robots_txt_status": "許可(2026-10-15確認。/cancel/・/setup/・/tools/のみDisallow)",
}

BASE_URL = "https://oshimacoffee.cart.fc2.com"
CATEGORY_ID = 3  # 焙煎豆
PAGES = 6
CRAWL_DELAY_SECONDS = 1.5
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# 商品ID -> 産地(ストレートのみ)。商品説明の【生産国・地域】/農園名で判断。None=ページから判断不能
ORIGIN = {
    398: "ルワンダ", 397: "ドミニカ共和国", 396: "パナマ", 395: "ジャマイカ", 393: "グアテマラ",
    394: "パナマ", 385: "タンザニア", 383: "エチオピア", 373: "ドミニカ共和国", 84: "セントヘレナ",
    348: "ジャマイカ", 359: "ジャマイカ", 1: "ジャマイカ", 132: "グアドループ", 277: "アメリカ(ハワイ)",
    344: "グアテマラ", 361: "コスタリカ", 351: "グアテマラ", 342: "コスタリカ", 257: "パナマ",
    337: "コスタリカ", 166: "コスタリカ", 331: "エルサルバドル", 204: "イエメン", 6: "エクアドル",
    301: "コスタリカ", 329: "グアテマラ", 272: "エクアドル", 264: "エルサルバドル", 265: None,
    274: "エチオピア", 5: "イエメン", 253: "タンザニア", 89: "エチオピア", 15: "グアテマラ",
    236: "ブラジル", 134: "ボリビア", 17: "インドネシア", 13: "インドネシア", 14: "タンザニア",
    12: "コロンビア", 8: "ブラジル", 75: "ブラジル",
}
BLEND_IDS = {29, 20, 27, 24, 23, 22, 77, 76}
# ページに焙煎度の記載が無い/複数あるものの補正
ROAST_OVERRIDE = {17: "ハイロースト", 75: "浅煎り", 76: "深煎り"}
ROAST_MAP = {"ミディアム": "ミディアムロースト", "ハイ": "ハイロースト", "ハイロースト": "ハイロースト"}

ROAST_PATTERN = re.compile(r"【焙\s*煎\s*度\s*合\s*い】\s*\n\s*([^\n]+)")
PRICE_PATTERN = re.compile(r"価格：\s*([\d,]+)円")
SOLD_OUT_PATTERN = re.compile(r"完売|在庫\s*0+\s*g|在庫切れ|品切れ")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_items() -> list[tuple[int, str, str]]:
    """(商品ID, 一覧上の商品名, 商品パス) を返す。"""
    items = []
    seen = set()
    for p in range(PAGES):
        url = f"{BASE_URL}/?ca={CATEGORY_ID}" + (f"&page={p}" if p else "")
        soup = BeautifulSoup(fetch_html(url), "html.parser")
        time.sleep(CRAWL_DELAY_SECONDS)
        for d in soup.select("div.item2"):
            a = d.select_one("div.name a")
            if not a:
                continue
            m = re.match(r"/ca\d+/(\d+)/", a["href"])
            if not m or int(m.group(1)) in seen:
                continue
            seen.add(int(m.group(1)))
            items.append((int(m.group(1)), a.get_text(strip=True).replace("　", " ").strip(), a["href"]))
    return items


def build_record(pid: int, name: str, path: str) -> dict | None:
    url = f"{BASE_URL}{path}"
    soup = BeautifulSoup(fetch_html(url), "html.parser")
    variation = soup.find("select", attrs={"name": "variation"})
    var_texts = [o.get_text(strip=True) for o in variation.find_all("option")] if variation else []
    var_texts = [t for t in var_texts if "バリエーションを選択" not in t]
    sold_out = bool(var_texts) and all(SOLD_OUT_PATTERN.search(t) for t in var_texts)

    order = soup.find("select", attrs={"name": "order_su"})
    weight = 100
    if order:
        wm = re.match(r"(\d+)\s*g", order.find("option").get_text(strip=True))
        if wm:
            weight = int(wm.group(1))

    for sc in soup(["script", "style"]):
        sc.decompose()
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))
    price = None
    pm = PRICE_PATTERN.search(text)
    if pm:
        price = int(pm.group(1).replace(",", ""))

    # 本文: パンくず(「＞ 商品名」)の次の見出しの後〜「価格：」の前。【当店焙煎での味の目安】以降(星評価)は除外
    desc = None
    k = text.find("＞ ", text.find("焙煎豆\n"))
    j = text.find("価格：")
    if k >= 0 and j > k:
        body = text[k:j].split("\n", 2)
        body = body[2] if len(body) > 2 else ""
        body = body.split("【当店焙煎での味の目安】")[0]
        desc = re.sub(r"\s+", " ", body).strip()[:400] or None

    roast = ROAST_OVERRIDE.get(pid)
    if roast is None:
        rm = ROAST_PATTERN.search(text)
        if rm:
            raw = rm.group(1).strip()
            roast = ROAST_MAP.get(raw)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if pid in BLEND_IDS:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["processing_method"] = None
        parsed["grade"] = None
    else:
        origin = ORIGIN.get(pid)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "description" if origin else None

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
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, name, path in collect_items():
        time.sleep(CRAWL_DELAY_SECONDS)
        try:
            rec = build_record(pid, name, path)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {path} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_oshimacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_oshimacoffee.json に出力しました")


if __name__ == "__main__":
    main()
