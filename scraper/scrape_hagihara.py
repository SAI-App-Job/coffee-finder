# -*- coding: utf-8 -*-
"""
scrape_hagihara.py

萩原珈琲株式会社(shop.hagihara-coffee.com、〒657-0836 兵庫県神戸市灘区
城内通1-6-18、昭和39年創業の自家焙煎豆のオンライン販売)の商品情報を
取得する。独自構築(Vue.js製フロントエンド+独自JSON API)。本プロジェクトで
初めてのこのタイプの店舗。

robots.txt確認済み(2026-09時点): /robots.txtが存在せず(404)、制限なし。

【プラットフォーム識別について】
実データ確認済み: 商品一覧ページ(coffee_list.html等)はVue.js(js/vue.js)+
axios(js/axios.js)で構築されたSPAで、静的HTMLには商品への個別リンクが
存在しない。ページ内のインラインスクリプトを確認したところ、
`axios({method:"GET", url:"api/goods.json"+params})`という形で
`api/goods.json?goods_id=1,2,3,...`から商品データを取得しており、
商品詳細ページのリンクは`coffee_detail.html?id=<goods_id>`という
Vueテンプレート(`v-bind:href="'coffee_detail.html?id=' + item.id"`)で
生成されていることが判明した。認証不要でAPIに直接アクセス可能。

【商品一覧の取得方法について】
実データ確認済み: `api/goods.json`をパラメータなしで呼ぶと、goods_idを
指定した場合の絞り込み前の全140件(コーヒー豆・紅茶・ココア・ジュース・
ギフト・カリタ/ハリオ等の抽出器具を含む)が一括で返る。各商品は
`fcategory.title`(大分類)と`scategory.title`(小分類)を持ち、実データでは
fcategory="コーヒー豆"かつscategory in {"ストレート","ブレンド"}の37件
(ドリップバッグ珈琲・リキッドタイプは別のscategoryのため自動的に除外される)
が対象の焙煎豆商品。このカテゴリ条件で絞り込む。

【非コーヒー豆商品の除外について】
実データ確認済み: 上記の絞り込み後も「お試しセット」(cap="送料込"、複数
銘柄の詰め合わせサンプルで単一銘柄ではない)が1件混入するため
NON_BEAN_KEYWORDSで除外する。残り36件を対象とする。

【在庫状況について】
実データ確認済み: 全商品でstock_flag="0"。この値が「取り扱い中」を表す
規定値と判断し、"0"以外を欠品扱いとする(欠品商品の実例が見つからず
未検証だが、他フィールド(disp_flag="1"=表示中、del_flag="0"=削除されて
いない)と同様に「0」が正常値というこのAPIの命名慣習に合わせた)。
"""

import json
import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "萩原珈琲",
    "url": "https://www.hagihara-coffee.com/",
    "platform": "独自構築(Vue.js + 独自JSON API)",
    "address": "兵庫県神戸市灘区城内通1-6-18",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。/robots.txtが存在せず404、制限なし)",
}

API_URL = "https://shop.hagihara-coffee.com/api/goods.json"
DETAIL_URL_TEMPLATE = "https://shop.hagihara-coffee.com/coffee_detail.html?id={id}"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_FCATEGORY = "コーヒー豆"
TARGET_SCATEGORIES = {"ストレート", "ブレンド"}
NON_BEAN_KEYWORDS = ["お試しセット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇℊ]")


def fetch_all_goods() -> list[dict]:
    resp = requests.get(API_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def build_record(goods: dict) -> dict | None:
    title = (goods.get("goods_name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = DETAIL_URL_TEMPLATE.format(id=goods["id"])
    price_raw = goods.get("price")
    price = int(float(price_raw)) if price_raw not in (None, "") else None

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    structural_out_of_stock = str(goods.get("stock_flag")) != "0"
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_m = WEIGHT_PATTERN.search(goods.get("capacity_text") or "")
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_goods = fetch_all_goods()
    targets = [
        g for g in all_goods
        if (g.get("fcategory") or {}).get("title") == TARGET_FCATEGORY
        and (g.get("scategory") or {}).get("title") in TARGET_SCATEGORIES
        and g.get("disp_flag") == "1"
        and g.get("del_flag") == "0"
    ]

    records = []
    flavored_records = []
    for goods in targets:
        detail = build_record(goods)
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
    with open("data_hagihara.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hagihara.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
