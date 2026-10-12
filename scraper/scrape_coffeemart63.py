# -*- coding: utf-8 -*-
"""
scrape_coffeemart63.py

コーヒーマート63(coffee-mart.jp、石川県金沢市玉鉾2-27、遠赤外線自家焙煎・注文焙煎)の
コーヒー豆商品情報を取得する。WordPress(独自テーマ)+外部カート(easy-myshop)。

【robots.txt】/wp/wp-admin/ のみ Disallow(2026-10-12確認)。

【一覧と在庫の判定】
https://coffee-mart.jp/store/ に過去分を含む約190商品が一括で並ぶ(ページ送りなし)。
各商品カードの div.item_status 内のバッジで状態を示す:
  span.soldout「完売」 = 販売終了/在庫なし(約95件。過去商品が残っている)
  span.again「再販売」/new「NEW」/recommend「おすすめ」/popular「人気」/classic「定番」
  バッジなし = 販売中
詳細ページはカートボタンが完売品にも残るため、バッジが唯一の判定材料。
「完売」の商品は「現行販売中の豆だけを収録」の方針で除外する。
末尾の「人気の商品」ランキング(5件、div.beans の外の簡易リスト)は重複なので無視する。

【商品情報】
詳細ページの table(国/エリア・農園/生産者/標高/品種/生産処理/焙煎度)と本文p、
価格「○○円(税込)/ 100g」から取得する。重量は100g単位(通常)。
除外: 単位が「100g」でないもの(ドリップパック・アイスコーヒー・水出し・セット等 = 「1個」「1セット」)、
インフューズド(果実・ハーブ・香料を加える製法)。
"""

import json
import re
import sys
import time
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "コーヒーマート63",
    "url": "https://coffee-mart.jp/store/",
    "platform": "WordPress(独自テーマ)+easy-myshop",
    "address": "石川県金沢市玉鉾2-27",
    "prefecture": "石川県",
    "robots_txt_status": "許可(2026-10-12確認。/wp/wp-admin/のみDisallow)",
}

LIST_URL = "https://coffee-mart.jp/store/"
CRAWL_DELAY_SECONDS = 0.7
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

NON_BEAN_KEYWORDS = ["ドリップパック", "ドリップバッグ", "セット", "詰め合わせ", "ギフト", "水出し", "ディップ", "アイスコーヒー 無糖"]
INFUSED_KEYWORDS = ["インフューズド", "インフューズ", "WineYeast"]
# 樽(ウイスキー・ラム・ブランデー・ワイン・カシャーサ)で生豆を寝かせ、樽の香りを移す「バレルコーヒー」。
# 店自身が「インフューズドコーヒーの代表」と説明しているため、方針に従い除外する。
BARREL_KEYWORDS = ["バレル", "樽"]

CELL_COUNTRY_FIX = {"マラウィ": "マラウイ", "ガテマラ": "グアテマラ", "タイ": "タイ", "中国": "中国"}
NAME_COUNTRY_FALLBACK = {"タイの怠け者コーヒー": "タイ"}  # 国欄の無いページ(本文でタイ北部のカレン族農家と明記)

PRICE_PATTERN = re.compile(r"([\d,]+)\s*円\(税込\)\s*/\s*(\d+)\s*g")
BLEND_NAMES = ["ブレンド"]


def fetch(url):
    r = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    return BeautifulSoup(r.text, "html.parser")


def list_items():
    soup = fetch(LIST_URL)
    out = []
    for li in soup.select("div.beans ul.list > li"):
        a = li.find("a", href=True)
        h3 = li.find("h3")
        if not a or not h3:
            continue  # 「人気の商品」ランキングの簡易リストは h3 が無い
        status = li.select_one("div.item_status span")
        out.append({
            "url": a["href"],
            "list_name": " ".join(h3.get_text(" ", strip=True).split()),
            "badge": status.get_text(strip=True) if status else None,
            "badge_class": (status.get("class") or [None])[0] if status else None,
        })
    return out


