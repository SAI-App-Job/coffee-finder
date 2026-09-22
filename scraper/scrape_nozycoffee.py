# -*- coding: utf-8 -*-
"""
scrape_nozycoffee.py

NOZY COFFEE(nozycoffee-onlinestore.com、東京都渋谷区神宮前5-17-13
[THE ROASTERY]、シングルオリジン専門の自家焙煎コーヒー豆販売)の商品情報を
取得する。カラーミーショップ(実際のショップアカウントはtheroastery.shop-pro.jp、
独自ドメインnozycoffee-onlinestore.comでエイリアス運用)。

【店舗発見の経緯】
高田馬場エリアの調査を機に開始した全国の未調査エリア洗い出しの一環で、渋谷
エリアを調査した際にtailoredcafe.jp/coffee-labo.co.jpの紹介記事経由で発見。
「THE ROASTERY」(渋谷区神宮前・原宿キャットストリート)・「BREWS」(天王洲)・
「flow」(京都市下京区)の3拠点を展開する著名なシングルオリジン専門店(2010年
三宿にて創業、運営会社: TYSONS & COMPANY)。本スクレイパーのSHOP_INFOは
創業由来の原宿THE ROASTERYの住所を代表値として採用し、他拠点はdata/shops.json
側で別途手動追加する想定(27 COFFEE ROASTERS等と同じ運用)。

【文字コード】EUC-JP(実データ確認済み、<meta charset>でcontent-type:
text/html; charset=euc-jp)。scrape_etop.pyと同じくresp.encodingを明示する。

【商品一覧の取得方法について】
実データ確認済み: カテゴリページ(?mode=cate&cbid=2602460&csid=0、BEANS)には
ランキングウィジェット(class="pull-left width--110"等、全ページ共通で
コーヒー豆以外の商品も含む)と実際のカテゴリ商品一覧(class="product-list__unit
product-list__unit-lg")の2種類のpidリンクが混在している。後者のみを対象とする
ことで、ドリップバッグ・ギフトボックス・定期便・グッズ等の非対象商品を除外できる
(NOZY COFFEEはBEANSカテゴリ自体を焙煎豆単品のみに限定して運用しているため、
カテゴリ商品一覧を使えばNON_BEAN_KEYWORDSによるタイトル除外は不要だった)。

【商品説明(div.product__explain)の構造について】
実データ確認済み: 基本は2〜3つの<hr>で区切られた構成。1セクション目は商品名
(英語/日本語)+ラベル付き仕様(Region/Farmer/Altitude/Variety/Processing/
Profile、英語ラベル+日本語併記)、2セクション目が日英両方のテイスティング文。
3セクション目(抽出方法動画への誘導リンク、定型文)は<hr>で区切られる場合と
区切られず2セクション目に直接続く場合の両方があった(例: Brazil/COQUEIROは
<hr>2個のみ)。誘導リンクは<div>でラップされているため、2セクション目の
走査中に<div>要素に到達した時点で打ち切ることで対応した。また、HTML内の
コメントノード(bs4のComment、Pythonのstr派生クラスのためisinstance(str)判定に
一致してしまう)を明示的に除外しないと、コメント文字列自体がflavor_notesに
混入することも実データで判明した。2セクション目の全文(日本語+英語段落)を
flavor_notesとして採用する。

【価格・重量について】
実データ確認済み: 全商品が「豆/粉」×「150g/450g」(商品により重量が異なる
場合あり)のバリアント構成で、option2_valueに「<重量>g/<価格>円」形式で
埋め込まれている。挽き方は「豆」を優先し、重量は最小のものを代表バリアントと
して採用する(405coffee.py等と同じ考え方)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup, Comment

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "NOZY COFFEE",
    "url": "https://nozy-coffee.jp/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメインnozycoffee-onlinestore.comで運用)",
    "address": "東京都渋谷区神宮前5-17-13",
    "prefecture": "東京都",
    "robots_txt_status": "未確認(scrape_etop.pyと同じカラーミーショップ標準構成を想定)",
}

BASE_URL = "https://nozycoffee-onlinestore.com"
CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2602460&csid=0"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
LABEL_PATTERN = re.compile(r"^(Region|Farmer|Altitude|Variety|Processing|Profile)\b")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def fetch_product_pids() -> list[str]:
    soup, _ = fetch(CATEGORY_URL)
    pids = []
    seen = set()
    for a in soup.select("li.product-list__unit-lg a[href*='pid=']"):
        m = re.search(r"pid=(\d+)", a.get("href", ""))
        if not m:
            continue
        pid = m.group(1)
        if pid not in seen:
            seen.add(pid)
            pids.append(pid)
    return pids


def parse_explain_sections(soup: BeautifulSoup) -> tuple[dict, str | None]:
    """div.product__explainを3つの<hr>で区切り、(ラベル辞書, テイスティング文)を返す。"""
    container = soup.select_one("div.product__explain")
    if not container:
        return {}, None

    sections = [[]]
    for child in container.children:
        if getattr(child, "name", None) == "hr":
            sections.append([])
            continue
        sections[-1].append(child)

    if len(sections) < 3:
        return {}, None

    labels = {}
    for el in sections[1]:
        if getattr(el, "name", None) == "strong":
            m = LABEL_PATTERN.match(el.get_text(strip=True))
            if not m:
                continue
            label = m.group(1)
            value_parts = []
            for sib in el.next_siblings:
                if getattr(sib, "name", None) in ("strong", "hr"):
                    break
                if getattr(sib, "name", None) == "br":
                    break
                value_parts.append(sib if isinstance(sib, str) else sib.get_text())
            labels[label] = "".join(value_parts).strip()

    # 実データ確認済み: 3セクション目(抽出方法動画への誘導)が<hr>で区切られず
    # 直接続くケースがある(例: Brazil/COQUEIRO)。<div>(誘導ボタンのラッパー)に
    # 到達した時点で打ち切り、HTMLコメントノード(bs4.Comment、isinstance(str)に
    # 一致してしまうため明示的に除外)も飛ばす。
    flavor_lines = []
    for el in sections[2]:
        if isinstance(el, Comment):
            continue
        if getattr(el, "name", None) == "div":
            break
        if isinstance(el, str):
            text = el.strip()
        elif getattr(el, "name", None) == "br":
            continue
        else:
            text = el.get_text(strip=True)
        if text:
            flavor_lines.append(text)
    flavor_notes = "\n".join(flavor_lines) if flavor_lines else None

    return labels, flavor_notes


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    bean_variants = [v for v in variants if v.get("option1_value") == "豆"] or variants
    def weight_of(v):
        m = WEIGHT_PATTERN.search(v.get("option2_value") or "")
        return int(m.group(1)) if m else float("inf")
    if not bean_variants:
        return None
    return min(bean_variants, key=weight_of)


def build_record(pid: str) -> dict | None:
    soup, raw_html = fetch(f"{BASE_URL}/?pid={pid}")
    m = COLORME_JSON_PATTERN.search(raw_html)
    if not m:
        return None
    data = json.loads(m.group(1))["product"]
    title = data.get("name", "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    product_url = f"{BASE_URL}/?pid={pid}"

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": data.get("sales_price"),
            "product_url": product_url,
        }

    labels, flavor_notes = parse_explain_sections(soup)

    origin_note = labels.get("Region")
    if origin_note:
        detected = detect_country_name(origin_note) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("Processing")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("Variety")
    farm_note = labels.get("Farmer")
    if labels.get("Altitude"):
        farm_note = f"{farm_note}(標高{labels['Altitude']})" if farm_note else f"標高{labels['Altitude']}"

    variant = pick_canonical_variant(data.get("variants", []))
    price = variant.get("option_price") if variant else data.get("sales_price")
    weight_m = WEIGHT_PATTERN.search((variant or {}).get("option2_value") or "")
    weight_g = int(weight_m.group(1)) if weight_m else None

    structural_out_of_stock = isinstance(data.get("stock_num"), int) and data["stock_num"] <= 0
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "variety": variety,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    pids = fetch_product_pids()

    records = []
    flavored_records = []
    for pid in pids:
        # 一覧ページ取得のみでは価格変化を判定できないため(詳細ページを開かないと
        # variants情報が取れない)、常に詳細ページを取得する。5件程度の小規模
        # ショップのため負荷は軽微。
        record = build_record(pid)
        if record is None:
            continue
        if record.get("is_flavored"):
            flavored_records.append(record)
        else:
            records.append(record)

    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_nozycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nozycoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
