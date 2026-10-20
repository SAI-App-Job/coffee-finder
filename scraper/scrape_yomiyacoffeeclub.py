# -*- coding: utf-8 -*-
"""
scrape_yomiyacoffeeclub.py

夜宮珈琲倶楽部(https://shop.yomiyacoffee.club/、福岡県北九州市戸畑区一枝1-7-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
楽天/Yahoo!等のモール・独自EC調査の新規発掘。
同店の公式SHOP(https://yomiya-official-shop-parent.yomiyacafe.workers.dev/shop、11商品・200g)は
同じ店の別販売先だが、BASE店(sitemap上32商品、うち豆31)のほうが品目が多く100g単位で価格を比較しやすいため
BASE店を採用し、公式SHOPは重複させない。

【対象商品について】
BASEトップは一覧がJS描画で取りにくいため、sitemap.xml から商品URLを集めて個別商品ページから取得する
(sitemap確認: 2026-10-20。商品32件のうちドリップバッグ10は除外し、豆31件)。
全商品とも内容量100g(商品説明に記載)。価格・在庫は商品ページ、説明文はJSON-LDのdescriptionから取得する。
産地・焙煎度は説明文の「Coffee Profile」欄(生産国/原産国・焙煎度)から取得する。
焙煎度は「ご注文を受けてから焙煎」で購入時にオプションで浅め/深めを選べるため、説明欄の標準焙煎度を採用する。
豆のまま/中挽き/粗挽きはオプションで選べ、価格は同一。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では許可)。
本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "夜宮珈琲倶楽部",
    "url": "https://shop.yomiyacoffee.club/",
    "platform": "BASE",
    "address": "福岡県北九州市戸畑区一枝1-7-1",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE店(https://shop.yomiyacoffee.club/)のsitemapと商品ページを2026-10-20に確認(最新ブログ2026-09-29、商品更新は随時)。"
                   "全商品100g。ドリップバッグ10は除外。同店の公式SHOP(yomiya-official-shop-parent.yomiyacafe.workers.dev/shop、11商品・200g)は"
                   "別販売先のため重複させずBASE店を採用。商品説明に「北九州市戸畑区の夜宮珈琲倶楽部で自家焙煎」「ご注文を受けてから焙煎」と記載。"
                   "公式サイト(https://yomiyacoffee.club/)に住所・営業時間と「北九州・戸畑の、小さな自家焙煎珈琲店」の記載あり。"
                   "2026-10-15から一部商品の価格改定(公式お知らせ2026-09-20)があり、BASE店の表示価格は改定途中の可能性がある。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://shop.yomiyacoffee.club"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
SLEEP_SEC = 5

# 豆でない商品(ドリップバッグ等)は除外
EXCLUDE_IDS = {"50222171"}  # ドリップバッグ10
# ブレンド(説明の生産国が複数国、または商品名にブレンド表記なし)
BLEND_IDS = {"55876616", "55912348", "59267019", "141575042"}
# 説明の焙煎度が範囲表記で標準が特定できないもの(焙煎度は不明=Noneのまま)
ROAST_UNKNOWN_IDS = {"55912348", "159570814"}

LD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')


def get_item_ids() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    ids = re.findall(r"<loc>https://shop\.yomiyacoffee\.club/items/(\d+)</loc>", resp.text)
    return list(dict.fromkeys(ids))


def map_roast(text: str) -> str | None:
    """Coffee Profileの焙煎度表記を、アプリで使う焙煎度の語彙に寄せる"""
    if "中浅" in text:
        return "中浅煎り"
    if text.startswith("中深"):
        return "中深煎り"
    if text.startswith("中"):
        return "中煎り"
    if "ハイロースト" in text:
        return "ハイロースト"
    if "フルシティ" in text:
        return "中深煎り"
    if "シティ" in text:
        return "中煎り"
    if "深" in text:
        return "深煎り"
    if "浅" in text:
        return "浅煎り"
    return None


def parse_description(desc: str) -> dict:
    flat = re.sub(r"[ \t　]+", " ", desc)
    # 説明文(キャッチコピー部分): 価格改定の告知行・【商品名】行・焙煎度行を除き、---/Coffee Profile/【発送...】/・項目の手前まで
    body_lines = []
    for line in desc.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(("---", "Coffee Profile", "・")) or (line.startswith("【") and not line.endswith("】")):
            break
        if (line.startswith("【") and line.endswith("】")) or line.startswith("焙煎度") or re.match(r"^\d+/\d+より", line):
            continue
        body_lines.append(line)
    body = re.sub(r"\s+", " ", " ".join(body_lines)).strip()[:300] or None

    origin = None
    m = re.search(r"(?:生産国|原産国)[：:]\s*([^\s/／・\-]+)", flat)
    if m:
        origin = m.group(1).strip()
    roast_text = None
    m = re.search(r"焙煎度[：:]\s*([^\n]+)", desc)
    if m:
        roast_text = m.group(1).strip()
    else:
        m = re.search(r"【焙煎度】\s*([^\n]+)", desc)
        if m:
            roast_text = m.group(1).strip()
    weight = None
    m = re.search(r"(?:内\s*容\s*量?|内容)[】：:]*\s*(\d+)\s*[gｇ]", desc)
    if m:
        weight = int(m.group(1))
    return {"body": body, "origin": origin, "roast_text": roast_text, "weight": weight}


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    ld = None
    for m in LD_PATTERN.finditer(html_text):
        try:
            j = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(j, dict) and j.get("@type") == "Product":
            ld = j
            break
    if not ld:
        return None
    name = re.sub(r"\s+", " ", ld["name"]).strip()
    info = parse_description(ld.get("description") or "")
    pur = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(pur) and pur.group(1) == "unpurchasable"
    try:
        price = int(ld["offers"]["price"])
    except (KeyError, TypeError, ValueError):
        price = None

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if item_id in BLEND_IDS:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if info["origin"]:
            detected = detect_country_name(info["origin"]) or info["origin"]
            if not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)

    roast = None if item_id in ROAST_UNKNOWN_IDS else (map_roast(info["roast_text"]) if info["roast_text"] else None)

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
        "roast_hint": info["roast_text"],
        "flavor_notes": info["body"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": info["weight"] or 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    ids = [i for i in get_item_ids() if i not in EXCLUDE_IDS]
    for item_id in ids:
        time.sleep(SLEEP_SEC)
        try:
            record = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yomiyacoffeeclub.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yomiyacoffeeclub.json に出力しました")


if __name__ == "__main__":
    main()
