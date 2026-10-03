# -*- coding: utf-8 -*-
"""
scrape_kashiwayacoffee.py

かしわや珈琲(kashiwaya.shop-pro.jp、東京都八王子市千人町3-3-3、販売業者:かしわや珈琲 長澤智之、
店舗は八王子の1店舗)のオンラインショップの商品情報を取得する。カラーミーショップ
(charset=euc-jp、`resp.encoding = "euc-jp"`を明示)。

※群馬県の「柏屋カフェ NAKAYOSHI COFFEE」(scrape_kashiwaya.py、kashiwaya.com)とは別の店舗。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「ハウスブレンド」(cbid=2565583)と「シングルオリジン」
(cbid=2575306)の全商品(ハウスブレンド#0〜#3の4種とシングルオリジン・デカフェ9種の計13件、
全て200g1サイズ)。商品画像の更新日時は2026-08(最新)まで確認でき、現行の品揃えと判断した。
焙煎度は商品名の括弧内「(シティロースト/中煎り)」等から取得する(ブレンドも焙煎度違いの
#0〜#3)。「【カフェインレス】メキシコ サン・フェルナンド組合」はシティロースト(中煎り)と
フレンチロースト(深煎り)の2商品。

【価格・重量】
商品名の末尾「200g」と一覧の税込価格(例: 「1,836円(税136円)」の1,836円)を採用する
(軽減税率8%込み)。在庫は一覧の「SOLD OUT」表示で判定する(2026-10時点は全件在庫あり)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "かしわや珈琲",
    "url": "https://kashiwaya.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "東京都八王子市千人町3-3-3",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://kashiwaya.shop-pro.jp"
CATEGORY_IDS = [("ハウスブレンド", "2565583"), ("シングルオリジン", "2575306")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップバッグ")
MAX_PAGES = 5


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for label, cbid in CATEGORY_IDS:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0" + ("" if page == 1 else f"&page={page}")
            soup = BeautifulSoup(fetch(url), "html.parser")
            new = 0
            for li in soup.select("li.product-list__unit"):
                a = li.select_one("a.product-list__name")
                if not a:
                    continue
                m = re.search(r"pid=(\d+)", a["href"])
                if not m or m.group(1) in items:
                    continue
                new += 1
                price_el = li.select_one(".product-list__price")
                pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
                text = li.get_text(" ", strip=True)
                items[m.group(1)] = {
                    "pid": m.group(1),
                    "name": re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip(),
                    "price": int(pm.group(1).replace(",", "")) if pm else None,
                    "sold_out": any(k in text for k in ("SOLD OUT", "売り切れ", "在庫切れ")),
                    "group": label,
                }
            if new == 0:
                break
    return list(items.values())


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    desc: list[str] = []
    farm: list[str] = []
    if "おすすめ商品" in lines:
        end = lines.index("おすすめ商品")
        # 説明文は、カート操作ブロックの最後の「特定商取引法に基づく表記」リンクの直後から
        marks = [i for i in range(end) if lines[i] == "特定商取引法に基づく表記"]
        start = (marks[-1] + 1) if marks else end
        sect = lines[start:end]
        in_farm = False
        for ln in sect:
            if ln.startswith("<生豆について>"):
                in_farm = True
                continue
            if ln.startswith(("<賞味期限", "＊", "*", "【デカフェ処理】")):
                in_farm = False
                if ln.startswith("【デカフェ処理】"):
                    in_farm = True
                continue
            (farm if in_farm else desc).append(ln)
    return {"desc": " ".join(desc), "farm": " / ".join(farm)}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", name)
    wm = re.search(r"(\d+)\s*g\s*$", norm, re.I)
    weight_g = int(wm.group(1)) if wm else None
    display = re.sub(r"[\s/]*\d+\s*g\s*$", "", norm, flags=re.I).strip()
    display = re.sub(r"\s+", " ", display)
    parsed = parse_product(display)
    roast_hint = None
    rm = re.search(r"\(([^()]*(?:ロースト)[^()]*)\)", display)
    if rm:
        roast_hint = rm.group(1).strip()
    if "ブレンド" in display:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, display)
        if not parsed["origin_country"]:
            c = detect_country_name(display)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "country_name"
    out = item["sold_out"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": detail["desc"][:300] or None,
        "farm_note": re.sub(r"\s*/?\s*賞味期限.*$", "", detail["farm"])[:300] or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            detail = parse_detail(fetch(f"{BASE_URL}/?pid={item['pid']}"))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            detail = {"desc": "", "farm": ""}
        rec = build_record(item, detail)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kashiwayacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kashiwayacoffee.json に出力しました")


if __name__ == "__main__":
    main()
