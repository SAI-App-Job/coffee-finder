# -*- coding: utf-8 -*-
"""
scrape_kusacafe.py

KUSA.喫茶 自家焙煎COFFEE+PAN.(kusacafe.shop-pro.jp、千葉県長生郡長生村一松乙1987-14、
店主 姫野博、FUJI ROYAL直火3kg釜+DIEDRICH半熱風12kg釜で自家焙煎)の商品情報を取得する。
カラーミーショップ(charset=euc-jpのため`r.encoding = "euc-jp"`を明示する)。

【店舗発見の経緯】
千葉県の自家焙煎店調査(カラーミーショップ系)で発見。

【対象商品について】
実データ確認済み(2026-10時点): 次の2カテゴリのみを対象とする(1ページ6件の
ページ送り、&page=Nで全件取得)。
  ・珈琲豆 オリジナルブレンド(cbid=2571904、全6件)
  ・珈琲豆 シングルオリジン産地別(cbid=2571905、全20件)
「KUSA.のスペシャル珈琲商品」(リキッドアイス珈琲・ダンクスタイル珈琲=ドリップバッグ類・
ルイボスティー・焼菓子・シュトレン)と「KUSA.セレクション作品」(書籍等)は対象外。
同一銘柄が100g〜500gの複数重量で選べる(variantsは重量別、価格は重量が増えるほど割引)ため、
最小の100gの価格を代表とする(名前の「重量　価格」行の先頭variant=100g)。
売切れ商品は商品名に「＜SOLD OUT＞」が付き在庫数0になるため、完売として収録する
(商品名からは「＜SOLD OUT＞」を除去する)。
商品名は「BRAZIL 〜 フレンチロースト（深煎り）」のように英字大文字の産地名+焙煎度表記で、
「COSTARICA」のように辞書(coffee_parser)の「costa rica」と綴りが異なるものは
ORIGIN_ALIASESで補う。ブレンドは商品名に「BLEND」を含む(origin None・category ブレンド)。
本文の「産地/品種/精製方法」行はfarm_note、それ以外の説明文はflavor_notesとする。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "KUSA.喫茶 自家焙煎COFFEE+PAN.",
    "url": "https://kusacafe.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "千葉県長生郡長生村一松乙1987-14",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://kusacafe.shop-pro.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = ["2571904", "2571905"]  # オリジナルブレンド / シングルオリジン産地別
MAX_PAGES = 10

# 商品名の綴りが辞書と異なる産地(正規化後の小文字で判定)
ORIGIN_ALIASES = {
    "costarica": "コスタリカ",
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)
FARM_LINE_PATTERN = re.compile(r"^(産地|品種|精製方法|精製)\s")
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ー?ロースト")
SOLD_OUT_PATTERN = re.compile(r"[＜<]\s*SOLD\s*OUT\s*[＞>]\s*", re.IGNORECASE)


def detect_roast_level(name: str) -> str | None:
    """「○○ロースト」の明示表記のみから焙煎度を取る(「ハイツ農園」の「ハイ」等への誤爆防止)。"""
    m = ROAST_PATTERN.search(name)
    return f"{m.group(1)}ロースト" if m else None


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_product_ids() -> list[str]:
    ids: list[str] = []
    for cbid in CATEGORY_IDS:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0&page={page}"
            found = re.findall(r"\?pid=(\d+)", fetch(url))
            new = [pid for pid in dict.fromkeys(found) if pid not in ids]
            if not new:
                break
            ids.extend(new)
    return ids


def clean_name(raw: str) -> str:
    name = SOLD_OUT_PATTERN.sub("", raw)
    name = re.sub(r"[＜<][^＞>]*リリース[^＞>]*[＞>]", "", name)
    name = name.replace("☆", "")
    name = re.sub(r"[\s　]+", " ", name).strip()
    return name


def build_record(pid: str) -> dict | None:
    html_text = fetch(f"{BASE_URL}/?pid={pid}")
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product") or {}
    title = (product.get("name") or "").strip()
    if not title:
        return None
    name = clean_name(title)
    sold_out = bool(SOLD_OUT_PATTERN.search(title)) or product.get("stock_num") == 0

    # 代表重量=先頭variant(100g)
    variants = product.get("variants") or []
    price = product.get("sales_price_including_tax")
    weight_g = None
    if variants:
        first = variants[0]
        price = first.get("option_price_including_tax", price)
        wm = WEIGHT_PATTERN.search(first.get("option1_value") or "")
        if wm:
            weight_g = int(wm.group(1))

    # 説明文(商品名行〜「販売価格」行)
    lines = [ln.strip() for ln in BeautifulSoup(html_text, "html.parser").get_text("\n", strip=True).split("\n") if ln.strip()]
    end = next((i for i, ln in enumerate(lines) if ln == "販売価格"), len(lines))
    starts = [i for i in range(end) if lines[i] == title]
    farm_lines, desc_lines = [], []
    if starts:
        for ln in lines[starts[-1] + 1:end]:
            if ln.startswith("ーーー"):
                continue
            (farm_lines if FARM_LINE_PATTERN.match(ln) else desc_lines).append(re.sub(r"[\s　]+", " ", ln))

    if weight_g is None:
        # variantsが無い場合の代替(本文「グラム」欄の先頭行)
        for i, ln in enumerate(lines):
            if ln == "グラム" and i + 1 < len(lines):
                wm = WEIGHT_PATTERN.search(lines[i + 1])
                if wm:
                    weight_g = int(wm.group(1))
                break

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if not detected:
            low = unicodedata.normalize("NFKC", name).lower()
            detected = next((c for k, c in ORIGIN_ALIASES.items() if k in low), None)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": detect_roast_level(name),
        "roast_hint": None,
        "flavor_notes": " ".join(desc_lines) or None,
        "farm_note": " / ".join(farm_lines) or None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in list_product_ids():
        try:
            record = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: pid={pid} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kusacafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kusacafe.json に出力しました")


if __name__ == "__main__":
    main()
