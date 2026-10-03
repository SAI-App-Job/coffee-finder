# -*- coding: utf-8 -*-
"""
scrape_naminonecoffee.py

波の音珈琲(naminonecoffee.jimdofree.com、神奈川県横須賀市秋谷1-13-1。ご注文を受けてから
焙煎する自家焙煎所。珈琲豆は3種類のオリジナルブレンドのみ)の商品情報を取得する。
Jimdo製サイトの「珈琲豆」ページ(/珈琲豆/)に、見出し「3種類のブレンド珈琲たち」以下、
ブレンド名→説明→【参考：風味・香り】の順で並び、末尾に「各種ひと袋200g入りで、1500円(税込)」
と価格が書かれている。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。トップページの2026年9月28日付お知らせ「価格を見直しました。
各種ひと袋200gを1500円」に基づき現行価格として扱う。

【対象商品について】
実データ確認済み(2026-10時点): ブレンド3銘柄(秋谷ブレンド・立石から贈り物・西海岸通り物語)。
「お試しセット」(100g×3種)はセット商品のため除外。代表重量は表示されている200g
(1袋200g・1500円。購入数量によらず均一価格)。名称に「ブレンド」を含まない2銘柄も
店のページ上でブレンド珈琲と明記されているためカテゴリはブレンドとする。
焙煎度はページ冒頭の「シティーローストからフルシティーロースト」をroast_hintに保持する。
商品はすべて同一ページのため product_url は商品名の「#フラグメント」で一意化する。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

SHOP_INFO = {
    "name": "波の音珈琲",
    "url": "https://naminonecoffee.jimdofree.com/",
    "platform": "Jimdo(メール注文)",
    "address": "神奈川県横須賀市秋谷1-13-1",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "https://naminonecoffee.jimdofree.com/%E7%8F%88%E7%90%B2%E8%B1%86/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
PRICE_PATTERN = re.compile(r"(\d+)\s*[gｇ]入りで[、,]\s*([\d,]+)\s*円")
ROAST_HINT = "シティロースト〜フルシティロースト"
STOP_LINES = ("問い合わせ・注文ページへ", "商品価格・送料ページへ")


def fetch_lines() -> list[str]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    return [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]


def scrape_all_products() -> list[dict]:
    lines = fetch_lines()
    text = "\n".join(lines)
    price_m = PRICE_PATTERN.search(text)
    if not price_m:
        return []
    weight_g, price = int(price_m.group(1)), int(price_m.group(2).replace(",", ""))

    start = next(i for i, ln in enumerate(lines) if ln.startswith("3種類のブレンド珈琲"))
    end = next((i for i, ln in enumerate(lines) if i > start and ln.startswith("珈琲豆の価格については")), len(lines))
    # 各ブレンドは「名称→説明→【参考：風味・香り】→問い合わせ・注文ページへ→商品価格・送料ページへ」の並び。
    # 区切りの2行(STOP_LINES)で分割する。
    blocks: list[list[str]] = []
    cur: list[str] = []
    for ln in lines[start + 1:end]:
        if ln == STOP_LINES[0]:
            if cur:
                blocks.append(cur)
            cur = []
        elif ln == STOP_LINES[1]:
            continue
        else:
            cur.append(ln)
    # 見出し直後の導入文(ブレンド名の由来の総説)は商品説明ではないため先頭ブロックから除く
    if blocks and blocks[0][0].startswith("ブレンド珈琲豆各種"):
        blocks[0] = blocks[0][1:]
    records = []
    for b in blocks:
        name = b[0]
        desc = re.sub(r"\s+", " ", " ".join(b[1:])).strip() or None
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "ブレンド",
            "origin_country": None,
            "origin_source": None,
            "designated_brand": None,
            "processing_method": None,
            "grade": None,
            "roast_level": None,
            "roast_hint": ROAST_HINT,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": [],
            "blend_components": [],
            "price": price,
            "weight_g": weight_g,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{PAGE_URL}#{quote(name)}",  # 全商品が同一ページのため一意なフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_naminonecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_naminonecoffee.json に出力しました")


if __name__ == "__main__":
    main()
