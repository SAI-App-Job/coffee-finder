# -*- coding: utf-8 -*-
"""
aggregate_events.py

scrape_events_wcc.py / scrape_events_scaj.py / scrape_events_ace.py /
scrape_events_jcf.py が出力する data_events_wcc.json / data_events_scaj.json /
data_events_ace.json / data_events_jcf.json を統合し、/data/events.json
(EVENT_SOURCE + EVENT 相当)を更新する。

【4団体で出力フィールドが異なる理由】
WCCはstart_date/end_date、ACEはCOEオークション日+NW審査週間、SCAJはstart_date/
end_date+テーマ/主催者、JCFはstart_date/end_date+開催地(archiveLabel)と、
サイトごとに取得できる情報の形が異なる。本スクリプトはこれらをdata/events.json
の共通スキーマ(date_rangeという表示用の日本語文字列)へ変換する。
description(紹介文)は、調査済みの解説文のような創作は行わず、スクレイパーが
実際に取得した情報(優勝者・テーマ等)からのみ組み立てる。

【タイムスタンプの扱い】
aggregate_shops.pyと同様、内容に変化がなければlast_scraped_atも前回の値を
そのまま引き継ぎ、「変化がなければコミットしない」というワークフロー側の
挙動を壊さないようにする。
"""

import json
from datetime import datetime, timezone
from pathlib import Path

SCRAPER_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRAPER_DIR.parent / "data"

SOURCES = {
    "wcc": "data_events_wcc.json",
    "scaj": "data_events_scaj.json",
    "ace": "data_events_ace.json",
    "jcf": "data_events_jcf.json",
}


def load_source(source_id: str) -> dict:
    path = SCRAPER_DIR / SOURCES[source_id]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} が見つかりません({source_id}のスクレイパーが正常終了したか確認してください)"
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_existing() -> dict:
    path = DATA_DIR / "events.json"
    if not path.exists():
        return {"sources": [], "events": []}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def stabilize_timestamp(new_obj: dict, old_obj: dict | None, field: str) -> None:
    if not old_obj:
        return
    new_copy = {k: v for k, v in new_obj.items() if k != field}
    old_copy = {k: v for k, v in old_obj.items() if k != field}
    if new_copy == old_copy:
        new_obj[field] = old_obj.get(field)


def format_date_range(start_iso: str | None, end_iso: str | None) -> str | None:
    """ISO日付(YYYY-MM-DD)を、既存データの表記(例: 2026年6月25日〜27日)に近い
    日本語形式へ変換する。年・月をまたぐ場合はそれぞれ明示する。"""
    if not start_iso:
        return None
    sy, sm, sd = (int(x) for x in start_iso.split("-"))
    if not end_iso or end_iso == start_iso:
        return f"{sy}年{sm}月{sd}日"
    ey, em, ed = (int(x) for x in end_iso.split("-"))
    if (sy, sm) == (ey, em):
        return f"{sy}年{sm}月{sd}日〜{ed}日"
    if sy == ey:
        return f"{sy}年{sm}月{sd}日〜{em}月{ed}日"
    return f"{sy}年{sm}月{sd}日〜{ey}年{em}月{ed}日"


def build_event_id(source_id: str, name: str) -> str:
    return f"{source_id}:{name}"


def normalize_wcc(record: dict, source_id: str) -> dict:
    description = f"優勝: {record['champion']}" if record.get("champion") else None
    return {
        "id": build_event_id(source_id, record["name"]),
        "source_id": source_id,
        "name": record["name"],
        "event_type": record.get("event_type", "competition"),
        "host_country": None,
        "venue": record.get("venue"),
        "date_range": format_date_range(record.get("start_date"), record.get("end_date")),
        "related_country": None,
        "related_brand": None,
        "description": description,
        "source_url": record.get("source_url"),
    }


def normalize_scaj(record: dict, source_id: str) -> dict:
    date_range = record.get("date_range_raw") or format_date_range(
        record.get("start_date"), record.get("end_date")
    )
    description = record.get("theme")
    return {
        "id": build_event_id(source_id, record["name"]),
        "source_id": source_id,
        "name": record["name"],
        "event_type": record.get("event_type", "exhibition"),
        "host_country": "日本",
        "venue": record.get("venue"),
        "date_range": date_range,
        "related_country": "日本",
        "related_brand": None,
        "description": description,
        "source_url": record.get("source_url"),
    }


def normalize_ace(record: dict, source_id: str) -> dict:
    coe = record.get("coe_auction_date")
    nw_start = record.get("national_winner_start_date")
    nw_end = record.get("national_winner_end_date")

    parts = []
    if coe:
        _, m, d = (int(x) for x in coe.split("-"))
        parts.append(f"COE(オークション): {m}月{d}日")
    if nw_start:
        nw_range = format_date_range(nw_start, nw_end)
        # format_date_rangeは「Y年M月D日」形式を返すため、既存の表記(月日のみ)に
        # 合わせて先頭の年部分だけ取り除く
        if nw_range:
            nw_range = nw_range.split("年", 1)[-1]
        parts.append(f"NW(審査週間): {nw_range}")
    date_range = " / ".join(parts) if parts else None

    return {
        "id": build_event_id(source_id, record["name"]),
        "source_id": source_id,
        "name": record["name"],
        "event_type": record.get("event_type", "auction"),
        "host_country": record.get("related_country"),
        "venue": record.get("related_country"),
        "date_range": date_range,
        "related_country": record.get("related_country"),
        "related_brand": None,
        "description": None,
        "source_url": record.get("source_url"),
    }


def normalize_jcf(record: dict, source_id: str) -> dict:
    return {
        "id": build_event_id(source_id, record["name"]),
        "source_id": source_id,
        "name": record["name"],
        "event_type": record.get("event_type", "festival"),
        "host_country": "日本",
        "venue": record.get("venue"),
        "date_range": format_date_range(record.get("start_date"), record.get("end_date")),
        "related_country": "日本",
        "related_brand": None,
        "description": None,
        "source_url": record.get("source_url"),
    }


NORMALIZERS = {"wcc": normalize_wcc, "scaj": normalize_scaj, "ace": normalize_ace, "jcf": normalize_jcf}


def main():
    now_iso = datetime.now(timezone.utc).isoformat()
    existing = load_existing()
    existing_sources = {s["id"]: s for s in existing.get("sources", [])}

    sources = []
    events = []

    for source_id in SOURCES:
        source_data = load_source(source_id)
        info = source_data["event_source"]

        source_record = {
            "id": source_id,
            "name": info.get("name"),
            "url": info.get("url"),
            "robots_txt_status": info.get("robots_txt_status"),
            "update_cadence": info.get("update_cadence"),
            "last_scraped_at": now_iso,
        }
        stabilize_timestamp(source_record, existing_sources.get(source_id), "last_scraped_at")
        sources.append(source_record)

        normalize = NORMALIZERS[source_id]
        for record in source_data.get("events", []):
            event = normalize(record, source_id)
            events.append(event)

    DATA_DIR.mkdir(exist_ok=True)
    with (DATA_DIR / "events.json").open("w", encoding="utf-8") as f:
        json.dump({"sources": sources, "events": events}, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[done] sources={len(sources)}件, events={len(events)}件 を data/events.json に出力しました")


if __name__ == "__main__":
    main()
