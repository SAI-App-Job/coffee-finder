# -*- coding: utf-8 -*-
"""
scrape_lowkeytone.py

ローキートーン珈琲店(lowkeytone.com / オンラインショップ lowkeytonecoffee.com、東京都世田谷区砧6-37-6-BC、
小田急線祖師ヶ谷大蔵駅近く、「コーヒー豆は全て当店の焙煎機でローストした自家焙煎」)の
商品情報を取得する。カラーミーショップ(charset=euc-jp、`resp.encoding = "euc-jp"`を明示)。

【住所について】
オンラインショップの特定商取引法に基づく表記の住所「東京都世田谷区砧6-37-6-BC」を採用
(2026-10確認)。lowkeytone.com側の「世田谷・砧にあるコーヒー豆焙煎所」とも一致。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆 ２５０ｇ」(cbid=1604916、全28商品・3ページ。
レギュラーブレンド・季節限定ブレンド・シングルオリジン・カフェインレス)を対象とする。
同一銘柄の「コーヒー豆 ５００ｇ」カテゴリ(cbid=2496475)は大きいサイズなので使わない
(代表サイズは最小サイズ=250g)。「コーヒーの日」記念ブレンドの2種のみ200g。
コーヒー豆セット・クリックポスト便セット・ドリップパック・水出しパック・器具は別カテゴリのため
対象外。シングルオリジンの「ホンジュラスCOE」(2023年入賞ロット)等は数量限定品として
掲載が続いているため含める。

【焙煎度・価格】
注文時に焙煎度合(中浅煎り(マイルド)/中深煎り(ほろにが))等を選べる商品が多く、その場合は
roast_hintに選択肢を保持する。価格は一覧の税込価格(商品によっては「実店舗同様、250gパック割引
20%OFF価格」が適用された価格)。在庫は一覧の「SOLD OUT」表示で判定する(2026-10時点は全件在庫あり)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ローキートーン珈琲店",
    "url": "https://lowkeytonecoffee.com/",
    "platform": "カラーミーショップ",
    "address": "東京都世田谷区砧6-37-6-BC",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://lowkeytonecoffee.com"
CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=1604916&csid=0"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ドリップパック", "パック入", "水出し", "きんちゃく")
MAX_PAGES = 6


def fetch(url: str) -> str | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}&page={page}"
        html_text = fetch(url)
        if html_text is None:
            break
        soup = BeautifulSoup(html_text, "html.parser")
        new = 0
        for li in soup.select("li.c-item-list__item"):
            a = li.select_one(".c-item-list__ttl a")
            price_el = li.select_one(".c-item-list__price")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a["href"])
            if not m or m.group(1) in items:
                continue
            new += 1
            price_text = price_el.get_text(" ", strip=True) if price_el else ""
            pm = re.search(r"([\d,]+)\s*円", price_text)
            expl = li.select_one(".c-item-list__expl")
            items[m.group(1)] = {
                "pid": m.group(1),
                "name": re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip(),
                "price": int(pm.group(1).replace(",", "")) if pm else None,
                "short": expl.get_text(strip=True) if expl else None,
                "sold_out": "SOLD OUT" in li.get_text() or "在庫なし" in li.get_text(),
            }
        if new == 0:
            break
    return list(items.values())


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    section: list[str] = []
    if "DETAIL" in lines:
        start = lines.index("DETAIL") + 1
        end = next(
            (i for i in range(start, len(lines))
             if lines[i] in ("REVIEW", "WRITE REVIEW") or lines[i].startswith("RECOMMENDED")),
            len(lines),
        )
        # 関連商品の一覧(「…円(税込)」)が本文に混ざる場合があるので、価格行以降は切り捨てる
        cut = next((i for i in range(start, end) if "円(税込)" in lines[i]), end)
        section = lines[start:cut]
    fields: dict[str, str] = {}
    free: list[str] = []
    i = 0
    while i < len(section):
        m = re.match(r"^【(.+?)】\s*(.*)$", section[i])
        if m:
            label, val = m.group(1), m.group(2)
            if not val and i + 1 < len(section) and not section[i + 1].startswith("【"):
                val = section[i + 1]
                i += 1
            fields[label] = val
        elif not section[i].startswith(("★", "＊", "*")):
            free.append(section[i])
        i += 1
    # 焙煎度の選択肢(選択式の場合は「焙煎具合：」の行にもある)
    return {"fields": fields, "free": free}


def build_record(item: dict, detail: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", name)
    wm = re.search(r"(\d+)\s*g\s*$", norm, re.I)
    weight_g = int(wm.group(1)) if wm else None
    display = re.sub(r"\s*\d+\s*g\s*$", "", norm, flags=re.I).strip()
    display = re.sub(r"\s+", " ", display)
    parsed = parse_product(display)
    if "ブレンド" in display or parsed["category"] == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, display)
        if not parsed["origin_country"]:
            c = detect_country_name(" ".join(detail["fields"].values()))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
    fields = detail["fields"]
    flavor_notes = fields.get("カッピングコメント")
    if not flavor_notes:
        base = re.sub(r"[\s　]", "", display)
        extra = [
            ln for ln in detail["free"]
            if base not in re.sub(r"[\s　]", "", unicodedata.normalize("NFKC", ln))
            and not ln.startswith(("煎り具合", "〜", "~", "(", "（", "豆のまま", "●", "挽き", "RECOMMENDED", "<<", "＜＜"))
        ]
        # 焙煎度のみの短い紹介文(item["short"])は roast_hint 側で保持するので、本文だけを使う
        flavor_notes = " ".join(extra[:3])[:300] or None
    farm_bits = [f"{k}:{fields[k]}" for k in ("農園", "農園主", "エリア", "標高", "品種", "精製方法") if fields.get(k)]
    roast_hint = fields.get("焙煎度合") or item["short"]
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
        "flavor_notes": flavor_notes[:300] if flavor_notes else None,
        "farm_note": " / ".join(farm_bits) or None,
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
            html_text = fetch(f"{BASE_URL}/?pid={item['pid']}")
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        detail = parse_detail(html_text) if html_text else {"fields": {}, "free": []}
        rec = build_record(item, detail)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_lowkeytone.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lowkeytone.json に出力しました")


if __name__ == "__main__":
    main()
