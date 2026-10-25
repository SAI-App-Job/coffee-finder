# -*- coding: utf-8 -*-
"""
scrape_bankokunakano.py

萬国コーヒー(萬国コーヒー株式会社・直営カフェ SmB CAFE、東京都中野区本町3-31-2、
bankoku-coffee.ocnk.net)の自家焙煎コーヒー豆の商品情報を取得する。おちゃのこネット(Ocnk、新テーマ)。
※岡山県津山市の「ばんこく珈琲 津山」(scrape_bankokucoffee.py)とは別の店。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「期間限定コーヒー」(27)「ストレート【中煎り】」(18)
「ストレート【深煎り】」(19)「ブレンドコーヒー」(4)「バリエーションコーヒー」(5)「カフェインレス」(8)
の商品。除外: フレーバーコーヒー(香料付き。インフューズド系)、ドリップバッグ、水出しバッグ、
ギフト、紅茶、グッズ、期間限定の「粉」版(豆版を採用)。
【価格・重量】一覧は「630円～2,520円(税込)」のようにオプション(100g〜500g)の価格幅で表示され、
オプション別の価格はJS経由のため静的HTMLに出ない。そのため最小重量(100g)=一覧の下限価格を
採用する(100gが最も安いサイズ。中野坂上ブレンド等の200g単独商品は200gの価格)。
【焙煎度】カテゴリ(中煎り/深煎り)または商品説明の【焙煎度合】から取得。
【robots.txt】GPTBot等の特定UAのみDisallow(User-agent: * は制限なし)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "萬国コーヒー",
    "url": "https://bankoku-coffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "東京都中野区本町3-31-2",
    "prefecture": "東京都",
    "robots_txt_status": "許可(特定のAIクローラ名のみDisallow、User-agent: * は制限なし)",
    "source_note": "特商法表示 https://bankoku-coffee.ocnk.net/info (2026-10-20確認)に「萬国コーヒー株式会社 東京都中野区本町３－３１－２」。"
                   "公式 https://www.bankoku-coffee.co.jp/company.php に「〒164-0012 東京都中野区本町3-31-2」「自社で焙煎した新鮮なコーヒー豆」、"
                   "珈琲人名鑑 https://www.ejcra.org/interview/bankokucoffee/ に半熱風式フジの焙煎機・2011年に本社を改装して直営カフェSmB CAFEを開店・店頭で30種類以上の豆を販売。"
                   "1959年創業。ショップのお知らせは2026-10-22付(PHPセキュリティ更新)で現役。価格はオプション幅の下限(100g)を採用。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://bankoku-coffee.ocnk.net"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
SLEEP = 2.0
CATEGORIES = [("27", "limited"), ("18", "straight_mid"), ("19", "straight_dark"), ("4", "blend"), ("5", "variation"), ("8", "decaf")]
ROAST_MAP = [("フレンチ", "深煎り"), ("イタリアン", "深煎り"), ("フルシティ", "深煎り"), ("シティ", "中深煎り"), ("ハイ", "中煎り"),
             ("ミディアム", "中煎り"), ("ライト", "浅煎り"), ("シナモン", "浅煎り")]


def get(url):
    time.sleep(SLEEP)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def list_cells(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for li in soup.select("li.list_item_cell"):
        a = li.select_one("a[href*='/product/']")
        m = re.search(r"/product/(\d+)", a["href"]) if a else None
        if not m:
            continue
        name = re.sub(r"\s+", " ", li.select_one(".goods_name").get_text(" ", strip=True)).strip()
        price_el = li.select_one(".selling_price")
        nums = [int(x.replace(",", "")) for x in re.findall(r"([\d,]+)\s*円", price_el.get_text(" ", strip=True))] if price_el else []
        stock = li.select_one(".stock")
        sold = "soldout" in li["class"] or (stock is not None and "在庫なし" in stock.get_text())
        out.append({"pid": m.group(1), "name": name, "price": min(nums) if nums else None, "sold": sold})
    return out


def roast_from_text(text):
    m = re.search(r"【焙煎度合】\s*([^\n【]+)", text)
    if not m:
        return None, None
    raw = m.group(1).strip()
    first = re.split(r"[〜~・、/]", unicodedata.normalize("NFKC", raw))[0]
    for word, level in ROAST_MAP:
        if first.startswith(word):
            return level, raw
    return None, raw


def processing_from_text(text):
    m = re.search(r"(?:精製方法|精製処理|精選方法)\s*([^\s]+)", text)
    return detect_processing_method(m.group(1)) if m else None


def scrape_all_products() -> list[dict]:
    items = {}
    for cid, group in CATEGORIES:
        for c in list_cells(get(f"{BASE_URL}/product-list/{cid}")):
            c["group"] = group
            items.setdefault(c["pid"], c)

    records = []
    for it in items.values():
        name = it["name"]
        if re.search(r"(・|\s)粉$", name) or it["price"] is None:
            continue
        html_text = get(f"{BASE_URL}/product/{it['pid']}")
        soup = BeautifulSoup(html_text, "html.parser")
        for t in soup(["script", "style"]):
            t.decompose()
        text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n", strip=True))
        k = text.find("商品詳細")
        detail = text[k + 4:] if k >= 0 else text
        end = detail.find("当店は１９５９年創業")
        detail = detail[:end] if end > 0 else detail

        # 重量: 名前の「200g」等(単独商品)。範囲表記(100g〜500g)は最小の100g
        nm = unicodedata.normalize("NFKC", name)
        wm = re.search(r"(\d+)\s*g", nm)
        weight = int(wm.group(1)) if wm else 100
        clean = re.sub(r"\s*\d+\s*g.*$", "", nm).strip()
        clean = re.sub(r"[・\s]*豆$", "", clean).strip()
        clean = re.sub(r"\s+", " ", clean)

        m = re.search(r"【生産地】\s*([^\n【]+)", detail)
        origin_raw = m.group(1).strip() if m else ""
        origin_parts = [p for p in re.split(r"[・、,/／\s]+", origin_raw) if p]
        countries = []
        for p in origin_parts:
            c = detect_country_name(p)
            if c and c not in countries:
                countries.append(c)
        is_blend = it["group"] == "blend" or "ブレンド" in clean or len(countries) >= 2
        desc_main = detail.split("【商品名】")[0].strip()
        desc = re.sub(r"\s+", " ", desc_main)[:400] or None

        roast_level, roast_raw = roast_from_text(detail)
        if not roast_level:
            mr = re.search(r"焙煎度合\s*([^\s]+)", detail)
            if mr:
                roast_raw = roast_raw or mr.group(1)
                for word, level in ROAST_MAP:
                    if unicodedata.normalize("NFKC", mr.group(1)).startswith(word):
                        roast_level = level
                        break
        if not roast_level:
            mr = re.search(r"(中深煎り|中煎り|深煎り|浅煎り)", detail)
            if mr:
                roast_level = mr.group(1)
        if it["group"] == "straight_mid" and not roast_level:
            roast_level = "中煎り"
        if it["group"] == "straight_dark" and not roast_level:
            roast_level = "深煎り"

        parsed = parse_product(clean)
        components = []
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
            components = [{"origin_country": c} for c in countries]
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = (countries[0] if countries else None) or detect_country_name(clean)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description" if countries else "raw_name"
            parsed = apply_category_hint_fallback(parsed, clean)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": clean,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": None if is_blend else (parsed["processing_method"] or processing_from_text(detail)),
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_selectable": False,
            "roast_hint": roast_raw,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": components,
            "price": it["price"],
            "weight_g": weight,
            "stock_status": "完売" if it["sold"] else "販売中",
            "out_of_stock": bool(it["sold"]),
            "product_url": f"{BASE_URL}/product/{it['pid']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_bankokunakano.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bankokunakano.json に出力しました")


if __name__ == "__main__":
    main()
