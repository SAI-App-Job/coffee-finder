# -*- coding: utf-8 -*-
"""
scrape_redclover.py

三軒茶屋珈琲 red-clover(レッドクローバー、東京都世田谷区太子堂1-15-11、公式 https://sanchacoffee.com/)の
カラーミーショップ(旧 redcoffee.shop-pro.jp → 独自ドメイン sanchacoffee.com に転送)の商品情報を取得する。

【販売先の採用理由】
同店は楽天市場店(www.rakuten.co.jp/sancha-redclover/)も出店しているが、カラーミー(公式サイト兼ECは
sanchacoffee.com)は焙煎豆の品目が最も揃っている(ブレンド約58、ストレート約50、デカフェ4。2026-10-25時点)ため
カラーミーを採用し、楽天は重複させない。

【対象商品について】
カテゴリ「ハワイ」「アメリカ合衆国」「ブレンド」「焙煎豆｜中南米・カリブ」「焙煎豆｜アフリカ・中東」「焙煎豆｜アジア・大洋州」
「カフェインレスコーヒー（デカフェ）焙煎豆」の商品を、一覧(?mode=cate&cbid=...&page=N)から集める。
除外: ドリップパック各カテゴリ、生豆各カテゴリ(10kg/軽量)、セット。
商品ごとのバリエーション(`Colorme.product.variants`)は「100g/200g/300g(×豆のまま/挽く)」と
「ドリップパック(粉のみ)」。豆のまま・最小重量(100g)の税込価格を採用する(挽くとドリップパックは使わない)。
在庫: inventory_control が "none" の商品は在庫管理なし=販売中。"option" の商品は採用バリエーションの
stock_num が 0 なら完売(ページに SOLD OUT 表示。2018〜2021年産などの旧ロットが完売のまま掲載されている)。
同名のブレンドが2ページある場合(「口づけが止まらない」「ドライマティーニ」。ドリップパック8枚の選択肢が加わった再掲)は
先に出現した(古い)ページのみを採用する。
焙煎度はタイトルの（中煎り）等の呼称を roast_hint にする。価格は税込(8%)。

【robots.txt】
User-agent: * は /secure/ と /cart/ のみ制限(2026-10-25確認。sanchacoffee.com / redcoffee.shop-pro.jp とも同内容)。
識別UA・間隔2秒で取得する。ページはEUC-JP。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "三軒茶屋珈琲 red-clover",
    "url": "https://sanchacoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "東京都世田谷区太子堂1-15-11",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-25確認。User-agent: *は/secure/と/cart/のみ制限)",
    "source_note": "カラーミーショップ(https://sanchacoffee.com/)のカテゴリ・商品ページを2026-10-25に確認。同店の楽天市場店"
                   "(https://www.rakuten.co.jp/sancha-redclover/)は品目が少ないため不採用で重複させない。"
                   "店主紹介に『焙煎→消費者販売までの工程の一切を一貫して自社で行ってます』、実店舗は世田谷区太子堂1-15-11(三軒茶屋駅南口徒歩3分)",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://sanchacoffee.com/"
CATEGORY_IDS = [
    "2951604",  # ハワイ
    "3000210",  # アメリカ合衆国
    "2866768",  # ブレンド
    "1123130",  # 焙煎豆｜中南米・カリブ
    "1128005",  # 焙煎豆｜アフリカ・中東
    "1801201",  # 焙煎豆｜アジア・大洋州
    "2773411",  # カフェインレスコーヒー(デカフェ)焙煎豆
]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 2
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
ROAST_PATTERN = re.compile(r"[（(【]([^（()）【】]*煎り)[）)】]")
# coffee_parser の国名辞書で拾えない産地表記の補完
ORIGIN_OVERRIDES = {"アメリカ合衆国": "アメリカ", "マラウィ": "マラウイ", "コートジボワール": "コートジボワール"}
ROAST_HINT_MAP = {"中・浅煎り": "中浅煎り", "中・深煎り": "中深煎り", "極・深煎り": "極深煎り"}


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("euc-jp", "replace")


def collect_pids() -> list[str]:
    pids: list[str] = []
    for cid in CATEGORY_IDS:
        page = 1
        while page <= 10:
            url = f"{BASE_URL}?mode=cate&cbid={cid}&csid=0" + (f"&page={page}" if page > 1 else "")
            try:
                html_text = fetch_page(url)
            except requests.RequestException as e:
                print(f"[warn] 一覧取得失敗: {url} ({e})")
                break
            for pid in re.findall(r"\?pid=(\d+)", html_text):
                if pid not in pids:
                    pids.append(pid)
            time.sleep(CRAWL_DELAY_SECONDS)
            if f"page={page + 1}" in html_text:
                page += 1
            else:
                break
    return pids


def clean_name(raw: str) -> str:
    name = unicodedata.normalize("NFKC", raw)
    name = name.replace("｜", " ").replace("|", " ")
    name = name.replace("【焙煎豆】", " ").replace("【 焙煎豆】", " ").replace("焙煎豆", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def pick_variant(variants: list[dict]) -> tuple | None:
    """豆のまま・最小重量(gのみ。ドリップパック等は除く)のバリエーションを返す。"""
    best = None  # (重量, バリエーション)
    for v in variants:
        w = re.fullmatch(r"(\d+)\s*g", unicodedata.normalize("NFKC", v.get("option1_value") or ""))
        if not w or not (v.get("option2_value") or "").startswith("豆"):
            continue
        weight = int(w.group(1))
        if best is None or weight < best[0]:
            best = (weight, v)
    return best


def build_record(pid: str) -> dict | None:
    url = f"{BASE_URL}?pid={pid}"
    html_text = fetch_page(url)
    m = COLORME_JSON_PATTERN.search(html_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = (product.get("name") or "").strip()
    is_bean = "焙煎豆" in title or title.startswith("ブレンド【") or "カフェインレス" in title
    if not is_bean or "生豆" in title or "セット" in title or "ドリップパック" in title:
        return None
    picked = pick_variant(product.get("variants") or [])
    if not picked:
        return None
    weight, variant = picked

    price = variant.get("option_price_including_tax")
    if data.get("inventory_control") == "none":
        out = False
    else:
        out = (variant.get("stock_num") or 0) <= 0
    name = clean_name(title)
    is_blend = title.startswith("ブレンド【")

    roast_m = ROAST_PATTERN.search(unicodedata.normalize("NFKC", title))
    # NFKC後は「・」「煎り」はそのまま
    roast_hint = None
    if roast_m:
        r = roast_m.group(1)
        roast_hint = ROAST_HINT_MAP.get(r, r)

    soup = BeautifulSoup(html_text, "html.parser")
    exp = soup.select_one("div.product-order-exp")
    desc = re.sub(r"\s+", " ", exp.get_text(" ", strip=True)).strip() if exp else None
    if not desc:
        og = soup.select_one('meta[property="og:description"]')
        desc = og.get("content") if og else None
    desc = desc[:400] if desc else None

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name[:20])
        if not parsed["origin_country"]:
            for kw, country in ORIGIN_OVERRIDES.items():
                if kw in name:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records, seen = [], set()
    for pid in collect_pids():
        try:
            rec = build_record(pid)
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        finally:
            time.sleep(CRAWL_DELAY_SECONDS)
        if rec is None or rec["raw_name"] in seen:
            continue
        seen.add(rec["raw_name"])
        records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_redclover.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_redclover.json に出力しました")
    for r in records:
        print(" ", r["raw_name"][:60], "|", r["category"], r["origin_country"], r["roast_hint"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
