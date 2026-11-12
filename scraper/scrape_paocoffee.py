# -*- coding: utf-8 -*-
"""
scrape_paocoffee.py

パオコーヒー(有限会社サーティーフーズ、東京都調布市西つつじヶ丘3-15-2)の楽天市場店
(www.rakuten.co.jp/paocoffee)の商品情報を取得する。楽天市場(item.rakuten.co.jp、EUC-JP)。

【実店舗・自家焙煎の根拠】(2026-10-25確認)
楽天市場の会社概要(https://www.rakuten.co.jp/paocoffee/info.html)で所在地「東京都調布市西つつじヶ丘3-15-2」、
店名見出し「いりたて自家焙煎コーヒー豆専門店。新鮮なコーヒーが約30種類!」。商品名すべてに「自家焙煎 珈琲豆」。

【楽天市場店を採用した理由】
自社ECは未確認(販売先は楽天市場のみ)。

【対象商品について】
ショップカテゴリ「【お試し用ミニサイズ】100gコーヒー」(c/0000000308)の商品のうち、豆の単品
(ストレート・ブレンド・デカフェ)の100gミニパック。各銘柄は500g・1kgの大容量も別商品として存在するが、
最小重量の100gを代表とする。価格は豆のままのSKUの税込価格。
除外: ドリップバッグ(coffee_drip)・リキッド・水出しバッグ・カフェポッド・器具・濾紙・紅茶、
カテゴリ外の200g/500g/1kg版。

【ページ構造】商品ページは EUC-JP。ページ内に他商品(おすすめ)の "sku":[...] も埋め込まれるため、
"newItemNumber":"<商品番号>" の後ろにある最初の "sku" 配列を当該商品のSKUとして採用する。
在庫は axis の内容量(100g)の isSoldOut。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "パオコーヒー",
    "url": "https://www.rakuten.co.jp/paocoffee/",
    "platform": "楽天市場",
    "address": "東京都調布市西つつじヶ丘3-15-2",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可とみなす(2026-10確認。rakuten.co.jp/item.rakuten.co.jpのrobots.txtは検索系パラメータ(?i= ?s=)等のみ禁止)",
    "source_note": "楽天市場店(https://www.rakuten.co.jp/paocoffee/)の「【お試し用ミニサイズ】100gコーヒー」カテゴリと各商品ページ(SKU情報)を2026-10-25に確認。会社概要(info.html)で所在地を確認。出店20周年、営業日案内あり(現行)",
    "last_verified_at": "2026-10-25",
}

SHOP_ID = "paocoffee"
CATEGORY_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/c/0000000308/"
ITEM_URL = f"https://item.rakuten.co.jp/{SHOP_ID}/" + "{code}/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 3
NON_BEAN_KEYWORDS = ["ドリップ", "リキッド", "水出し", "ポッド", "カリタ", "ハリオ", "濾紙", "フィルター", "セット", "紅茶"]
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|深煎り|中煎り|浅煎り)")
ROAST_ROMAN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|シティ|フルシティ|フレンチ|イタリアン)ロースト")


def fetch(url: str) -> requests.Response:
    resp = None
    for attempt in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=90)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.encoding = "euc-jp"
    return resp


def extract_json_array(html_text: str, start: int) -> list:
    """html_text[start] が '[' の位置から括弧対応でJSON配列を切り出す。"""
    depth, in_str, esc = 0, False, False
    for k in range(start, len(html_text)):
        ch = html_text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == chr(92):
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(html_text[start:k + 1])
    return []


def extract_skus(html_text: str, code: str) -> list[dict]:
    """当該商品番号の後ろにある最初の "sku":[...] を返す(ページ内には他商品のSKUも埋め込まれる)。"""
    i = html_text.find(f'"newItemNumber":"{code}"')
    if i < 0:
        return []
    j = html_text.find('"sku":[', i)
    if j < 0:
        return []
    return extract_json_array(html_text, j + len('"sku":'))


def list_codes() -> list[str]:
    resp = fetch(CATEGORY_URL)
    if resp.status_code != 200:
        print(f"[warn] カテゴリページ取得失敗: HTTP {resp.status_code}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    codes, seen = [], set()
    for a in soup.select(f'a[href*="item.rakuten.co.jp/{SHOP_ID}/"]'):
        m = re.search(rf"{SHOP_ID}/([^/?#]+)/", a["href"])
        if not m or m.group(1) == "c" or m.group(1) in seen:
            continue
        text = unicodedata.normalize("NFKC", a.get_text(" ", strip=True))
        # カテゴリ本体の豆100g商品のみ(おすすめ欄の器具・ドリップ等は名称で除外)
        if not re.search(r"100\s*g", text) or any(k in text for k in NON_BEAN_KEYWORDS):
            continue
        seen.add(m.group(1))
        codes.append(m.group(1))
    return codes


def build_record(code: str) -> dict | None:
    resp = fetch(ITEM_URL.format(code=code))
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {code} (HTTP {resp.status_code})")
        return None
    html_text = resp.text
    tm = re.search(rf'"newItemNumber":"{re.escape(code)}","title":"([^"]*)"', html_text)
    title = unicodedata.normalize("NFKC", tm.group(1)) if tm else ""
    skus = extract_skus(html_text, code)
    cand = None
    for s in skus:
        vals = " ".join(s.get("selectorValues") or [])
        if "100g" in vals and "豆のまま" in vals:
            cand = s
            break
    if cand is None:
        print(f"[warn] 100g・豆のままのSKUなし: {code}")
        return None
    price = int(cand["taxIncludedPrice"])
    attrs = {a["title"]: a.get("value") for a in cand.get("attributes", [])}

    # 在庫: axis の内容量(100g)の isSoldOut
    sold_out = False
    am = re.search(r'"axis":\[\{"key":"内容量","label":"内容量","values":\[\{"value":"100g","label":"100g","isSoldOut":(true|false)', html_text)
    if am:
        sold_out = am.group(1) == "true"

    name = re.sub(r"^.*】", "", title).strip()
    name = re.sub(r"\s*[（(]?\s*100g\s*[）)]?\s*/.*$", "", name).strip()
    name = re.sub(r"\s*[（(]?\s*100g\s*[）)]?\s*$", "", name).strip()
    name = name.replace("・NO.1", " NO.1")
    is_decaf = "デカフェ" in name or "カフェインレス" in title or "ノンカフェイン" in title

    soup = BeautifulSoup(html_text, "html.parser")
    desc_el = soup.select_one(".sale_desc")
    desc_text = unicodedata.normalize("NFKC", desc_el.get_text("\n", strip=True)) if desc_el else ""
    roast = None
    for m in re.finditer(r"焙煎[：:]\s*([^\n]+)", desc_text):
        rm = ROAST_PATTERN.search(m.group(1))
        if rm:
            roast = rm.group(1)
    roast_en = None
    for m in re.finditer(r"焙煎[：:]\s*([^\n]+)", desc_text):
        rr = ROAST_ROMAN.search(m.group(1))
        if rr:
            roast_en = rr.group(0)
    # 風味説明: シリーズ共通の説明(【シリーズ名】見出しの直後の行)と店共通の導入文を除いた最初の長い段落
    paras, prev = [], ""
    for ln in desc_text.splitlines():
        is_series_text = prev.startswith("【") and prev.endswith("】")
        if len(ln) > 40 and not is_series_text and not ln.startswith(("約30種類", "いろいろな", "名の知れた")):
            paras.append(ln)
        prev = ln
    flavor = None

    is_blend = attrs.get("シングルオリジン・ブレンド") == "ブレンド" or "ブレンド" in name or name in ("和み",)
    parsed = parse_product(name)
    origin = attrs.get("コーヒー・茶の原料原産地")
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        c = detect_country_name(origin or "") or detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "shop_attribute" if origin else "raw_name"
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
        "roast_level": roast or roast_en or parsed["roast_level"],
        "roast_hint": roast_en if roast else None,
        "flavor_notes": flavor,
        "_paras": paras,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "decaf_process": "デカフェ(除去方法の詳細記載なし)" if is_decaf else None,
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": ITEM_URL.format(code=code),
    }


def scrape_all_products() -> list[dict]:
    records = []
    codes = list_codes()
    for i, code in enumerate(codes):
        time.sleep(REQUEST_INTERVAL)
        rec = build_record(code)
        if rec:
            records.append(rec)
    # 風味説明: 3商品以上に共通する段落(シリーズ説明・サイクロン被害のお知らせ等)は商品固有でないため除く
    from collections import Counter
    freq = Counter(p for r in records for p in set(r["_paras"]))
    for r in records:
        own = [p for p in r.pop("_paras") if freq[p] < 3]
        r["flavor_notes"] = own[0][:400] if own else None
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_paocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_paocoffee.json に出力しました")


if __name__ == "__main__":
    main()
