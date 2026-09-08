# -*- coding: utf-8 -*-
"""
scrape_cogito.py

漕人 cogito(cogito-web.com、滋賀県高島市鴨1318-2、自家焙煎豆のオンライン
販売)の商品情報を取得する。カラーミーショップ(shop-pro.jp、
cogito.shop-pro.jp)。

自家焙煎確認済み: cogito-web.com/detail/?id=coffee ページに「コーヒー豆を
焙煎します」の記述あり。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【「色指数」表記について】
実データ確認済み: 焙煎度合いを「浅煎り」等の言葉ではなく「色指数XX」
(アグトロン値を模した独自の焙煎度数値)で表記する店舗方針。
coffee_parserの一般的な焙煎度キーワードには一致しないため roast_level は
Noneのままとなるが、raw_nameに数値表記自体は保持されるため情報は失われ
ない。

【非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml掲載の全42件): 以下が非対象。
  - 「水出しコーヒー（○○ 80g/90g 色指数XX）」11件: 商品詳細ページの
    説明文で「1パックに深煎り80gから中煎り90gほど入っています」
    「容器に入れて水出しする」用の抽出済みパック商品と確認(液体の
    完成品ではないが、粉砕済み・個包装された専用商品のため他店の
    「水出しアイスコーヒーパック」除外方針に合わせて対象外とする)
  - 「漕人オリジナルドリップバッグ」「ドリップバッグ詰め合わせ30P
    （ギフト用）」「ドリップバッグ詰め合わせ20P（ギフト用）」3件:
    ドリップバッグ(単品/ギフトセット)
  - 「江東堂 生地缶 長型 300g」「江東堂 生地缶 平型 200g」2件: 豆保存用の
    キャニスター(缶)で、コーヒー豆そのものではない
  - 「デーツ」「ブラックレーズン」「グリーンレーズン」「ピスタチオ」
    (いずれも天日干しドライフルーツ・ナッツ)、「金時いもチップス」
    「紫いもチップス」「黄金いも（笹切り）」「金時いもチップス・うす塩味」
    「紅はるかチップス」「じゃがチップス」(国産手揚げ芋チップス各種)、
    「パスタスナック・るんるんしお味」「麩市 地がらし」の計12件: コーヒーと
    無関係な食品・菓子類
残り13件(いずれも焙煎豆の単品・ブレンド、100g or 80g)を対象とする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "漕人 cogito",
    "url": "https://cogito-web.com/",
    "platform": "カラーミーショップ",
    "address": "滋賀県高島市鴨1318-2",
    "prefecture": "滋賀県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://cogito.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "水出しコーヒー", "ドリップバッグ", "生地缶",
    "デーツ", "レーズン", "ピスタチオ",
    "金時いも", "紫いも", "黄金いも", "紅はるか", "じゃがチップス",
    "パスタスナック", "麩市",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ㎏]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    script_text = ""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "var Colorme" in text:
            script_text = text
            break

    m = COLORME_PATTERN.search(script_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
    title = re.sub(r"\s+", " ", title)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax") or product.get("sales_price")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(price) if price is not None else None,
            "product_url": product_url,
        }

    structural_out_of_stock = product.get("stock_num") == 0
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = None
    if weight_m:
        weight_g = int(weight_m.group(1)) * 1000 if "㎏" in weight_m.group(0) else int(weight_m.group(1))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = build_record(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_cogito.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cogito.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