def parse_detail(url):
    r = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    raw_html = r.text
    soup = BeautifulSoup(raw_html, "html.parser")
    h1 = soup.select_one("main#shop h1")
    for sp in h1.select("span"):
        sp.decompose()
    name = " ".join(h1.get_text(" ", strip=True).split())
    price_text = soup.select_one("main#shop p.price").get_text(" ", strip=True)
    m = PRICE_PATTERN.search(price_text)
    price = int(m.group(1).replace(",", "")) if m else None
    weight = int(m.group(2)) if m else None
    unit_text = price_text

    table = {}
    # 本サイトの table は <th>項目<th><td>値<td> と閉じタグが崩れているため、正規表現で読む
    tm = re.search(r"<table>(.*?)</table>", raw_html, re.S)
    if tm:
        raw = tm.group(1)
        for k, v in re.findall(r"<th>(.*?)<th>\s*<td>(.*?)<td>", raw, re.S):
            k = BeautifulSoup(k, "html.parser").get_text(strip=True)
            v = " ".join(BeautifulSoup(v, "html.parser").get_text(" ", strip=True).split())
            table[k] = v
    text_div = soup.select_one("div.bean article div.text")
    paras = [p.get_text("\n", strip=True) for p in text_div.find_all("p")] if text_div else []
    return {"name": name, "price": price, "weight": weight, "unit_text": unit_text, "table": table, "desc": "\n".join(paras)}


def build_record(item, d):
    name = d["name"]
    parsed = parse_product(name)
    country_cell = d["table"].get("国")
    if "レンド" in name and parsed["category"] != "ブレンド":
        parsed["category"] = "ブレンド"  # 例: 「ラブ♡レンド」
    is_blend = parsed["category"] == "ブレンド"
    if is_blend:
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        # 国欄(table)が最も確実。商品名の国名検出は「ケニア式ウォッシュ」のタイ産などで誤るため上書きする
        c = None
        if country_cell:
            c = CELL_COUNTRY_FIX.get(country_cell) or detect_country_name(country_cell) or country_cell
        elif name in NAME_COUNTRY_FALLBACK:
            c = NAME_COUNTRY_FALLBACK[name]
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
    roast_text = d["table"].get("焙煎度")
    farm_bits = [d["table"].get(k) for k in ("エリア・農園",)]
    farm_note = "、".join(b for b in farm_bits if b) or None
    if d["table"].get("標高"):
        farm_note = (farm_note + "、" if farm_note else "") + "標高" + d["table"]["標高"]
    if d["table"].get("品種"):
        farm_note = (farm_note + "、" if farm_note else "") + "品種:" + d["table"]["品種"]
    process = d["table"].get("生産処理")
    pm = parsed["processing_method"]
    if not pm and process:
        from coffee_parser import detect_processing_method
        pm = detect_processing_method(process)
    if pm and "デカフェ" in pm and not any(k in name + (process or "") for k in ("デカフェ", "カフェインレス", "カフェイン")):
        pm = None  # 「マウンテンウォーター製法」は産地ブランドの呼称で、デカフェ工程ではない
    stock_status = detect_stock_status(name, False)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": pm,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_text,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": d["desc"] or None,
        "blend_components": [],
        "price": d["price"],
        "weight_g": d["weight"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products():
    items = list_items()
    records, excluded = [], []
    for it in items:
        if it["badge_class"] == "soldout":
            excluded.append({"name": it["list_name"], "reason": "完売(販売終了扱い)"})
            continue
        name = it["list_name"]
        if any(k in name for k in NON_BEAN_KEYWORDS):
            excluded.append({"name": name, "reason": "非コーヒー豆(ドリップパック/セット/水出し等)"})
            continue
        try:
            d = parse_detail(it["url"])
        except Exception as e:  # noqa
            print("[warn]", it["url"], e)
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if d["weight"] != 100 or "100g" not in d["unit_text"]:
            excluded.append({"name": d["name"], "reason": "単位が100gではない: " + d["unit_text"]})
            continue
        if any(k in d["name"] or k in d["desc"] for k in INFUSED_KEYWORDS):
            excluded.append({"name": d["name"], "reason": "インフューズド"})
            continue
        if any(k in d["name"] for k in BARREL_KEYWORDS) or any(k in d["table"].get("生産処理", "") for k in BARREL_KEYWORDS + ["樽詰め"]):
            excluded.append({"name": d["name"], "reason": "バレルコーヒー(樽の香り付け=インフューズド扱い)"})
            continue
        records.append(build_record(it, d))
    return records, excluded


if __name__ == "__main__":
    records, excluded = scrape_all_products()
    out = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeemart63.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("[done]", len(records), "件を data_coffeemart63.json に出力 / 除外", len(excluded))
    for e in excluded:
        if e["reason"] != "完売(販売終了扱い)":
            print("  除外:", e["name"], "-", e["reason"])
