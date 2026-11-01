# -*- coding: utf-8 -*-
"""
scrape_kship.py

COFFEE ROASTER K-ship(香川県木田郡三木町池戸2903-1、2012年開業の自家焙煎珈琲店。店内飲食あり、
GIESEN社の焙煎機を店内に設置)のオンラインショップの商品情報を取得する。FC2ショッピングカート。

【対象商品について】
実データ確認済み(2026-11-02時点): 全41点のうち、珈琲豆のカテゴリ
  - 限定豆(ケニア クイーン)・ブレンド(K-shipブレンド、深煎りブレンド)・
    ストレート(グァテマラ ジャスミン、インドネシア マンデリン、エチオピア イルガチェフェ)
  - ネット限定豆(エクアドル グレートマウンテン。注文後焙煎・500g単位のみ)
の7銘柄を対象とする。100g単位で注文でき、価格は100gあたり(エクアドルのみ500gあたり)。
挽き方は豆のまま/粉(各種)で価格同一。豆のままを前提に価格・重量を採用する。
除外: マスターズ・セレクト(3か月・6か月の定期配送)、ドリップバッグセット、水出しパック、
ギフトBOX、スコーンセット、器具、雑貨(鈴の村)、豆缶。

【ページ構造について】
一覧は「/?ca=all」にpar_page=100をPOSTして全件を1ページに表示させる(既定は6件/ページ)。
商品は`li.item`(dt.name a=商品名・リンク、dd.price=価格)。詳細ページに【原産国】【産地】【品種】
【焙煎度】【その他】(精製)【ブレンド】【K-shipマスターより】の構造化行がある。
在庫はoptionのdata-stock="0"/data-submit="0"で判定(現状は全件販売中)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    detect_processing_method, normalize_processing_method,
)

SHOP_INFO = {
    "name": "COFFEE ROASTER K-ship",
    "url": "https://kship.cart.fc2.com/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "香川県木田郡三木町池戸2903-1",
    "prefecture": "香川県",
    "robots_txt_status": "許可(User-agent: * で /cancel/ /setup/ /tools/ のみ Disallow。識別可能なUser-Agentを使用)",
    "source_note": "FC2カート商品一覧(/?ca=all、全41点)と各商品ページ、特商法(https://kship.cart.fc2.com/laws)、店舗の紹介(https://kship.cart.fc2.com/userpage?id=56226)、公式サイト(https://www.k-ship.jp/、お知らせ2026-10-29付)を2026-11-02に確認。2012年7月開業の実店舗(11席・GIESEN社焙煎機設置)で自家焙煎。",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://kship.cart.fc2.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 1.6

# 珈琲豆のカテゴリ(ca番号): 14=限定豆, 15=ブレンド, 16=ストレート, 22=ネット限定豆
BEAN_CATEGORIES = {"14", "15", "16", "22"}
BLEND_CATEGORIES = {"15"}


def fetch(session: requests.Session, method: str, url: str, **kw) -> str:
    time.sleep(REQUEST_INTERVAL)
    resp = session.request(method, url, timeout=30, **kw)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items(session: requests.Session) -> list[dict]:
    html_text = fetch(session, "POST", f"{BASE_URL}/?ca=all", data={"par_page": "100", "Submit_par": "設定"})
    soup = BeautifulSoup(html_text, "html.parser")
    items, seen = [], set()
    for li in soup.select("li.item"):
        a = li.select_one("dt.name a")
        if not a:
            continue
        m = re.search(r"/ca(\d+)/(\d+)/", a["href"])
        if not m or m.group(2) in seen or m.group(1) not in BEAN_CATEGORIES:
            continue
        seen.add(m.group(2))
        pr = li.select_one("dd.price")
        pm = re.search(r"([\d,]+)\s*円", pr.get_text()) if pr else None
        items.append({
            "id": m.group(2),
            "ca": m.group(1),
            "name": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", a.get_text(" ", strip=True))),
            "price": int(pm.group(1).replace(",", "")) if pm else None,
        })
    return items


def parse_fields(lines: list[str]) -> dict:
    """【見出し】の次行以降(次の【まで)を値として集める。"""
    fields: dict[str, str] = {}
    key = None
    buf: list[str] = []
    for line in lines:
        m = re.fullmatch(r"【\s*([^】]+?)\s*】", line)
        if m:
            if key is not None:
                fields.setdefault(key, " ".join(buf).strip())
            key, buf = re.sub(r"[\s　]+", "", m.group(1)), []
        elif key is not None:
            if line.startswith(("価格", "種類")):
                break
            buf.append(line)
    if key is not None:
        fields.setdefault(key, " ".join(buf).strip())
    return fields


def build_record(session: requests.Session, item: dict) -> dict | None:
    url = f"{BASE_URL}/ca{item['ca']}/{item['id']}/p-r-s/"
    soup = BeautifulSoup(fetch(session, "GET", url), "html.parser")
    options = [o for o in soup.select("select[name=variation] option") if o.get("value") != "not_selected"]
    sold_out = bool(options) and all(o.get("data-stock") == "0" or o.get("data-submit") == "0" for o in options)
    for sc in soup(["script", "style"]):
        sc.decompose()
    text = (soup.select_one("div#contents") or soup.body).get_text("\n", strip=True)
    lines = [unicodedata.normalize("NFKC", l.strip()) for l in text.split("\n") if l.strip()]
    fields = parse_fields(lines)

    # 重量: 「注文数」の選択肢「1×100g」から最小単位を採る
    wm = re.search(r"1×(\d+)g", text)
    weight = int(wm.group(1)) if wm else None
    price = item["price"]

    name = re.sub(r"\(\d+g単位\)$", "", item["name"]).strip()
    is_blend = item["ca"] in BLEND_CATEGORIES
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        c = detect_country_name(fields.get("原産国") or "")
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
        elif not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    processing = None
    if not is_blend:
        other = fields.get("その他") or ""
        processing = normalize_processing_method(other) if other else None
        processing = processing or parsed["processing_method"] or detect_processing_method(name)

    roast = (fields.get("焙煎度") or "").strip() or None
    desc_parts = []
    if fields.get("K-shipマスターより"):
        desc_parts.append(fields["K-shipマスターより"])
    if is_blend and fields.get("ブレンド"):
        desc_parts.append("ブレンド: " + fields["ブレンド"])
    if fields.get("産地"):
        desc_parts.append("産地: " + fields["産地"])
    desc = re.sub(r"\s+", " ", " ".join(desc_parts)).strip()[:400] or None
    farm_bits = [f"{k}: {fields[k]}" for k in ("品種", "標高", "グレード") if fields.get(k)]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": "、".join(farm_bits) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    records = []
    for item in list_items(session):
        try:
            rec = build_record(session, item)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {item['name']} ({e})")
            continue
        if rec is not None and rec["price"] is not None:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kship.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kship.json に出力しました")


if __name__ == "__main__":
    main()
