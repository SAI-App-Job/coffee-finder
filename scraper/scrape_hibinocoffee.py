# -*- coding: utf-8 -*-
"""
scrape_hibinocoffee.py

日々ノ珈琲(hibinocoffee.jp、福岡県福岡市中央区平尾2-17-6 山荘第2アパート1F、
直火式焙煎機による自家焙煎の豆販売専門店)の公式オンラインショップの商品情報を取得する。
MakeShop(新形式 /view/item/)。

【対象商品について】
実データ確認済み(2026-10時点): 全商品一覧(/view/category/all_items、2ページ・計65件)は
1銘柄につき 100g / 150g / 200g / 500g が別商品として登録されている。
同一銘柄は最小重量(100g)の商品を代表として採用する。
 - ブレンド: 日々是ブレンド・好日ブレンド・ほろにがブレンド・秋ブレンド「金律」「紅零」
   (秋ブレンドは2026-09-01〜11-30の季節限定)
 - ストレート: ブラジル・ダテラ、ガテマラ・サンタカタリーナ(中煎り)、極深煎りガテマラ・
   サンタカタリーナ(売り切れ。100g・150gのみ)、エチオピア2種、ルワンダ、タンザニア、
   ケニア、コロンビア、インドネシア・マンデリン
 - カフェインレス・エチオピア(スイスウォーター式。中深煎り)
除外: ドリップパック、水出しアイスパック、ジプロック・缶・ドリップパックのギフトセット。

【焙煎度】
商品ページの<title>に含まれるカテゴリ(コーヒー豆 浅煎り / 中煎り / 深煎り)を採用する。
カフェインレス・エチオピアは説明文の「中深煎りに焙煎」、極深煎りガテマラは商品名から。

【在庫】
詳細ページの span.detail-sold-out(SOLD OUT表示)があれば完売。

【robots.txt】
/robots.txt は404(MakeShopの標準404ページ)で、クロール制限の記述は無い。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "日々ノ珈琲",
    "url": "https://hibinocoffee.jp/",
    "platform": "MakeShop",
    "address": "福岡県福岡市中央区平尾2-17-6 山荘第2アパート1F",
    "prefecture": "福岡県",
    "robots_txt_status": "制限記述なし(2026-10-20確認。/robots.txtは404)",
    "source_note": "公式オンラインショップ(https://hibinocoffee.jp/)の全商品一覧と各商品ページ、店舗概要を2026-10-20に確認。同一銘柄は100g/150g/200g/500gが別商品のため最小の100gを代表とした。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://hibinocoffee.jp"
LIST_URLS = [f"{BASE_URL}/view/category/all_items", f"{BASE_URL}/view/category/all_items?page=2"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2

NON_BEAN_KEYWORDS = ("ドリップパック", "水出し", "ギフト")
NAME_PATTERN = re.compile(r"^(?P<base>.+?)(?P<w>\d+)g$")
ROAST_FROM_TITLE = re.compile(r"コーヒー豆\s*(浅煎り|中煎り|深煎り)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for url in LIST_URLS:
        soup = BeautifulSoup(fetch(url), "html.parser")
        for a in soup.select('a[href*="/view/item/"]'):
            m = re.search(r"/view/item/(\d+)", a["href"])
            if not m:
                continue
            li = a.find_parent("li") or a.parent
            text = re.sub(r"\s+", " ", li.get_text(" ", strip=True))
            tm = re.search(r"(?:SOLD OUT\s*)?(\S.*?)\s*[￥¥]\s*([\d,]+)", text)
            if not tm:
                continue
            name = tm.group(1).replace("SOLD OUT", "").strip()
            items.setdefault(m.group(1), {"id": m.group(1), "name": name, "price": int(tm.group(2).replace(",", ""))})
        time.sleep(REQUEST_INTERVAL)
    return list(items.values())


def pick_representatives(items: list[dict]) -> list[dict]:
    """同一銘柄(重量表記を除いた名称)ごとに最小重量の商品を選ぶ。"""
    best: dict[str, tuple[int, dict]] = {}
    for it in items:
        if any(kw in it["name"] for kw in NON_BEAN_KEYWORDS):
            continue
        m = NAME_PATTERN.match(it["name"])
        if not m:
            continue
        w = int(m.group("w"))
        base = m.group("base").strip()
        it = dict(it, base=base, weight_g=w)
        if base not in best or w < best[base][0]:
            best[base] = (w, it)
    return [v[1] for v in best.values()]


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    rm = ROAST_FROM_TITLE.search(title)
    sold_out = soup.select_one("span.detail-sold-out") is not None
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    desc_lines: list[str] = []
    if "ポイント獲得！" in lines:
        for ln in lines[lines.index("ポイント獲得！") + 1:]:
            if ln in ("数量", "豆・挽") or "についてつぶやく" in ln:
                break
            if ln.startswith("販売開始：") or ln.startswith("販売終了："):
                continue
            desc_lines.append(ln)
    return {"roast": rm.group(1) if rm else None, "sold_out": sold_out, "desc": " ".join(desc_lines)}


def build_record(item: dict, detail: dict) -> dict:
    name = item["base"]
    parsed = parse_product(name)
    roast = detail["roast"]
    if "極深煎り" in name:
        roast = "極深煎り"
    elif "カフェインレス" in name and "中深煎り" in detail["desc"]:
        roast = "中深煎り"
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    elif "カフェインレス" in name:
        parsed["category"] = "デカフェ"
        parsed = apply_category_hint_fallback(parsed, name)
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
    sold_out = detail["sold_out"]
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
        "flavor_notes": detail["desc"][:300] if detail["desc"] else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/view/item/{item['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in pick_representatives(list_items()):
        try:
            detail = parse_detail(fetch(f"{BASE_URL}/view/item/{item['id']}"))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            continue
        records.append(build_record(item, detail))
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hibinocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hibinocoffee.json に出力しました")


if __name__ == "__main__":
    main()
