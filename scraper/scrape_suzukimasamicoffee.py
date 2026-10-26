# -*- coding: utf-8 -*-
"""
scrape_suzukimasamicoffee.py

焙煎職人 鈴木正美の店(THE COFFEE CLUB M's COMPANY、千葉県我孫子市若松)の自社EC
(suzukimasami.jp/shop/、EC-CUBE系)の商品情報を取得する。

【対象】全93件のうち、焙煎豆(ブレンド・ストレート・カフェインレス)。
除外: 生豆(自分で焙煎シリーズ)、手網焙煎機、ドリップバッグ各種、職人アイスコーヒーリキッド、
3種セット・ギフトセット、コーヒーシュガー、ペーパーフィルター、保存缶。
【価格・重量】サイズは 50g/100g/150g/200g/250g/1kgセット。50gは少量のため、100gパックの
「豆のまま」の税込価格を代表にする(「100g 1,296円〜」)。
EC-CUBE の classCategories は商品によって (挽き方→サイズ) と (サイズ→挽き方) の2通りの入れ子順があるため、
selectの選択肢ラベルとリーフ名を連結して「豆のまま」「100gパック」を判定する。
【在庫】100gパック・豆のままのリーフの stock_find(false なら品切れ)。
【商品名】タイトルは宣伝文句が長いため、『』内の銘柄名を raw_name に採用し、産地・精製は全文から判定する。
robots.txt: /wp-admin/ のみ禁止(/shop/ は制限なし、2026-10-26確認)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "焙煎職人 鈴木正美の店",
    "url": "https://suzukimasami.jp/shop/products/list",
    "platform": "EC-CUBE(独自ドメイン)",
    "address": "千葉県我孫子市若松139-4 1F",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(2026-10-26確認。/wp-admin/のみDisallow、/shop/配下は制限なし)",
    "source_note": "自社EC(https://suzukimasami.jp/shop/products/list)の商品一覧と各商品ページを2026-10-26に確認。"
                   "住所は公式の店舗案内(https://suzukimasami.jp/shopinfo/)、自家焙煎(直火焼き)は公式トップに基づく。"
                   "100gパックの豆のまま価格を採用。生豆・手網・ドリップバッグ・アイスリキッド・セット・ギフトは除外",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://suzukimasami.jp/shop"
LIST_URL = BASE_URL + "/products/list?disp_number=60&pageno={page}"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2.0

# 一覧の見出し(h4)に含まれていたら焙煎豆ではないとして取得しない
EXCLUDE_TITLE_KEYWORDS = [
    "生豆", "手網", "ドリップバッグ", "リキッド", "セット", "ギフト", "シュガー", "ペルーシュ",
    "フィルター", "保存缶",
]
# 商品名・カテゴリから産地を引けない銘柄(説明文・タイトルで確認)
ORIGIN_OVERRIDES = {
    "955": "ブラジル",  # バブリースペシャル2・カフェインレス: 説明文「ブラジル産スペシャリティ・カフェインレスコーヒー」
    "801": "キューバ",  # キューバ・アイランドTL
}
MIX_PIDS = {"914"}  # フレンチ・モカ: エチオピア+イエメンのモカMix(複数産地のためブレンド扱い)
KNOWN_GRIND_IDS = {"10": "豆のまま", "9": "極細挽き", "8": "中挽き", "7": "粗挽き"}
CLASS_MARKER = "eccube.classCategories = "
BRACKET_RE = re.compile(r"『([^』]+)』|【([^】]+)】")
ROAST_LABEL_RE = re.compile(r"(極深煎り|中深煎り|深煎り|中浅煎り|浅煎り|中煎り)")
SOLD_OUT_TITLE_RE = re.compile(r"Sorry\s*Sold\s*out", re.I)

_last = [0.0]


def fetch(url: str) -> str:
    wait = REQUEST_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
    _last[0] = time.time()
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_products() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    page = 1
    while True:
        soup = BeautifulSoup(fetch(LIST_URL.format(page=page)), "html.parser")
        items = soup.select("li.ec-shelfGrid__item")
        new = 0
        for it in items:
            a = it.select_one("a[href*='/products/detail/']")
            h = it.select_one("h4")
            if not a or not h:
                continue
            pid = re.search(r"/products/detail/(\d+)", a["href"]).group(1)
            if pid not in [x[0] for x in out]:
                out.append((pid, h.get_text(strip=True)))
                new += 1
        if not new:
            break
        page += 1
    return out


def extract_class_categories(html_text: str) -> dict:
    i = html_text.find(CLASS_MARKER)
    if i < 0:
        return {}
    start = html_text.find("{", i)
    depth = 0
    for k in range(start, len(html_text)):
        if html_text[k] == "{":
            depth += 1
        elif html_text[k] == "}":
            depth -= 1
            if depth == 0:
                break
    try:
        return json.loads(html_text[start:k + 1])
    except json.JSONDecodeError:
        return {}


def find_100g_bean_leaf(soup: BeautifulSoup, cc: dict) -> dict | None:
    """「豆のまま」×「100gパック」のリーフ(価格・在庫)を返す。入れ子順はどちらでも対応する。"""
    labels1 = {o.get("value"): o.get_text(strip=True) for o in soup.select("select[name=classcategory_id1] option")}
    for outer_id, inner in cc.items():
        # 品切れ商品はselectの選択肢が空になるため、挽き方IDの既知値(10=豆のまま)で補う
        outer_label = labels1.get(outer_id) or KNOWN_GRIND_IDS.get(outer_id, "")
        for leaf in inner.values():
            if not leaf.get("product_class_id"):
                continue
            label = unicodedata.normalize("NFKC", f"{outer_label} {leaf.get('name', '')}")
            if "豆のまま" in label and re.search(r"(?<!\d)100g", label):
                return leaf
    return None


def parse_detail(pid: str, list_title: str) -> dict | None:
    url = f"{BASE_URL}/products/detail/{pid}"
    html_text = fetch(url)
    soup = BeautifulSoup(html_text, "html.parser")
    h = soup.select_one(".ec-productRole__title h2")
    title = h.get_text(strip=True) if h else list_title
    cc = extract_class_categories(html_text)
    leaf = find_100g_bean_leaf(soup, cc)
    if leaf is None:
        print(f"[skip] 100g豆のまま無し: {pid} {title[:30]}")
        return None
    price = int(leaf["price02_inc_tax"].replace(",", ""))
    sold_out = (not leaf.get("stock_find")) or bool(SOLD_OUT_TITLE_RE.search(title))

    cats = [a.get_text(strip=True) for a in soup.select(".ec-productRole__category a")]
    cat_set = set(cats)
    desc_el = soup.select_one(".ec-productRole__description")
    desc_lines = [l.strip() for l in desc_el.get_text("\n", strip=True).split("\n")] if desc_el else []
    desc_lines = [l for l in desc_lines if l and not re.match(r"^[=＝・\-\s]*$", l) and "Sold out" not in l]
    flavor_notes = " ".join(desc_lines[:2])[:200] or None

    m = BRACKET_RE.search(title)
    name = (m.group(1) or m.group(2)).strip() if m else re.sub(r"^[\s☆彡※＝=]*(Sorry Sold out[＝=\s]*)?[☆彡\s]*", "", title).strip()

    is_blend = "ブレンド" in cat_set or pid in MIX_PIDS
    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if pid in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[pid]
            parsed["origin_source"] = "description"
        if not parsed["origin_country"]:
            c = detect_country_name(" ".join(cats))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "category_hint"
        if not parsed["origin_country"]:
            parsed = apply_category_hint_fallback(parsed, " ".join(cats))

    rm = ROAST_LABEL_RE.search(title)
    roast = rm.group(1) if rm else parsed["roast_level"]
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
        "roast_hint": None,
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, title in list_products():
        if any(k in title for k in EXCLUDE_TITLE_KEYWORDS):
            print(f"[exclude] {pid} {title[:40]}")
            continue
        try:
            rec = parse_detail(pid, title)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗 {pid}: {e}")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_suzukimasamicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_suzukimasamicoffee.json に出力しました")


if __name__ == "__main__":
    main()
