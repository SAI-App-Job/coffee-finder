# -*- coding: utf-8 -*-
"""
scrape_maillot.py

マイヨ工房(Atelier Maillot、珈琲焙煎 マイヨ工房。山梨県甲府市大里町1891-3、
https://www.ateliermaillot.com/)の商品情報を取得する。Jimdo(標準のショップモジュール)。

【住所】
公式サイトの「店舗情報」ページ(/店舗情報/)に「〒400-0053 山梨県甲府市大里町1891-3」と記載(2026-10確認)。

【robots.txt】
/app/・/j/はDisallowだが商品ページ自体は問題なし。Crawl-Delay: 5が指定されているため、
リクエスト間隔を5秒確保する(カテゴリ約40ページで約3分半かかる)。

【ページ構造】
国別カテゴリ(/オンラインショップ-1/<国名>/)とマイヨーブレンド・パルプドナチュラル珈琲の各ページに、
1ページ複数商品(`div.j-product`)が載る。商品名は `h4.fn`、説明は `div.description` の段落、
容量・挽き違いは `select.j-product__variants` の option(content=ラベル、data-params=JSON:
price/availability[1=購入可・2=残りわずか・3=在庫切れ])。weightFormatted は実際の容量と
一致しないため使わず、ラベルの「NNNg」を重量とする。
代表は最小重量(多くは200g)の「豆のまま」(無ければ挽き)の価格。最小重量の選択肢のうち1つでも
在庫切れでなければ販売中とする。ラベルに重量が無い商品(ブルーマウンテンNo.1「標準」、
ハワイ・コナ「High/Cityロースト」)は重量不明のため weight_g=None。

【焙煎度】
国別の豆は購入時に「焙煎おまかせ」で(コメント欄で変更可)注文する方式のため、roast_level は None、
商品説明の「推奨ロースト：City Roast(中深煎り)」を roast_hint・roast_selectable=True とする。
マイヨーブレンドは「ロースト : City(中煎り)」で固定のため roast_level に採用する。

【対象・除外】
実データ確認済み(2026-10時点)。対象: 国別カテゴリ、マイヨーブレンド、パルプドナチュラル珈琲の
焙煎豆。除外: ドリップバッグ、コーヒーのお茶(カスカラ)、ハンドドリップツール、「価格別」ページ
(複数銘柄の価格帯のくくりで商品ではない)。商品説明に「終売」「在庫終了」とある商品は販売終了のため
収録しない。別ページに同名商品が重複掲載されている場合は1件に統合する。
更新状況: 最新のお知らせ(ブログ)は2023/10/29と古いが、商品ページには「2026年分 入荷しました」
(ブラジル さくらブルボン)等があり、2026年も在庫更新されている。
"""

import json
import re
import time
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "マイヨ工房",
    "url": "https://www.ateliermaillot.com/オンラインショップ-1/",
    "platform": "Jimdo",
    "address": "山梨県甲府市大里町1891-3",
    "prefecture": "山梨県",
    "robots_txt_status": "実質許可(2026-10確認。/app/・/j/はDisallow、商品ページは対象外。Crawl-Delay: 5を遵守)",
}

SITE = "https://www.ateliermaillot.com/"
SHOP_PATH = "オンラインショップ-1/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY = 5

# カテゴリ(パス) -> 産地国 (None は国を商品名から判定、ブレンドは別扱い)
COUNTRY_PAGES = {
    "ブラジル": "ブラジル", "コロンビア": "コロンビア", "インドネシア": "インドネシア", "ペルー": "ペルー",
    "エチオピア": "エチオピア", "タンザニア": "タンザニア", "グァテマラ": "グアテマラ", "イエメン": "イエメン",
    "メキシコ": "メキシコ", "ケニア": "ケニア", "ラオス": "ラオス", "中国": "中国", "ジャマイカ": "ジャマイカ",
    "キューバ": "キューバ", "コスタリカ": "コスタリカ", "パプアニューギニア": "パプアニューギニア",
    "パナマ": "パナマ", "ニカラグア": "ニカラグア", "東ティモール": "東ティモール", "ブルンジ": "ブルンジ",
    "インド": "インド", "ドミニカ": "ドミニカ共和国", "エルサルバドル": "エルサルバドル", "ルワンダ": "ルワンダ",
    "ザンビア": "ザンビア", "コンゴ": "コンゴ民主共和国", "ウガンダ": "ウガンダ", "ベトナム": "ベトナム",
    "アメリカ": "アメリカ(ハワイ)", "ホンジュラス": "ホンジュラス", "エクアドル": "エクアドル", "タイ": "タイ",
    "ミャンマー-1": "ミャンマー", "ハイチ-1": "ハイチ", "マラウィ": "マラウィ",
}
BLEND_PAGE = "マイヨーブレンド"
HONEY_PAGE = "パルプドナチュラル珈琲"  # 国別ではない(商品名から国判定)

ROAST_WORDS = r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)"
ENG_ROAST = [("Full\\s*City", "深煎り"), ("City", "中深煎り"), ("High", "中煎り")]
WEIGHT_RE = re.compile(r"(\d+)\s*g")
DISCONTINUED_RE = re.compile(r"終売|在庫終了|販売終了")


def fetch_page(path: str) -> BeautifulSoup | None:
    url = SITE + urllib.parse.quote(path)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"[warn] {path}: HTTP {resp.status_code}")
        return None
    return BeautifulSoup(resp.text, "html.parser")


