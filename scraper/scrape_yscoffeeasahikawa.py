# -*- coding: utf-8 -*-
"""
scrape_yscoffeeasahikawa.py

Y'sコーヒー(ワイズコーヒー。北海道旭川市西神楽北1条3丁目230-39の西神楽工場直売店ほか、
カラーミーショップ ys-coffee.com / ys-coffee.shop-pro.jp)の自家焙煎コーヒー豆を取得する。
(兵庫県の別店「Y's coffee roaster & baked shop」= scrape_yscoffee.py とは無関係)

【対象】オンラインショップの商品のうち、同一の銘柄/ブレンドの豆を1袋または同一袋を複数袋で売る商品を
ENTRIES に列挙した22商品。このショップは「100g×3袋 全国送料無料」「100g×2袋」のように複数袋単位の
販売が中心で、1袋単位のバリエーションが存在しない商品が多い。そのため複数袋のものは販売単位の合計重量
(100g×3袋=300g)と税込価格をそのまま採用する(単価換算はしない)。
【除外】3種類セット・組み合わせ自由・おまかせ厳選セット・500g×6袋/3kgの事業者向けセット・ドリップパック・ギフト・
音楽家シリーズ(80g×5袋ギフト)・紅茶・「スペシャルティコーヒー200g」(中身が複数銘柄の選択式で銘柄が特定できない)・
「高級豆をアイスで楽しむ100g×3袋」(産地・構成が不明)。
【価格】商品の税込価格(豆/挽きで同額)。
【在庫】Colorme 商品情報の stock_num が 0 の商品は品切れ。
【焙煎度】商品名・説明文に1種類だけ明記されているものだけ入れ、焙煎度をバリエーションで選ばせる商品は
roast_level=None・roast_hint に選択肢を書く。
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
    "name": "Y'sコーヒー",
    "url": "https://ys-coffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道旭川市西神楽北1条3丁目230-39",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-10-26確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミーショップ ys-coffee.com(独自ドメイン)の商品一覧と各商品ページを2026-10-26に確認。"
                   "特定商取引法表記(販売業者 ワイズコーヒー、運営統括責任者 佐々木康子、旭川市西神楽北1条3丁目230-39、TEL 070-8955-5151)。"
                   "ショップ紹介ページに「西神楽店は毎週水曜日日曜日、新店舗10条通店は毎週金曜日11時オープン」、"
                   "営業日ページに「水曜日 西神楽店【旭川市西神楽北一条三丁目230の39】11時~16時」、"
                   "トップに「焙煎三日目の一番美味しい珈琲を出荷」「西神楽工場直売店」の記載。旭川市のふるさと納税返礼品ページにも"
                   "「ワイズコーヒー西神楽焙煎工場直送」とある。十条通店は旭川市十条通22丁目2-15(2026-10-26時点の調査メモ)。"
                   "複数袋単位の商品は合計重量・税込価格で出力。ショップ内の新商品(Sidra等)は2025~2026年に追加されている。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://ys-coffee.com/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
DELAY = 2.0
COLORME_RE = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.S)

# pid: (raw_name, weight_g, origin_country または None, 焙煎度 または None, 焙煎度の選択肢 または None, ブレンドか)
ENTRIES = {
    "192048312": ("Sidra 100g", 100, "エクアドル", None, None, False),
    "192792695": ("イパネマ レッドフルーツ 100g", 100, "ブラジル", None, None, False),
    "193961926": ("イパネマ ラズベリー 100g×2袋", 200, "ブラジル", None, "中煎り/深煎りから選択", False),
    "174511410": ("ゲイシャ 100g×2袋", 200, None, "中煎り", None, False),
    "188609930": ("オレンジショコラ 中深煎 200g", 200, "ブラジル", "中深煎り", None, False),
    "164123979": ("限定トラジャ ランテカルア 100g×3袋", 300, "インドネシア", "シティロースト", None, False),
    "181277273": ("ヒロ福地プロデュース BLUE blend 200g", 200, None, None, None, True),
    "149185957": ("ヒロ福地プロデュース H&CO 200g×2袋", 400, None, None, None, True),
    "178293922": ("2025 ヒロ福地 クリスマスブレンド 200g", 200, None, None, None, True),
    "189242482": ("ブルーマウンテンNo.1ブレンド", None, None, None, None, True),
    "187418960": ("バレルエイジド 中深煎 80g", 80, None, "中深煎り", None, False),
    "191562776": ("ラム酒バレルエイジド 80g", 80, None, None, None, False),
    "181072712": ("ブラジル No.2 100g×3袋", 300, "ブラジル", None, "中煎り/深煎りから選択", False),
    "146841457": ("マンデリン 100g×3袋", 300, "インドネシア", None, "中煎り/深煎りから選択", False),
    "146841938": ("コロンビア 100g×3袋", 300, "コロンビア", None, "浅煎り(ミディアム)/中煎り(シティ)/深煎り(フレンチ)から選択", False),
    "146842170": ("キリマンジャロ 100g×3袋", 300, "タンザニア", None, "中煎り/深煎りから選択", False),
    "146846754": ("グァテマラ 100g×3袋", 300, "グアテマラ", None, "浅煎り/深煎りから選択", False),
    "146846969": ("モカ 100g×3袋", 300, "エチオピア", None, "中煎り/深煎りから選択", False),
    "140339032": ("プレミアムブレンド 100g×3袋", 300, None, "フレンチロースト", None, True),
    "140339230": ("スペシャルブレンド 100g×3袋", 300, None, "ミディアムロースト", None, True),
    "152798896": ("スイスウォーター社カフェインレス 100g×3袋", 300, None, None, None, False),
    "189337829": ("ブルンジ レッドブルボン 深煎 100g×3袋", 300, "ブルンジ", "深煎り", None, False),
}


def fetch(url):
    # 500番台は回避せず、間隔を空けて最大2回だけ再試行する
    for attempt in range(3):
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code < 500 or attempt == 2:
            break
        time.sleep(20)
    r.raise_for_status()
    return r.content.decode("euc-jp", errors="replace")


def norm(s):
    s = unicodedata.normalize("NFKC", s.replace("　", " "))
    return re.sub(r"\s+", " ", s).strip()


def get_desc(html):
    """「ホーム > カテゴリ > ▼ 商品名」の後ろから「■オプションの値段詳細」までを説明文とする。"""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l]
    idx = [i for i, l in enumerate(lines) if l == "＞"]
    if not idx:
        return None
    i = idx[-1] + 2  # カテゴリ名の次
    if i < len(lines) and lines[i].startswith("▼"):
        i += 2 if lines[i] == "▼" else 1
    seg = []
    for l in lines[i:]:
        if l.startswith("■オプション") or l in ("・", "買い物を続ける"):
            break
        seg.append(l)
    txt = " ".join(seg)
    txt = re.sub("[\U00010000-\U0010ffff☀-➿️​]", "", txt)  # 絵文字・ゼロ幅文字を除く
    txt = re.sub(r"[#*]+", "", txt)
    txt = re.sub(r"^\s*商品名 \S+ (商品の特徴 |--- )?", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    txt = re.sub(r"^商品の特徴 ", "", txt)
    return txt[:300] or None


def build(pid, entry):
    raw, weight, origin, roast, hint, is_blend = entry
    url = BASE_URL + "?pid=" + pid
    html = fetch(url)
    m = COLORME_RE.search(html)
    if not m:
        return None
    p = json.loads(m.group(1))["product"]
    price = p["sales_price_including_tax"]
    stock = p.get("stock_num")
    out = isinstance(stock, int) and stock <= 0
    parsed = parse_product(raw)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if origin and not parsed["origin_country"]:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "manual"
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
        "roast_hint": hint,
        "flavor_notes": get_desc(html),
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
    print(f"[info] 対象 {len(ENTRIES)}件")
    records = []
    for pid, entry in ENTRIES.items():
        time.sleep(DELAY)
        try:
            rec = build(pid, entry)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {pid} ({e})")
            continue
        if rec:
            records.append(rec)
    with open("data_yscoffeeasahikawa.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yscoffeeasahikawa.json に出力しました")


if __name__ == "__main__":
    main()
