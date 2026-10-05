# -*- coding: utf-8 -*-
"""
scrape_rondovel.py

自家焙煎珈琲ロンドベル(rondovel.cart.fc2.com、愛知県名古屋市西区万代町2-55-2 ハートイン万代1A)の
商品情報を取得する。FC2ショッピングカート。

【対象商品について】
実データ確認済み(2026-10時点): 全件表示137件(「?ca=all」をpar_page=100のPOSTで表示件数を
広げると100件/1ページになり、2ページ目以降は「?ca=all&page=N」で28件ずつ。本スクリプトは
カテゴリ別・全件表示・トップの各ページを巡回してid(商品番号)で重複排除する)のうち、
次を対象とする。
  - 豆のカテゴリ: ☆カフェインレス(ca13)・♡フルーティテイスト(ca62)・♠ビター(苦み強)(ca64)・
    ♠ビター(ほろ苦)(ca65)・♢マイルドテイスト(ca63)・♧クリアーテイスト(ca61)・★ストレートコーヒー(ca66)
    の商品のうち、商品名が「【2P】」のもの(同じ銘柄の2パックセットで、重量違いの別商品)は
    最小重量の方を代表とするため除外。
  - ca46(セット/SALE/グッズ)のうち単品の豆: ハミングバード 250g(338)・ディープストライカー 250g(491)・
    【超特価】コーヒーの日記念ブレンド(664)・リ・ネートルブレンド【2P】(466、単品版が無く500g
    =250g×2パックで販売)。他の「3種set/2種set」「福袋」「入門セット」「喫茶まいるーむ」等のセット類、
    トートバッグ等のグッズは除外。
  - ca56(水出しアイス)のうち、紙パック詰め無しの豆・粉の「ショット・サマー」(566、水出し用の
    やや深めロースト豆)。紙パック入りの「みずでっぽー」等の水出しアイス商品、ca57のドリップバッグ類は除外。
  - ca66のコピルアック(53、100%ピュア/70%/35%ブレンドのバリエーション。100%ピュアを代表とする)。

【重量・価格について】
商品ごとにバリエーション(select[name=variation]のoption)があり、「1,700円 ★M 豆のまま」
「950円 ☆S 豆のまま」のように価格とパック種別(S/M)が入る。パック種別の炒り上がり重量は
説明文の「Sパック＝炒り上がり約122g」「Mパック＝炒り上がり約245g」等から読み取る(Sは約122〜125g、
Mは約240〜250g)。最小重量(多くはSパック)のバリエーションの価格・在庫を代表とする。
Sパックが無い商品(Mのみ)はMを採用。option属性のdata-stock="0"(「[完売しました]」表示)は品切れ。
バリエーションが無い商品は一覧/詳細の価格表示と「完売しました」表示で判定する。

【焙煎度について】
焙煎度は商品ごとに固定とは限らず、一部の商品は注文時に選択式(例: やや深炒りP/中炒りA/やや浅炒りB)。
説明文中の最初の焙煎度表現(「深煎りビター」「中炒り」等)をroast_hintに記録し、roast_levelは
タイトル/説明文に明確な単一の記述がある場合のみ設定する。炒→煎に統一して記録する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "自家焙煎珈琲ロンドベル",
    "url": "https://rondovel.cart.fc2.com/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "愛知県名古屋市西区万代町2-55-2 ハートイン万代1A",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://rondovel.cart.fc2.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
LIST_CATEGORIES = ["13", "61", "62", "63", "64", "65", "66", "46", "56"]
BEAN_CATEGORIES = {"13", "61", "62", "63", "64", "65", "66"}
EXTRA_IDS = {"338", "491", "664", "466", "566", "53"}
MAX_PAGES = 10

ROAST_PATTERN = re.compile(r"(やや浅|中浅|やや深|中深|浅|中|深)[煎炒]り")
PACK_DEF_PATTERN = re.compile(r"([SM])パック\s*[=＝]\s*炒り上がり(?:約)?\s*(\d+)")
N_PACK_PATTERN = re.compile(r"([☆★]\s*N\d+)[^。]*?炒り上がり|生豆(\d+)gを焙煎します。煎り上がりは約(\d+)g")


def fetch_html(url: str, session: requests.Session | None = None) -> str:
    resp = (session or requests).get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_items() -> dict[str, dict]:
    items: dict[str, dict] = {}

    def add(html_text: str) -> int:
        soup = BeautifulSoup(html_text, "html.parser")
        count = 0
        for li in soup.select("li.item_inner"):
            a = li.select_one("dt.name a")
            if not a:
                continue
            m = re.search(r"/ca(\d+)/(\d+)/", a["href"])
            if not m:
                continue
            count += 1
            iid = m.group(2)
            if iid not in items:
                items[iid] = {"id": iid, "ca": m.group(1), "cas": set(),
                              "name": re.sub(r"\s+", " ", a.get_text(" ", strip=True))}
            items[iid]["cas"].add(m.group(1))
        return count

    # 全件表示を100件/ページで取得(par_pageの設定はセッションに保持される)
    sess = requests.Session()
    sess.headers.update(REQUEST_HEADERS)
    resp = sess.post(f"{BASE_URL}/?ca=all", data={"par_page": "100", "Submit_par": "設定"}, timeout=30)
    resp.encoding = "utf-8"
    add(resp.text)
    for ca in LIST_CATEGORIES + [""]:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/?ca={ca}&page={page}" if ca else f"{BASE_URL}/?page={page}"
            if add(fetch_html(url)) == 0:
                break
    # ca=allの2ページ目以降(par_page=28の既定表示)
    for page in range(1, MAX_PAGES + 1):
        if add(fetch_html(f"{BASE_URL}/?ca=all&page={page}")) == 0:
            break
    return items


def is_target(item: dict) -> bool:
    if item["id"] in EXTRA_IDS:
        return True
    # 同じ商品が複数カテゴリ(味のグループ+ストレート等)に載るため、所属カテゴリ集合で判定する
    if item["cas"] & BEAN_CATEGORIES and "2P】" not in item["name"]:
        return True
    return False


def parse_price(text: str | None) -> int | None:
    m = re.search(r"([\d,]+)\s*円", text or "")
    return int(m.group(1).replace(",", "")) if m else None


def parse_variants(soup: BeautifulSoup) -> list[dict]:
    out = []
    for opt in soup.select("select[name=variation] option"):
        if opt.get("value") == "not_selected":
            continue
        label = re.sub(r"\s+", " ", opt.get_text(" ", strip=True))
        price = parse_price(opt.get("data-price_replace")) or parse_price(label)
        sold = opt.get("data-stock") == "0" or opt.get("data-submit") == "0" or "完売" in label
        pack = re.search(r"[☆★]+\s*([SM]|N\d+)(?![A-Za-z])", label)
        out.append({"label": label, "price": price, "sold_out": sold, "pack": pack.group(1) if pack else None})
    return out


def pack_weights(text: str) -> dict[str, int]:
    weights: dict[str, int] = {}
    flat = re.sub(r"(?<=\d)\s+(?=\d)", "", unicodedata.normalize("NFKC", text))
    for pack, g in PACK_DEF_PATTERN.findall(flat):
        weights.setdefault(pack, int(g))
    # 「☆ N300 … 煎り上がりは約245g」形式
    for m in re.finditer(r"[☆★]\s*(N\d+)\s*】?\s*生豆\d+gを焙煎します。?\s*煎り上がりは約\s*(\d+)\s*g", flat):
        weights.setdefault(m.group(1), int(m.group(2)))
    return weights


def first_weight(text: str) -> int | None:
    flat = re.sub(r"(?<=\d)\s+(?=\d)", "", unicodedata.normalize("NFKC", text))
    m = re.search(r"(?:炒り上がり|煎り上がり|炒りあがり)(?:約)?\s*(\d+)(?:[〜~]\d+)?\s*g", flat)
    return int(m.group(1)) if m else None


def clean_description(text: str, name: str) -> str | None:
    lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or s in ("S_America", "pigeon"):
            continue
        if s == name or re.search(r"^テイスト表内|パック\s*＝|生豆\d+gを焙煎|炒り上がり|煎り上がり|^g$|^\d+\s*g$|2Pセット|こちらもチェック|^→→|^（まずはお試し", s):
            continue
        lines.append(s)
    cleaned = re.sub(r"\s+", " ", " ".join(lines)).strip()
    return cleaned[:400] or None


def build_record(item: dict) -> dict | None:
    url = f"{BASE_URL}/ca{item['ca']}/{item['id']}/p-r-s/"
    html_text = fetch_html(url)
    soup = BeautifulSoup(html_text, "html.parser")
    variants = parse_variants(soup)

    for sc in soup(["script", "style"]):
        sc.decompose()
    body = soup.select_one("div.item_detail") or soup.select_one("div#contents") or soup.body
    text = body.get_text("\n", strip=True)
    start = text.find(item["name"])
    end = text.find("価格：")
    desc_text = text[start + len(item["name"]):end] if start >= 0 and end > start else text
    name = item["name"]
    title = re.sub(r"\s*【(?:2P|S)】", "", name).strip()
    title = re.sub(r"\s+", " ", title)

    # 重量・価格・在庫(最小重量のバリエーションを代表とする)
    weights = pack_weights(desc_text)
    price = None
    weight_g = None
    sold_out = False
    chosen_label = None
    if variants:
        groups: dict[str | None, list[dict]] = {}
        for v in variants:
            groups.setdefault(v["pack"], []).append(v)
        # 100%ピュア等、パック種別がなくラベルで分かれるもの(コピルアック等)は先頭グループ=先頭バリエーション
        def group_weight(key):
            if key is None:
                return first_weight(desc_text)
            return weights.get(key)
        candidates = [(group_weight(k), k, vs) for k, vs in groups.items()]
        known = [c for c in candidates if c[0] is not None]
        if known:
            weight_g, key, vs = min(known, key=lambda c: c[0])
        else:
            weight_g, key, vs = None, candidates[0][1], candidates[0][2]
        if key is None and len(groups) == 1:
            # パック種別なし: ラベルは焙煎度/挽き方の選択肢。コピルアックのみ先頭(100%ピュア)を代表とする
            if item["id"] == "53":
                vs = [v for v in vs if "100%ピュア" in v["label"]]
        priced = [v for v in vs if v["price"] is not None]
        if priced:
            rep_price = min(v["price"] for v in priced)
            price = rep_price
            sold_out = all(v["sold_out"] for v in vs)
        chosen_label = vs[0]["label"] if vs else None
    else:
        price_el = soup.select_one(".price") or soup.select_one(".item_price")
        price = parse_price(text[end:end + 40]) if end > 0 else None
        weight_g = first_weight(desc_text)
        sold_out = "完売しました" in text[end:end + 80] if end > 0 else False
        # SALE表示(ハミングバード等)は「セール価格：」の値を採用
        sm = re.search(r"セール価格：\s*([\d,]+)\s*円", text)
        if sm:
            price = int(sm.group(1).replace(",", ""))

    # 「ハミングバード 250g」のように商品名に重量が入る場合
    nm = re.search(r"(\d+)\s*g\b", unicodedata.normalize("NFKC", title))
    if nm and weight_g is None:
        weight_g = int(nm.group(1))
    if nm:
        weight_g = int(nm.group(1))
        title = re.sub(r"\s*\d+\s*g\b", "", unicodedata.normalize("NFKC", title)).strip()
    if item["id"] == "466":
        weight_g = 500  # 約250g×2パック
    if item["id"] == "664":
        title = "コーヒーの日記念ブレンド"

    # 分類・産地
    is_straight = "66" in item["cas"]
    parsed = parse_product(title)
    flat_desc = unicodedata.normalize("NFKC", desc_text)
    if is_straight:
        parsed["category"] = "ストレート"
        if item["id"] == "53":
            parsed["origin_country"] = "インドネシア"
            parsed["origin_source"] = "product_description"
        elif not parsed["origin_country"]:
            m = re.search(r"生豆生産国\)?\s*([^\s].*?)(?:\n|$)", desc_text)
            c = detect_country_name(m.group(1)) if m else None
            c = c or detect_country_name(desc_text)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, title)
        processing = parsed["processing_method"] or detect_processing_method(desc_text)
    else:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
        processing = None

    # 焙煎度
    roast = None
    hint = None
    rm = ROAST_PATTERN.search(unicodedata.normalize("NFKC", desc_text).replace("炒", "煎"))
    if rm:
        hint = rm.group(0)
    selectable = any(re.search(r"[A-C]／|おすすめ）", v["label"]) for v in variants)
    if selectable:
        for v in variants:
            rm2 = re.search(r"おすすめ）\s*([^／\s]+)", v["label"])
            if rm2:
                hint = "おすすめ: " + re.sub(r"[A-Z]$", "", rm2.group(1)).replace("炒", "煎")
                break

    record = {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": hint,
        "flavor_notes": clean_description(desc_text, name),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }
    if re.search(r"カフェインレス|デカフェ", title) and re.search(r"液体二酸化炭素|液体CO2", flat_desc):
        record["decaf_process"] = "液体CO2抽出によりカフェインを除去"
    if selectable:
        record["roast_selectable"] = True
    return record


def scrape_all_products() -> list[dict]:
    records = []
    for item in collect_items().values():
        if not is_target(item):
            continue
        try:
            rec = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_rondovel.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_rondovel.json に出力しました")


if __name__ == "__main__":
    main()