def norm_name(name: str) -> str:
    n = unicodedata.normalize("NFKC", name)
    n = re.sub(r"[\s　]+", "", n).replace("ァ", "ア")
    return n


def clean_name(name: str) -> str:
    n = unicodedata.normalize("NFKC", name)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def roast_from_text(text: str) -> str | None:
    m = re.search(ROAST_WORDS, text)
    if m:
        return m.group(1)
    best = None
    for pat, word in ENG_ROAST:
        mm = re.search(pat, text, re.I)
        if mm and (best is None or mm.start() < best[0]):
            best = (mm.start(), word)
    return best[1] if best else None


def parse_variants(card) -> list[dict]:
    out = []
    for o in card.select("select option"):
        raw = o.get("data-params")
        if not raw:
            continue
        try:
            p = json.loads(raw)
        except json.JSONDecodeError:
            continue
        label = o.get("content") or o.get_text(strip=True)
        m = WEIGHT_RE.search(unicodedata.normalize("NFKC", label))
        out.append({
            "label": label,
            "price": int(p["price"]) if p.get("price") is not None else None,
            "avail": p.get("availability"),
            "weight": int(m.group(1)) if m else None,
            "ground": "挽き" in label,
        })
    return out


def pick_representative(variants: list[dict]) -> tuple[dict | None, bool]:
    """最小重量の豆のまま選択肢を代表に。(代表, 販売中か)"""
    if not variants:
        return None, False
    weighted = [v for v in variants if v["weight"] is not None]
    if weighted:
        min_w = min(v["weight"] for v in weighted)
        group = [v for v in weighted if v["weight"] == min_w]
    else:
        group = variants
    beans = [v for v in group if not v["ground"]]
    rep = (beans or group)[0]
    in_stock = any(v["avail"] != 3 for v in group)
    return rep, in_stock


def extract_processing(desc_paras: list[str], blob: str) -> str | None:
    """「精選方法：○○」等の短い項目値だけを正規化して採用する(文中の言及は拾わない)。"""
    m = re.search(r"(?:精選方法|精製方法|精製|工程)[:：]?\s*([^/]{1,20})(?:/|$)", blob)
    if m:
        found = detect_processing_method(m.group(1))
        if found:
            return found
    return None


def build_record(card, page_path: str, origin_hint: str | None, is_blend: bool) -> dict | None:
    title_el = card.select_one("h4.fn")
    if not title_el:
        return None
    name = clean_name(title_el.get_text(" ", strip=True))
    desc_el = card.select_one("div.description")
    paras = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in desc_el.select("p")] if desc_el else []
    paras = [p for p in paras if p]
    blob = " / ".join(paras)
    if DISCONTINUED_RE.search(blob):
        return None

    variants = parse_variants(card)
    rep, in_stock = pick_representative(variants)
    if not rep or rep["price"] is None:
        return None

    short_el = card.select_one(".cc-shop-product-short-desc")
    short = short_el.get_text(" ", strip=True) if short_el else ""

    # 焙煎度
    roast_level = None
    roast_hint = None
    if is_blend:
        m = re.search(r"ロースト\s*[:：]\s*[^(（]*[(（]([^)）]*)[)）]", blob)
        roast_level = roast_from_text(m.group(1)) if m else roast_from_text(blob)
    else:
        rec_para = next((p for p in paras if "推奨ロースト" in p), "")
        roast_hint = roast_from_text(rec_para) or roast_from_text(short)

    # 風味・説明(推奨ロースト行は除く)
    note_parts = [p for p in paras if not p.startswith("推奨ロースト") and not re.match(r"^(再入荷|在庫)", p)]
    notes = " ".join(note_parts)[:400] or None

    parsed = parse_product(name)
    country = origin_hint or detect_country_name(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "raw_name" if detect_country_name(name) else "category"
        parsed = apply_category_hint_fallback(parsed, name)

    processing = None if is_blend else (extract_processing(paras, blob) or parsed["processing_method"])

    url = SITE + urllib.parse.quote(page_path) + "#" + urllib.parse.quote(name)
    record = {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": rep["price"],
        "weight_g": rep["weight"],
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }
    if not is_blend and roast_hint:
        record["roast_selectable"] = True
    if "カフェインレス" in name or "デカフェ" in name:
        if "スイス" in blob and "ウォーター" in blob:
            record["decaf_process"] = "スイスウォータープロセスによりカフェインを除去"
    return record


def scrape_all_products() -> list[dict]:
    pages = [(BLEND_PAGE, None, True), (HONEY_PAGE, None, False)]
    pages += [(p, c, False) for p, c in COUNTRY_PAGES.items()]
    records: list[dict] = []
    seen: set[str] = set()
    dropped = 0
    for i, (page, origin, is_blend) in enumerate(pages):
        if i:
            time.sleep(CRAWL_DELAY)
        path = SHOP_PATH + page + "/"
        soup = fetch_page(path)
        if soup is None:
            continue
        cards = soup.select("div.j-product")
        for card in cards:
            rec = build_record(card, path, origin, is_blend)
            if rec is None:
                dropped += 1
                continue
            key = norm_name(rec["raw_name"])
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            records.append(rec)
        print(f"[info] {page}: {len(cards)}件中 累計{len(records)}件", flush=True)
    print(f"[info] 除外(終売・重複等): {dropped}件")
    return records


def main():
    records = scrape_all_products()
    with open("data_maillot.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_maillot.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["processing_method"], r["price"], r["weight_g"],
              r["roast_level"], r["roast_hint"], r["stock_status"])


if __name__ == "__main__":
    main()
