# -*- coding: utf-8 -*-
"""
scrape_itsumocoffee.py

ITSUMO COFFEE(いつもコーヒー。北海道札幌市東区北36条東22丁目5-25、販売業者「自家焙煎倶楽部」、
カラーミーショップ 21000.shop-pro.jp)の自家焙煎コーヒー豆を取得する。

【対象】トップページのナビに載る商品のうち、ストレート豆・ブレンド・アイスコーヒーブレンドの
200g袋。同じブレンドの500g袋(別商品)は最小重量の200g袋を代表とするため除外。
ドリップバッグ・水出しコーヒー玉・各種セット・ギフト・器具・書籍は対象外。
「東ティモール・マウベシ農協」はトップページに「販売終了しました」とあるため除外。
「ボンジャルディン農園」は商品名に「※欠品※」とあり在庫0のため、品切れとして出力する。
【価格】オプション「挽き方」の先頭「1.豆のまま」の税込価格。
【文字コード】EUC-JP。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "ITSUMO COFFEE",
    "url": "https://21000.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道札幌市東区北36条東22丁目5-25",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ 21000.shop-pro.jp の商品一覧と各商品ページを2026-10-26に確認。"
                   "特定商取引法表記(販売業者 自家焙煎倶楽部、運営統括責任者 山石英市、札幌市東区北36条東22丁目5-25)。"
                   "公式サイト itsumo-coffee.com に「厳しい気候の北海道札幌で焙煎しています」、"
                   "「夏季休暇のご案内(26.8.1)」に「店舗及び通販業務をお休み」の記載、食べログに同住所で登録(定休 月・木)。"
                   "公式サイトのお知らせは2026-09-30(メール便料金改定)まで更新。サイト自身は「通販専門店」を名乗るため店頭購入の可否は要確認。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://21000.shop-pro.jp/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)
EXTRA_PIDS = ["18417550"]
SKIP_PIDS = {
    "178245994",  # 東ティモール・マウベシ農協: 販売終了(トップページ告知 26.8.1)
}
EXCLUDE_WORDS = ["セット", "ドリップバッグ", "水出し", "ギフト", "500g", "フィルター", "ポット",
                 "ドリッパー", "ノート", "物語", "ケトル"]
BEAN_HINTS = ["煎り", "ブレンド"]  # 商品名にこのいずれかを含み、かつ200gのものだけ採用
ROAST_RE = re.compile(r"(極深煎|中深煎|中浅煎|深煎|浅煎|中煎)")


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 404:
        return ""
    r.raise_for_status()
    html = r.content.decode("euc-jp", errors="replace")
    return html


def list_pids():
    """トップページのナビゲーション(全商品リンク)から商品IDを集める。

    このショップはカスタムテンプレートで、カテゴリページにも全商品のナビが並ぶため、
    トップページの一覧をそのまま候補とし、各商品ページ側の名称で絞り込む。
    (公開終了済みのIDは商品ページが404になるので取得対象から外れる)
    """
    html = fetch(BASE_URL)
    time.sleep(DELAY)
    pids = []
    for pid in re.findall(r"\?pid=(\d+)", html):
        if pid not in pids:
            pids.append(pid)
    # ナビに載っていない欠品中の商品(ブラジル・ボンジャルディン農園)も商品ページで品切れとして取得する
    for pid in EXTRA_PIDS:
        if pid not in pids:
            pids.append(pid)
    return pids


def norm(s):
    s = unicodedata.normalize("NFKC", s.replace("　", " "))
    return re.sub(r"\s+", " ", s).strip()


def get_desc(html, title):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l]
    try:
        i = lines.index("ツイート")
    except ValueError:
        return None
    seg = []
    for l in lines[i + 2:]:
        if l == "商品詳細":
            break
        seg.append(l)
    txt = " ".join(seg)
    txt = re.sub(r"【(産地紹介|香味紹介)】", "", txt)
    return txt.strip()[:300] or None


def build(pid):
    url = BASE_URL + "?pid=" + pid
    html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None  # 公開終了(404)
    p = json.loads(m.group(1))["product"]
    raw = norm(p["name"])
    if any(w in raw for w in EXCLUDE_WORDS):
        return None
    if not any(h in raw for h in BEAN_HINTS) or "200g" not in raw:
        return None
    out = False
    if "欠品" in raw:
        out = True
        raw = norm(raw.replace("※欠品※", ""))
    stock = p.get("stock_num")
    if isinstance(stock, int) and stock <= 0:
        out = True
    variants = p.get("variants") or []
    beans = [v for v in variants if (v.get("option1_value") or "").strip().startswith("1.豆のまま")] or variants
    price = beans[0]["option_price_including_tax"] if beans else p["sales_price_including_tax"]
    wm = re.search(r"(\d+)\s*g", raw, re.I)
    weight = int(wm.group(1)) if wm else None
    rm = ROAST_RE.search(raw)
    roast = (rm.group(1) + "り") if rm else None
    is_blend = "ブレンド" in raw
    parsed = parse_product(raw)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, raw)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": get_desc(html, raw),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def main():
    pids = [p for p in list_pids() if p not in SKIP_PIDS]
    print(f"[info] 候補 {len(pids)}件")
    records = []
    for pid in pids:
        time.sleep(DELAY)
        try:
            rec = build(pid)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {pid} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_itsumocoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_itsumocoffee.json に出力しました")


if __name__ == "__main__":
    main()
