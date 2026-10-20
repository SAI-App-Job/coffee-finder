# -*- coding: utf-8 -*-
"""
scrape_uemachicoffee.py

上町珈琲(有限会社上町珈琲、大阪市天王寺区上本町8-2-3、1943年創業の珈琲・紅茶専門店)の
独自EC「上町珈琲オンラインショップ」(uemachicoffee.shop-pro.jp、カラーミーショップ)の
コーヒー豆カテゴリ(cbid=2673519)の商品情報を取得する。

【独自ECを採用した理由】
同店は楽天市場店(www.rakuten.co.jp/auc-uemachicoffee/)にも出店しているが、独自ECは
コーヒー豆カテゴリだけで66商品(上町ブレンド・ハイクラス・ストレート・スペシャルティ・
カフェインレス等)と品目が最も揃っており、豆のまま・100g単位の価格も商品ページで確認しやすいため。

【実店舗・自家焙煎の根拠】
公式サイト https://uemachicoffee.com/history/ に「小売店・焙煎工場を現在の地に移転。…PROBAT社製
コーヒーロースターを導入し、厳選された生豆と熟練の焙煎による店頭販売」、
https://uemachicoffee.com/uemachicoffee/ に「コーヒーは世界各地の生豆を取り寄せています」
「焙煎人が毎日心をこめて焙煎しています」「実店舗での価格」(営業9-18時、日祝定休)と記載。

【対象商品】
コーヒー豆カテゴリの単品(ブレンド・シングルオリジン・デカフェ)の豆のまま、最小重量(通常100g)の価格。
除外: セット・詰め合わせ・ギフト、水出しアイスコーヒーバッグ、ディップスタイルバッグ、
まとめ買い(600g)、500g大袋(同銘柄の100gが別ページにあるため)。
同一銘柄が複数ページにある場合(SKIP_PIDS参照)は最小重量のページを代表にする。
在庫は商品ページの「SOLD OUT」表示で判定する(在庫数管理は未使用)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name, apply_category_hint_fallback

SHOP_INFO = {
    "name": "上町珈琲",
    "url": "https://uemachicoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "大阪府大阪市天王寺区上本町8-2-3",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-20確認。User-agent: *は/secure/と/cart/のみ制限)",
    "source_note": "独自EC(https://uemachicoffee.shop-pro.jp/)のコーヒー豆カテゴリと各商品ページ、特商法ページを2026-10-20に確認。"
                   "実店舗・焙煎工場は公式サイト(https://uemachicoffee.com/history/ ほか)で確認。楽天市場店(https://www.rakuten.co.jp/auc-uemachicoffee/)にも出店しているが品目の多い独自ECを採用",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://uemachicoffee.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=cate&cbid=2673519&csid=0&page={page}"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1.5

EXCLUDE_KEYWORDS = ["セット", "ギフト", "バッグ", "バック", "まとめ買い", "大袋"]
# 同一銘柄の別ページ(最小重量のページを代表にするため除外)
SKIP_PIDS = {
    "157220764": "ブルーマウンテンブレンド(200g〜)。100gの158993949を代表にする",
    "168765163": "アイスブレンド(200g〜)。100gの158993955を代表にする",
    "158994022": "マンデリンG1。同一銘柄・同条件の185981546を代表にする",
    "158994000": "コピルアク・ワイルド(50g×2の重複ページ)。187470411を代表にする",
}
ORIGIN_OVERRIDE = {
    "158994007": "ジャマイカ",   # ブルーマウンテンNO.1(カテゴリ「ジャマイカ・キューバ」)
    "158993966": "ペルー",       # マチュピチュ
    "158994006": "アメリカ(ハワイ)",  # ハワイコナ
    "158994014": "イエメン",     # モカマタリNO.9(名前に「イェーメン」)
}
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|深煎り|中煎り|浅煎り)")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(?:g|入)")
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def list_pids() -> list[str]:
    pids: list[str] = []
    for page in range(1, 15):
        soup = fetch_page(LIST_URL.format(page=page))
        found = 0
        for a in soup.select('a[href*="pid="]'):
            m = re.search(r"pid=(\d+)", a.get("href", ""))
            if m and m.group(1) not in pids:
                pids.append(m.group(1))
                found += 1
        time.sleep(CRAWL_DELAY_SECONDS)
        if found == 0:
            break
    return pids


def extract_product_json(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        m = COLORME_JSON_PATTERN.search(script.string or script.get_text() or "")
        if m:
            try:
                return json.loads(m.group(1)).get("product")
            except json.JSONDecodeError:
                return None
    return None


def to_num_weight(s: str) -> int | None:
    m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", s or ""))
    return int(m.group(1)) if m else None


def pick_variant(product: dict, page_weight: int | None) -> tuple[int | None, int | None]:
    """豆のまま(「豆」を含む選択肢)で最小重量の(価格, 重量)を返す。"""
    variants = product.get("variants") or []
    cands = []
    for v in variants:
        o1, o2 = v.get("option1_value") or "", v.get("option2_value") or ""
        if "豆" not in o1 + o2:
            continue
        w = to_num_weight(o1) or to_num_weight(o2) or page_weight
        cands.append((w if w is not None else 10 ** 6, v["option_price_including_tax"], w))
    if not cands:
        return product.get("sales_price_including_tax"), page_weight
    cands.sort(key=lambda c: c[0])
    return cands[0][1], cands[0][2]


def detect_origin(name: str, body: str) -> str | None:
    for src in (name, body):
        m = re.search(r"[原生]\s*産\s*[国地]\s*[:：】]?\s*([^\s）\)】]+)", src)
        if m:
            c = detect_country_name(m.group(1))
            if c:
                return c
    return detect_country_name(name)


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    soup = fetch_page(url)
    product = extract_product_json(soup)
    if not product:
        return None
    name = re.sub(r"\s+", " ", (product.get("name") or "").strip())
    name_sold = "完売" in name
    name = re.sub(r"【完売】|再入荷\s*", "", name).strip()
    if any(k in name for k in EXCLUDE_KEYWORDS):
        return None
    text = unicodedata.normalize("NFKC", soup.get_text("\n", strip=True))
    m = re.search(r"重量\s*\n?\s*(\d+)\s*g", text)
    page_weight = int(m.group(1)) if m else None
    if page_weight is None:
        # 重量欄が無い商品は商品名の「100g」、無ければ本文の【内容量】から補う
        page_weight = to_num_weight(name)
    if page_weight is None:
        cm = re.search(r"内\s*容\s*量】\s*(\d+)\s*g", text)
        page_weight = int(cm.group(1)) if cm else None
    price, weight = pick_variant(product, page_weight)
    cart_area = text.split("レビューを見る")[0]
    sold_out = "SOLD OUT" in cart_area or name_sold

    body = text.split("ツイート", 1)[-1].split("カテゴリーを選択")[0]
    is_blend = "ブレンド" in name
    parsed = parse_product(name)
    rm = ROAST_PATTERN.search(unicodedata.normalize("NFKC", name))
    roast = rm.group(1) if rm else parsed["roast_level"]
    if not rm:
        bm = re.search(r"焙\s*煎\s*度】\s*([^\n]+)", body)
        if bm:
            r2 = ROAST_PATTERN.search(bm.group(1))
            roast = r2.group(1) if r2 else roast
    if not rm and roast is None:
        # パンくず「焙煎度から選ぶ > 中煎り」から補う(複数該当する場合は採用しない)
        crumbs = re.findall(r"焙煎度から選ぶ\s*>\s*(\S+煎り)", text)
        if len(set(crumbs)) == 1:
            roast = crumbs[0]
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        origin = ORIGIN_OVERRIDE.get(pid) or detect_origin(name, body)
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "shop_attribute"
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
    fm = re.search(r"味の特徴[:：]\s*([^\n]+)", body)
    flavor = fm.group(1).strip() if fm else None
    stock_status = "完売" if sold_out else "販売中"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "flavor_notes": flavor,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in list_pids():
        if pid in SKIP_PIDS:
            continue
        try:
            rec = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {pid} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_uemachicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_uemachicoffee.json に出力しました")


if __name__ == "__main__":
    main()
