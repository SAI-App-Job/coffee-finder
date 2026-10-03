# -*- coding: utf-8 -*-
"""
scrape_thebeanscoffee.py

THE BEANS(www.rakuten.co.jp/thebeans、神奈川県綾瀬市綾西4-19-6 A棟、店舗運営責任者 上坂 真衣子、
注文を受けて焙煎度合いを選んで焙煎するオーダーメイド焙煎のスペシャルティコーヒー専門店)の楽天市場店の
商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。

【自家焙煎・住所の確認(2026-10)】
楽天市場の会社概要・店舗紹介ページに「神奈川県の小さな焙煎所で、いろいろなお客様と出会い」「お客様に煎り具合を
決めて頂きます」「どんな味に仕上げたいのか、お伺いしてから(生豆を)焙煎します」とあり、注文焙煎の自家焙煎店を
確認。登録住所(返送先)は神奈川県綾瀬市綾西4-19-6 A棟。調査依頼にあった海老名市柏ヶ谷1036の実店舗は
楽天のページ上では確認できなかったため、住所は楽天の登録住所を採用した。商品ページは2026-10時点で
ハロウィン関連の更新が入っており現行運営。

【取得方法】
楽天市場のrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止で、商品ページは通常のGETで取得できる。カテゴリ
(コーヒー豆=0000000326、ストレート=0000000327、ブレンド=0000000328、カフェインレス=0000000351、
新登場・イベント=0000000304)から商品コードを集め、各商品ページ(https://item.rakuten.co.jp/thebeans/<code>/)の
meta itemprop(price/availability)と、ページ内JSON(variantSelectors / skuごとのtaxIncludedPrice /
variantMappedInventories)を読む。1ページ数秒かかるためリクエスト間隔0.5秒で取得に数分かかる。

【対象商品について】
実データ確認済み(2026-10時点): 商品は「重量」セレクタ(100g/200g/300g大袋/300g小分け袋…)のバリエーション商品が
大半で、現在購入可能なバリエーション(skuの配列に残るもの)のうち最小サイズを代表とし、その税込価格を
採用する(在庫0のバリエーションはskuから外れるため、例えば「カフェオレブレンド」「秋ブレンド」は300gのみ)。
300g単品の「ストレート」系(ブルンジ・コスタリカ・ケニア キング)はセレクタ無しで、商品名の300gと
itemprop価格を使う。
除外: ギフト・セット・福袋・生豆(キャンプ用)・ドリップバッグ・トリオ・LIVE限定特注ブレンド・DOCUMENTコラボ。
「デカフェ(オーガニック、decaf-indonesia-300)」は商品名・説明が画像のみで銘柄名を文字から確認できないため除外。
商品名は楽天のtitle(SEO用の長文)から重量表記より前の銘柄部分を切り出し、「＼ハロウィンブレンド／」のような
強調表記はその中身を名前にする。説明文は画像主体のため、文字で取れた場合のみflavor_notesにする。
焙煎度合いは注文者が選ぶため、roast_levelは持たずroast_hintに記す。売り切れはavailabilityがInStock以外、
または代表バリエーションの在庫が0のもの。
"""

import html as html_lib
import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "THE BEANS",
    "url": "https://www.rakuten.co.jp/thebeans/",
    "platform": "楽天市場",
    "address": "神奈川県綾瀬市綾西4-19-6 A棟",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
}

