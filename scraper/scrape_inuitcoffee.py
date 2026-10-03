# -*- coding: utf-8 -*-
"""
scrape_inuitcoffee.py

葉山 inuit coffee roaster(www.rakuten.co.jp/inuitcoffee、神奈川県三浦郡葉山町堀内387、店舗運営責任者 乾 恵美、
葉山の海辺で自家焙煎するスペシャルティコーヒー専門店、Qグレーダー在籍)の楽天市場店の商品情報を取得する。
楽天市場(item.rakuten.co.jp、EUC-JP)。

【自家焙煎・住所の確認(2026-10)】
楽天市場の会社概要(info.html)に「〒240-0112 神奈川県三浦郡葉山町堀内387」「豆本来の個性を最大限活かしながら
葉山の店舗で丁寧に焙煎しています」とあり、商品説明にも「焙煎から2日以内のものをお送りします」「焙煎所」とある。
単独店舗。

【取得方法】
楽天市場のrobots.txt(www / item とも)は /*?i= /*?s= 等の検索系のみ禁止で、店舗トップ・カテゴリ・商品ページは
通常のGETで取得できる(認証・動的描画不要)。カテゴリページ(オリジナルブレンド=0000000100、シングルオリジン=
0000000105、カフェインレス=0000000127)から商品コードを集め、各商品ページ(https://item.rakuten.co.jp/inuitcoffee/<code>/)
の itemprop="price"(税込)・itemprop="availability"・商品名(title)・説明文(span.item_desc)を読む。
カテゴリページには削除済みの商品コード(404)も出るため、404は読み飛ばす。サーバーが遅い(1ページ数秒)ため
リクエスト間隔は0.5秒とし、取得に時間がかかる。

【対象商品について】
実データ確認済み(2026-10時点): 商品名が「スペシャルティコーヒー 200g【 銘柄 】」(一部100g)の単品コーヒー豆
(ブレンド3・シングルオリジン・デカフェ)のみを収録する。除外: トライアルセット・バラエティセット・
飲み比べセット・ギフトセット・ドリップバッグ・水出しパック・手提げ袋。各商品は1サイズ1ページ
(200g、希少ロットは100g)で、同一銘柄の複数サイズ展開は無い。
商品名は【】内の銘柄名(「[ カフェインレスコーヒー ]」の見出しは除く)、価格は税込、重量は商品名の「200g」「100g」。
焙煎度は説明の「ロースト度合い:フレンチロースト(深煎り)」から取る。
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
    "name": "葉山 inuit coffee roaster",
    "url": "https://www.rakuten.co.jp/inuitcoffee/",
    "platform": "楽天市場",
    "address": "神奈川県三浦郡葉山町堀内387",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
}

SHOP_ID = "inuitcoffee"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
CATEGORY_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/c/" + "{cid}/"
CATEGORY_IDS = ["0000000100", "0000000105", "0000000127"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップバッグ", "水出し", "手提げ", "トライアル", "バラエティ", "飲み比べ")

TITLE_PATTERN = re.compile(r"^スペシャルティコーヒー\s*(\d+)\s*g\s*【\s*(.+?)\s*】")
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')
AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ー?ロースト")
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
SPEC_PATTERN = re.compile(r"^(産地|標高|品種|精選方法|精製方法|ロースト度合い|使用銘柄|生豆生産国名)[:：]\s*(.+)$")


def fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp


def list_codes() -> list[str]:
    codes: list[str] = []
    for cid in CATEGORY_IDS:
        resp = fetch(CATEGORY_URL.format(cid=cid))
        for code in re.findall(rf"item\.rakuten\.co\.jp/{SHOP_ID}/([\w-]+)/", resp.text):
            if code != "c" and code not in codes:
                codes.append(code)
        time.sleep(0.5)
    return codes


def build_record(code: str) -> dict | None:
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        return None  # 削除済み商品コード
    html_text = resp.text
    title_m = re.search(r"<title>([^<]*)</title>", html_text)
    if not title_m:
        return None
    title = unicodedata.normalize("NFKC", BeautifulSoup(title_m.group(1), "html.parser").get_text())
    title = title.replace("【楽天市場】", "").strip()
    title = re.sub(r"^\[\s*カフェインレスコーヒー\s*\]\s*", "", title)
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    tm = TITLE_PATTERN.match(title)
    if not tm:
        return None
    weight_g = int(tm.group(1))
    name = re.sub(r"\s+", " ", tm.group(2)).strip()

    price_m = PRICE_PATTERN.search(html_text)
    avail_m = AVAIL_PATTERN.search(html_text)
    sold_out = bool(avail_m) and avail_m.group(1) != "InStock"

    soup = BeautifulSoup(html_text, "html.parser")
    desc_el = soup.select_one("span.item_desc") or soup.select_one(".item_desc")
    lines = []
    if desc_el:
        lines = [unicodedata.normalize("NFKC", ln.strip()) for ln in desc_el.get_text("\n", strip=True).split("\n") if ln.strip()]
    specs: dict[str, str] = {}
    story: list[str] = []
    spec_started = False
    for ln in lines:
        if ln.startswith(("◇", "***", "※", "≪")) and not spec_started:
            if ln.startswith(("***", "≪")):
                break
            continue
        m = SPEC_PATTERN.match(ln)
        if m:
            specs[m.group(1)] = m.group(2).strip()
            spec_started = True
            continue
        if spec_started and (ln.startswith(("***", "≪", "※")) or "豆のまま" in ln):
            break
        if not spec_started:
            story.append(ln)

    parsed = parse_product(name)
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
        processing = parsed["processing_method"]
        raw_proc = specs.get("精選方法") or specs.get("精製方法")
        if not processing and raw_proc:
            processing = normalize_processing_method(raw_proc)

    roast_src = specs.get("ロースト度合い", "") or title
    roast_m = ROAST_PATTERN.search(roast_src)
    hint_m = ROAST_HINT_PATTERN.search(roast_src)
    farm_bits = [f"{k}: {specs[k]}" for k in ("産地", "標高", "品種", "使用銘柄") if specs.get(k)]

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
        "flavor_notes": " ".join(story)[:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list[dict]:
    records = []
    for code in list_codes():
        try:
            record = build_record(code)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {code} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_inuitcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_inuitcoffee.json に出力しました")


if __name__ == "__main__":
    main()
