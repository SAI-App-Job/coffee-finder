# -*- coding: utf-8 -*-
"""
scrape_doicoffee.py

土居珈琲(株式会社土居珈琲、大阪府堺市西区浜寺元町4-496-1、1971年創業、「小さな焙煎」)の
公式サイト(www.doicoffee.com)の銘柄ページの商品情報を取得する。

【販売先について】
楽天市場店(www.rakuten.co.jp/doicoffee/)・Yahoo!ショッピング店(store.shopping.yahoo.co.jp/doicoffee/)にも
出店しているが、公式サイトは全銘柄の100g/200gの価格がページ上で確認できるため公式サイトを採用。

【実店舗・自家焙煎の根拠】
会社概要(https://www.doicoffee.com/about/index.html)に本社棟(浜寺元町4-496-1)・オフィス棟(4-495-1)、
トップページ・各ページに「『小さな焙煎』によって、作りだすコーヒー」「土居珈琲工房 探訪」
「店頭のお受け取りについて 焙煎したてのコーヒーをお渡しさせていただきます(オフィス棟、電話注文)」と記載。
販売店舗は本社の1か所のみ(11店舗以上のチェーンではない)。

【対象商品】
銘柄ページ(/product/NNN/*.html)の単品・ブレンドの豆(100gの価格を代表)と、デカフェ・ビヨンド
(/product/decafe/index.html、1ページに4銘柄)。除外: 飲み比べ・おためしセット・オフィスコーヒーセット・
Made By Hand(ドリップバッグ)・単品定期便の価格・ギフト。
焙煎度合い(ミディアム〜イタリアン)と挽き方は購入時にお客さまが選ぶ方式のため roast_level は None、
roast_selectable=True とする。在庫はページ上の SOLD OUT 表示(コメントアウトされていないもの)で判定。
robots.txt は /dev/ と /test/ のみ Disallow。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "土居珈琲",
    "url": "https://www.doicoffee.com/",
    "platform": "独自サイト(自社カートCGI)",
    "address": "大阪府堺市西区浜寺元町4-496-1",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-20確認。Disallowは/dev/と/test/のみ)",
    "source_note": "公式サイト(https://www.doicoffee.com/)のトップと各銘柄ページ、デカフェ・ビヨンド、会社概要、特商法ページを2026-10-20に確認。"
                   "楽天市場店(https://www.rakuten.co.jp/doicoffee/)・Yahoo!ショッピング店(https://store.shopping.yahoo.co.jp/doicoffee/)にも出店しているが、価格が確認しやすい公式サイトを採用",
    "last_verified_at": "2026-10-20",
}

BASE = "https://www.doicoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1.5
DECAF_URL = BASE + "/product/decafe/index.html"

# セット・ドリップバッグ等(銘柄ID)
EXCLUDE_IDS = {"401", "511", "515", "538", "541", "542", "943"}
# ブレンド(エスプレッソ・アイス用ブレンド含む)の銘柄ID
BLEND_IDS = {"033", "034", "036", "037", "039", "040", "041", "042", "043", "044", "045", "047", "048"}
ORIGIN_OVERRIDE = {"031": "アメリカ(ハワイ)", "049": "ジャマイカ", "051": "ジャマイカ", "069": "ジャマイカ",
                   "032": "インドネシア", "030": "インドネシア"}


def fetch(url: str):
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    if resp.status_code != 200:
        print(f"[warn] 取得失敗: {url} (HTTP {resp.status_code})")
        return None
    try:
        html_text = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        html_text = resp.content.decode("cp932", errors="replace")  # 一部のページはShift_JIS
    return BeautifulSoup(html_text, "html.parser")


def list_product_urls() -> list[str]:
    soup = fetch(BASE + "/")
    urls = []
    for a in soup.find_all("a", href=True):
        m = re.match(r"https://www\.doicoffee\.com/product/(\d+)/[^#?]+\.html$", a["href"])
        if m and m.group(1) not in EXCLUDE_IDS and a["href"] not in urls:
            urls.append(a["href"])
    return urls


def build(name, price, weight, product_id, url, blend, desc, sold_out, country_hint=None):
    parsed = parse_product(name)
    if blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        origin = ORIGIN_OVERRIDE.get(product_id) or country_hint or detect_country_name(name)
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "shop_attribute"
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
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
        "roast_selectable": True,
        "flavor_notes": desc,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def build_from_page(url: str) -> dict | None:
    soup = fetch(url)
    if not soup:
        return None
    pid = re.search(r"/product/(\d+)/", url).group(1)
    og = soup.find("meta", {"property": "og:title"})
    name = re.sub(r"\s+", " ", (og["content"].split("｜")[0] if og else "").replace("　", " ")).strip()
    text = soup.get_text("\n", strip=True)
    seg = text[text.find("商品名"):][:1500]
    m = re.search(r"(\d+)\s*g\s*\n\s*￥\s*\n\s*([\d,]+)", seg)
    if not name or not m:
        print(f"[warn] 名称/価格取得失敗: {url}")
        return None
    weight, price = int(m.group(1)), int(m.group(2).replace(",", ""))
    if price <= 0:
        return None
    sold_out = bool(soup.select(".soldout-back, .soldout-square, .soldout-button-area"))
    d = soup.find("meta", {"property": "og:description"})
    desc = d["content"].strip() if d else None
    if desc and desc.startswith(name):
        desc = desc[len(name):].strip()
    return build(name, price, weight, pid, url, pid in BLEND_IDS, desc, sold_out)


def build_from_decaf_page() -> list[dict]:
    soup = fetch(DECAF_URL)
    out = []
    if not soup:
        return out
    for li in soup.select("li.contents-flame"):
        nm = li.select_one(".product-name-area p")
        pr = li.select_one(".right-area .price")
        am = li.select_one(".right-area .amount-100g, .right-area [class*=amount-]")
        country = li.select_one(".product-country")
        if not (nm and pr):
            continue
        base_name = re.sub(r"\s+", " ", nm.get_text(strip=True))
        name = "デカフェ・ビヨンド " + base_name
        price = int(re.sub(r"[^\d]", "", pr.get_text()))
        wm = re.search(r"(\d+)\s*g", am.get_text()) if am else None
        weight = int(wm.group(1)) if wm else None
        origin = detect_country_name(country.get_text()) if country else None
        sold_out = bool(li.select(".soldout-button-area, .soldout-square, .soldout-back"))
        tasting = li.select_one(".tasting-contents")
        rec = build(name, price, weight, "decaf", DECAF_URL + "#" + requests.utils.quote(base_name), False,
                    tasting.get_text(strip=True) if tasting else None, sold_out, country_hint=origin)
        rec["decaf_process"] = None
        out.append(rec)
    return out


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        rec = build_from_page(url)
        time.sleep(CRAWL_DELAY_SECONDS)
        if rec:
            records.append(rec)
    time.sleep(CRAWL_DELAY_SECONDS)
    records.extend(build_from_decaf_page())
    return records


def main():
    records = scrape_all_products()
    with open("data_doicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_doicoffee.json に出力しました")


if __name__ == "__main__":
    main()
