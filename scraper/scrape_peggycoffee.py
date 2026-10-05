# -*- coding: utf-8 -*-
"""
scrape_peggycoffee.py

ペギー珈琲店(peggycoffee.cart.fc2.com、愛知県名古屋市千種区丘上町1丁目3)の商品情報を取得する。
FC2ショッピングカート。

【対象商品について】
実データ確認済み(2026-10時点): 全商品62件のうち、商品名が「銘柄名／200g」のように末尾に
重量(／NNNg)が付く焙煎豆(12銘柄のシングルオリジン+ブレンド3銘柄=15銘柄、各銘柄が100g/200g/
300g/500gの別商品として並ぶ)を対象とする。同一銘柄は最小重量の商品を代表として採用する
(多くは200g、ペルー・サンタロサとコロンビア・ファンマルティンは100g)。
除外: ギフトセット(オリジナルセレクト)、ドリップバッグ(DB〜)、水出しコーヒー(パック入り)、
ペーパーフィルター等の器具(商品名に「／NNNg」が無いためパターンで自動的に除外される)。

【ページ構造について】
一覧は「/?ca=all」にpar_page=100をPOSTして全62件を1ページに表示させる(既定は12件/ページ)。
商品は`div.item_list div.item`(div.name a=商品名・リンク、div.other b=価格、div.comment=説明)。
詳細ページには「焙煎[●●●○○]/中煎り」の焙煎度、【生産国】【農園】【精製】【品種】【風味】の
構造化行がある。バリエーション(select[name=variation])は挽き方のみ(価格同一)。
在庫はoptionのdata-stock="0"/data-submit="0"で判定(現状は全件販売中)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
    detect_processing_method,
)

SHOP_INFO = {
    "name": "ペギー珈琲店",
    "url": "https://peggycoffee.cart.fc2.com/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "愛知県名古屋市千種区丘上町1丁目3",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://peggycoffee.cart.fc2.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
BLEND_CATEGORIES = {"18", "19", "20", "14"}  # ペギー/メロー/アイスブレンドのcaと「ブレンドコーヒー」

NAME_PATTERN = re.compile(r"^(.+?)\s*[／/]\s*(\d+)\s*g$", re.I)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    sess = requests.Session()
    sess.headers.update(REQUEST_HEADERS)
    resp = sess.post(f"{BASE_URL}/?ca=all", data={"par_page": "100", "Submit_par": "設定"}, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    seen = set()
    for d in soup.select("div.item_list div.item"):
        a = d.select_one("div.name a")
        if not a:
            continue
        m = re.search(r"/ca(\d+)/(\d+)/", a["href"])
        if not m or m.group(2) in seen:
            continue
        seen.add(m.group(2))
        pr = d.select_one(".other b")
        pm = re.search(r"([\d,]+)\s*円", pr.get_text()) if pr else None
        items.append({
            "id": m.group(2),
            "ca": m.group(1),
            "name": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", a.get_text(" ", strip=True))),
            "price": int(pm.group(1).replace(",", "")) if pm else None,
        })
    return items


def parse_fields(text: str) -> dict:
    fields = {}
    for m in re.finditer(r"【\s*([^】]{1,12}?)\s*】\s*([^\n【]+)", text):
        key = re.sub(r"[\s　]+", "", m.group(1))
        fields.setdefault(key, m.group(2).strip())
    return fields


def build_record(item: dict, base: str, weight: int) -> dict | None:
    url = f"{BASE_URL}/ca{item['ca']}/{item['id']}/p-r-s/"
    html_text = fetch_html(url)
    soup = BeautifulSoup(html_text, "html.parser")
    variants = soup.select("select[name=variation] option")
    real = [o for o in variants if o.get("value") != "not_selected"]
    sold_out = bool(real) and all(o.get("data-stock") == "0" or o.get("data-submit") == "0" for o in real)

    for sc in soup(["script", "style"]):
        sc.decompose()
    text = (soup.select_one("div#contents") or soup.body).get_text("\n", strip=True)
    # 本文: 商品見出し(「銘柄／NNNg」2回目)の次行以降〜「価格：」の手前
    flat = text
    raw_name_orig = None  # NFKC前の表記(本文中の見出し行)
    for line in flat.split("\n"):
        if unicodedata.normalize("NFKC", line.strip()) == item["name"]:
            raw_name_orig = line.strip()
    if raw_name_orig:
        idx = flat.rfind(raw_name_orig)
        end = flat.find("価格：", idx)
        body = flat[idx + len(raw_name_orig):end] if end > idx else flat[idx:idx + 1500]
    else:
        body = flat[:1500]
    body_n = unicodedata.normalize("NFKC", body)

    roast = None
    rm = re.search(r"焙煎\[[●○]+\]\s*/\s*(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)", re.sub(r"\s+", "", body_n))
    if rm:
        roast = rm.group(1)

    fields = parse_fields(body_n)
    intro = [l.strip() for l in body.split("\n")]
    intro_lines = []
    for l in intro:
        if l.startswith("【") or l.startswith("＜"):
            break
        if re.match(r"^(焙煎［|●|○|］|＞)", l) or re.fullmatch(r"[●○]+", l) or l.startswith("※"):
            continue
        intro_lines.append(l)
    desc_parts = [" ".join(intro_lines)]
    if fields.get("風味"):
        desc_parts.append("風味: " + fields["風味"])
    desc = re.sub(r"\s+", " ", " ".join(p for p in desc_parts if p)).strip()[:400] or None

    is_blend = item["ca"] in BLEND_CATEGORIES or "ブレンド" in base
    parsed = parse_product(base)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        c = detect_country_name(fields.get("生産国") or "")
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "description"
        elif not parsed["origin_country"]:
            c = detect_country_name(base)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, base)

    if is_blend:
        processing = None
    elif fields.get("精製"):
        processing = normalize_processing_method(fields["精製"])
    else:
        processing = parsed["processing_method"] or detect_processing_method(base)

    record = {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": fields.get("農園"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }
    if "デカフェ" in base or "カフェインレス" in base:
        if re.search(r"マウンテンウォーター", body_n):
            record["decaf_process"] = "マウンテンウォータープロセスによりカフェインを除去"
        elif re.search(r"スイスウォーター", body_n):
            record["decaf_process"] = "スイスウォータープロセスによりカフェインを除去"
        elif re.search(r"液体二酸化炭素|液体CO2", body_n):
            record["decaf_process"] = "液体CO2抽出によりカフェインを除去"
    return record


def scrape_all_products() -> list[dict]:
    best: dict[str, tuple[int, dict, str]] = {}
    for item in list_items():
        m = NAME_PATTERN.match(item["name"])
        if not m or item["price"] is None:
            continue
        base = m.group(1).strip()
        weight = int(m.group(2))
        cur = best.get(base)
        if cur is None or weight < cur[0]:
            best[base] = (weight, item, base)

    records = []
    for weight, item, base in best.values():
        try:
            rec = build_record(item, base, weight)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_peggycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_peggycoffee.json に出力しました")


if __name__ == "__main__":
    main()