SHOP_ID = "thebeans"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
CATEGORY_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/c/" + "{cid}/"
CATEGORY_IDS = ["0000000326", "0000000327", "0000000328", "0000000351", "0000000304"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = (
    "セット", "福袋", "生豆", "ドリップバッグ", "ドリップパック", "トリオ", "LIVE", "DOCUMENT", "ポッキリ", "個入",
)
ROAST_HINT = "注文時に焙煎度合いを選択(オーダーメイド焙煎)"

WEIGHT_TOKEN = re.compile(r"\s*(\d+)\s*g\b", re.IGNORECASE)
PRICE_PATTERN = re.compile(r'itemprop="price" content="(\d+)"')
AVAIL_PATTERN = re.compile(r'itemprop="availability" content="[^"]*/(\w+)"')
NOISE_WORDS = ("コーヒー豆", "珈琲豆", "送料無料", "スペシャルティコーヒー")


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


def derive_name(title: str) -> str | None:
    """SEO用の長いtitleから銘柄名を切り出す(重量表記が無ければNone)。"""
    # 「＼ハロウィンブレンド／」のような強調表記にブレンド名が入る場合は、その中身を名前にする
    # (NFKC正規化で「＼」「／」は「\」「/」になっている)
    m = re.search(r"[＼\\]([^／/]*ブレンド[^／/]*)[／/]", title)
    if m and WEIGHT_TOKEN.search(title):
        return re.sub(r"\s+", " ", m.group(1)).strip()
    wm = WEIGHT_TOKEN.search(title)
    if not wm:
        return None
    head = title[:wm.start()]
    head = re.sub(r"[＼\\][^／/]*[／/]", " ", head)
    head = re.sub(r"[【】\[\]]", " ", head)
    for w in NOISE_WORDS:
        head = head.replace(w, " ")
    head = re.sub(r"\b豆 粉\b", " ", head)
    head = re.sub(r"\s+", " ", head).strip()
    return head or None


def parse_variants(html_text: str) -> list[dict]:
    """ページ内JSONのvariantSelectors/sku/variantMappedInventoriesから、現在購入可能なバリエーションを読む。"""
    i = html_text.find('"variantSelectors"')
    if i < 0:
        return []
    seg = html_text[i:i + 60000]
    inv = {}
    inv_m = re.search(r'"variantMappedInventories":(\[.*?\])', html_text)
    if inv_m:
        try:
            inv = {d["sku"]: d.get("quantity", 0) for d in json.loads(inv_m.group(1))}
        except (ValueError, KeyError):
            inv = {}
    variants = []
    for part in re.split(r'(?=\{"variantId":")', seg)[1:]:
        head = re.match(r'\{"variantId":"([^"]+)","selectorValues":\[([^\]]*)\]', part)
        if not head:
            continue
        w_m = re.match(r'\s*"(\d+)\s*g', head.group(2))
        tp = re.search(r'"taxIncludedPrice":([\d.]+)', part)
        if not w_m or not tp:
            continue
        vid = head.group(1)
        if any(v["variant"] == vid for v in variants):
            continue
        variants.append({
            "variant": vid,
            "weight_g": int(w_m.group(1)),
            "price": int(float(tp.group(1))),
            "quantity": inv.get(vid),
        })
    return variants


def build_record(code: str) -> dict | None:
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        return None
    html_text = resp.text
    title_m = re.search(r"<title>([^<]*)</title>", html_text)
    if not title_m:
        return None
    title = unicodedata.normalize("NFKC", html_lib.unescape(title_m.group(1)))
    title = title.replace("【楽天市場】", "")
    title = re.sub(r"[：|｜]\s*THE BEANS\s*$", "", title).strip()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    name = derive_name(title)
    if not name:
        return None

    avail_m = AVAIL_PATTERN.search(html_text)
    in_stock_flag = bool(avail_m) and avail_m.group(1) == "InStock"
    variants = parse_variants(html_text)
    if variants:
        rep = min(variants, key=lambda v: v["weight_g"])
        weight_g, price = rep["weight_g"], rep["price"]
        sold_out = (not in_stock_flag) or (rep["quantity"] is not None and rep["quantity"] <= 0)
    else:
        wm = WEIGHT_TOKEN.search(title)
        price_m = PRICE_PATTERN.search(html_text)
        weight_g = int(wm.group(1)) if wm else None
        price = int(price_m.group(1)) if price_m else None
        sold_out = not in_stock_flag

    soup = BeautifulSoup(html_text, "html.parser")
    desc_el = soup.select_one("td.exT_sdtext")
    desc = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True))) if desc_el else ""

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"]:
            # 「ホンジュラス産カフェイン99%除去」のようにtitle後半に産地がある場合
            m = re.search(r"([ァ-ヶー]+)産", title)
            c = detect_country_name(m.group(1)) if m else None
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": ROAST_HINT,
        "flavor_notes": desc[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
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
    with open("data_thebeanscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_thebeanscoffee.json に出力しました")


if __name__ == "__main__":
    main()
