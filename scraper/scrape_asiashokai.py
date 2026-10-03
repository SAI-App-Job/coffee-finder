# -*- coding: utf-8 -*-
"""
scrape_asiashokai.py

アジア商会 鎌倉店(kamakura.ocnk.net、神奈川県鎌倉市由比ガ浜2-5-18、株式会社アジア商会、
鎌倉で自家焙煎コーヒー豆の挽き売り・カフェ/喫茶店への卸)の商品情報を取得する。おちゃのこネット(UTF-8)。

【自家焙煎・住所の確認(2026-10)】
トップに「自家焙煎コーヒー豆の販売」「コーヒー豆を焙煎し、鎌倉で挽き売り販売をしています」、
特定商取引法ページの販売主は株式会社アジア商会(神奈川県鎌倉市由比ガ浜2-5-18)。サイト内に
他店舗の記載は無く、単独店舗と判断した。商品画像は2026-02更新分があり現行運営。

【対象商品について】
実データ確認済み(2026-10時点): 「ストレート(単品)」(product-list/6、14件)と
「ブレンド(混合)」(product-list/7、8件)の計22件。紅茶、クリックポスト便(product-list/61、
同一豆の別送料設定)、再発送用は除外。
各商品は1ページに「単位」オプション(100g/200g/300g/400g/500g)と「状態」(豆のまま/挽き)を持つ
バリエーション商品で、一覧の価格は最安=100gの価格。詳細ページのJS(pConf.priceArray)から
最小サイズの価格を読み取り、100g/税込を代表値とする(例: 950円/100g)。
売り切れはカート用の「オプション選択」ボタンが無く「お問い合わせ」のみ(商品画像もSOLD OUT)の
商品で、詳細にも単位オプションが無いため重量は不明(weight_g=None)、価格は一覧の最安表示を使う。
商品名はカテゴリから「ブレンド」を判定する(「イタリアン ロースト」等は商品名に「ブレンド」を含まない)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "アジア商会 鎌倉店",
    "url": "https://kamakura.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "神奈川県鎌倉市由比ガ浜2-5-18",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。User-Agent: *の制限無し。GPTBot等のAIクローラーのみDisallow)",
}

BASE_URL = "https://kamakura.ocnk.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
# (カテゴリID, ブレンドか)
CATEGORIES = [(6, False), (7, True)]

PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
UNIT_OPTION_PATTERN = re.compile(r'<option value="(\d+)">\s*(\d+)\s*g')
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン|ジャーマン)ー?ロースト")
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items, seen = [], set()
    for cat_id, is_blend in CATEGORIES:
        soup = BeautifulSoup(fetch(f"{BASE_URL}/product-list/{cat_id}"), "html.parser")
        for card in soup.select("li.list_item_cell"):
            a = card.select_one("a[href*='/product/']")
            pid_m = re.search(r"/product/(\d+)", a.get("href", "")) if a else None
            if not pid_m or pid_m.group(1) in seen:
                continue
            seen.add(pid_m.group(1))
            name_el = card.select_one(".goods_name")
            price_el = card.select_one(".selling_price")
            price_m = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
            values = [i.get("value") for i in card.select("input")]
            items.append({
                "pid": pid_m.group(1),
                "title": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", name_el.get_text(strip=True))).strip(),
                "list_price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "sold_out": "オプション選択" not in values,
                "is_blend": is_blend,
            })
        time.sleep(0.3)
    return items


def fetch_detail(pid: str) -> dict:
    html_text = fetch(f"{BASE_URL}/product/{pid}")
    # 単位オプション(最小サイズ)とその価格
    units = [(int(w), uid) for uid, w in UNIT_OPTION_PATTERN.findall(html_text)]
    weight_g, price = None, None
    if units:
        weight_g, uid = min(units)
        pm = re.search(rf"priceArray\[1\]\[{uid}\]\[\d+\]\s*=\s*(\d+)", html_text)
        price = int(pm.group(1)) if pm else None

    soup = BeautifulSoup(html_text, "html.parser")
    text = unicodedata.normalize("NFKC", soup.get_text("\n", strip=True))
    start = text.find("返品特約に関する重要事項")
    end = text.find("他の写真")
    body = text[start:end] if 0 <= start < end else ""
    lines = [ln.strip() for ln in body.split("\n")[1:] if ln.strip()]
    lines = [ln for ln in lines if "クリックポスト" not in ln and ln not in ("お問い合わせ", "・")]
    return {"weight_g": weight_g, "price": price, "lines": lines}


def parse_labels(lines: list[str]) -> tuple[dict, str]:
    """「【生産国】メキシコ」形式と「生産国\\nメキシコ」(ラベル行の次行が値)形式の両方を読む。"""
    names = ("商品名", "生産国", "標高", "精製方法", "品種", "生産量", "農園", "地域", "備考", "配合")
    labels, rest = {}, []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^【(.+?)】\s*(.*)$", ln)
        if m and m.group(1) in names:
            labels[m.group(1)] = m.group(2).strip()
        elif ln in names and i + 1 < len(lines) and lines[i + 1] not in names:
            labels[ln] = lines[i + 1].strip()
            i += 1
        elif ln in names:
            labels[ln] = ""  # 値が空のラベル(例: 「生産量」の次が「備考」)
        else:
            rest.append(ln)
        i += 1
    return labels, " ".join(rest)


def build_record(item: dict, detail: dict) -> dict:
    name = re.sub(r"\s+", " ", item["title"]).strip()
    parsed = parse_product(name)
    labels, rest = parse_labels(detail["lines"])
    if item["is_blend"]:
        parsed["category"] = "ブレンド"
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        processing = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and labels.get("生産国"):
            c = detect_country_name(labels["生産国"])
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"
        processing = parsed["processing_method"]
        if not processing and labels.get("精製方法"):
            processing = normalize_processing_method(labels["精製方法"])

    roast_m = ROAST_PATTERN.search(name.replace(" ", ""))
    hint_m = ROAST_HINT_PATTERN.search(name)
    farm_bits = [f"{k}: {labels[k]}" for k in ("農園", "地域", "標高", "品種") if labels.get(k)]
    price = detail["price"] if detail["price"] is not None else item["list_price"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": (roast_m.group(1) + "ロースト") if roast_m else None,
        "roast_hint": hint_m.group(1) if hint_m else None,
        "flavor_notes": (" ".join(x for x in ([f"配合: {labels['配合']}"] if labels.get("配合") else []) + [labels.get("備考", ""), rest] if x)[:300]) or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": detail["weight_g"],
        "stock_status": "完売" if item["sold_out"] else "販売中",
        "out_of_stock": item["sold_out"],
        "product_url": f"{BASE_URL}/product/{item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        try:
            detail = fetch_detail(it["pid"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={it['pid']} ({e})")
            continue
        records.append(build_record(it, detail))
        time.sleep(0.3)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_asiashokai.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_asiashokai.json に出力しました")


if __name__ == "__main__":
    main()
