# -*- coding: utf-8 -*-
"""
scrape_kobayashicoffeeyamanashi.py

小林コーヒー店(株式会社小林コーヒー店、山梨県甲斐市玉川179、公式 https://kobayashi-coffee-kofu.com/)の
Yahoo!ショッピングストア(store.shopping.yahoo.co.jp/kobayashi-coffee)の商品情報を取得する。
(既存の scrape_kobayashicoffee.py は北海道江別市の別店舗「豆工房 小林珈琲店」のため、
本スクリプトの slug は kobayashicoffeeyamanashi とした。)

【プラットフォーム】
他のYahoo!ショッピング店舗(scrape_saitaniya.py 等)と同様、店舗の商品一覧(/search.html、2ページ目以降は
?page=1,2,...)の Next.js `__NEXT_DATA__` JSON から商品名・価格・URLを取り、詳細ページの og:description と
schema.org availability で説明・在庫を取る。

【住所】
公式サイト https://kobayashi-coffee-kofu.com/menu.html のフッター「〒400-0116 山梨県甲斐市玉川179」で確認(2026-10)。

【対象商品】
実データ確認済み(2026-10時点、全36件): 商品名に「(200g)」を持つ焙煎豆(kc*/sp*コード)29件が対象。全商品が
200g単一サイズのため200gを代表とする。除外: ロイヤルギフトセット2種(gf*)、ギフトボックス(ot001/ot003)、
カリタ1杯用ドリッパー(ot002)、オリジナルドリップコーヒー(dp001/dp002、ドリップバッグ)。
Yahoo!店の価格は公式サイトの価格表より約10%高い(Yahoo!ショッピングの月額料等で9月に改定との注記あり)。
本データはYahoo!店の価格(オンライン購入できる価格)を採用する。
【数量限定】パナマゲイシャ(sp006)は「在庫なし」(販売休止の旨の記載あり)のため品切れとして収録する。
「フレンチ」「アイスコーヒー」は公式の価格表でブレンド欄に載っているためブレンドとして扱う。
焙煎度は説明文に「焙煎具合：浅煎り」等の記載がある商品のみ設定し、他は None。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "小林コーヒー店",
    "url": "https://kobayashi-coffee-kofu.com/",
    "platform": "Yahoo!ショッピング(店舗 kobayashi-coffee)",
    "address": "山梨県甲斐市玉川179",
    "prefecture": "山梨県",
    "robots_txt_status": "実質許可(Yahoo!ショッピング他店と同様、/search.html の page 指定は制限対象外)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/kobayashi-coffee"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"
}
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")

# コード -> (整形名, ブレンドか, 産地国)
NAMES = {
    "kc023": ("パプアニューギニア", False, "パプアニューギニア"),
    "kc004": ("ロイヤルブレンド", True, None),
    "sp008": ("グアテマラプレミアム", False, "グアテマラ"),
    "kc001": ("オリジナルブレンド", True, None),
    "kc005": ("カフェインレス グアテマラ", False, "グアテマラ"),
    "kc012": ("アイスコーヒー", True, None),
    "kc010": ("エンペラーロイヤルブレンド", True, None),
    "kc003": ("ハイブレンド", True, None),
    "kc015": ("グアテマラ", False, "グアテマラ"),
    "kc013": ("ブルーマウンテンブレンド", True, None),
    "kc006": ("スマトラマンデリン", False, "インドネシア"),
    "kc014": ("ジャワロブスタ", False, "インドネシア"),
    "kc017": ("モカマタリ", False, "イエメン"),
    "sp002": ("モカプレミアム", False, "エチオピア"),
    "kc002": ("マイルドブレンド", True, None),
    "kc019": ("エルサルバドル", False, "エルサルバドル"),
    "kc011": ("イタリアンブレンド", True, None),
    "kc020": ("コロンビアブレンド", True, None),
    "sp007": ("ブルーマウンテン ナンバー1", False, "ジャマイカ"),
    "kc021": ("アメリカンブレンド", True, None),
    "kc008": ("キリマンジェロブレンド", True, None),
    "kc009": ("モカブレンド", True, None),
    "kc016": ("フレンチ", True, None),
    "kc018": ("モカシダモ", False, "エチオピア"),
    "kc022": ("モカシダモ 浅煎り", False, "エチオピア"),
    "kc024": ("ブラジル 浅煎り", False, "ブラジル"),
    "sp003": ("コロンビアプレミアム", False, "コロンビア"),
    "sp004": ("ブラジルプレミアム", False, "ブラジル"),
    "sp006": ("パナマゲイシャ", False, "パナマ"),
}


def fetch_list_items() -> list[dict]:
    items: list[dict] = []
    for page in range(0, 20):
        url = f"{BASE_URL}/search.html" + (f"?page={page}" if page else "")
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
            data = json.loads(m.group(1))
            page_items = list(data["props"]["initialState"]["bff"]["searchResults"]["items"].values())[0][1]["content"]["items"]
        except Exception:
            break
        if not page_items:
            break
        items.extend(page_items)
    return items


def fetch_detail(url: str) -> dict:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
        return {"in_stock": True, "notes": None, "roast": None}
    text = resp.content.decode("utf-8", "replace")
    dm = re.search(r'og:description" content="([^"]*)"', text)
    notes = None
    roast = None
    if dm:
        desc = html.unescape(dm.group(1)).replace("<br>", "\n")
        lines = [l.strip().replace("　", " ") for l in desc.split("\n") if l.strip()]
        lines = [l for l in lines if not l.startswith("※")]
        joined = " ".join(lines)
        rm = re.search(r"焙煎具合[:：]\s*(\S+)", joined)
        if rm:
            roast = rm.group(1)
        else:
            rm = ROAST_PATTERN.search(joined)
            if rm:
                roast = rm.group(1)
        notes = re.sub(r"\s*焙煎具合[:：]\s*\S+", "", joined).strip()[:400] or None
    in_stock = "schema.org/OutOfStock" not in text and "schema.org/SoldOut" not in text and "schema.org/InStock" in text
    return {"in_stock": in_stock, "notes": notes, "roast": roast}


def build_record(stem: str, item: dict) -> dict:
    name, is_blend, origin = NAMES[stem]
    url = (item.get("url") or "").split("?")[0]
    detail = fetch_detail(url)

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name" if origin in name or name.startswith("モカ") else "description"
        parsed = apply_category_hint_fallback(parsed, name)

    out = not detail["in_stock"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": detail["roast"],
        "roast_hint": None,
        "flavor_notes": detail["notes"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": 200,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    items = fetch_list_items()
    print(f"[info] 一覧 {len(items)}件取得")
    records = []
    for it in items:
        url = (it.get("url") or "").split("?")[0]
        stem = url.rsplit("/", 1)[-1].replace(".html", "")
        if stem in NAMES and "200g" in (it.get("name") or "").replace("ｇ", "g"):
            records.append(build_record(stem, it))
    return records


def main():
    records = scrape_all_products()
    with open("data_kobayashicoffeeyamanashi.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kobayashicoffeeyamanashi.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_level"], r["stock_status"])


if __name__ == "__main__":
    main()
