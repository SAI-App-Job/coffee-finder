// data/shops.json の各店舗(単一拠点店舗はトップレベル、複数拠点店舗は
// locations[])と、scraper/manual/shops/*.json の各店舗を、Nominatim(OpenStreetMapの
// ジオコーディングAPI)で緯度経度に変換し、それぞれのファイルにlat/lngとして書き戻す
// 一回限りのバッチスクリプト。アプリ実行時(エンドユーザーのブラウザ)からは一切呼び出さない
// ―― Nominatimの利用ポリシー(https://operations.osmfoundation.org/policies/nominatim/)は
// 大量の即時リクエストや正体不明なUser-Agentでのアクセスを禁じており、
// 「ビルド時に一度だけジオコーディングし、結果を静的データとしてキャッシュする」運用が
// 推奨されているため。1リクエスト/秒のレート制限を守り、有効なUser-Agentを付与する。
//
// 【単一拠点店舗のトップレベルlat/lngについて】
// 以前はshop.locations(複数拠点店舗のみ)しか対象にしておらず、単一拠点店舗
// (全店舗の大半)は一度もジオコーディングされていなかった。aggregate_shops.py側も
// このスクリプトが書き込んだ値を次回の再集約時に引き継ぐよう修正済み(merge_shop
// 参照)。
//
// 実行方法: node scripts/geocode-shops.js
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOPS_PATH = path.join(__dirname, "..", "data", "shops.json");
const MANUAL_SHOPS_DIR = path.join(__dirname, "..", "scraper", "manual", "shops");
const USER_AGENT = "CoffeeFinderApp/1.0 (https://github.com/SAI-App-Job/coffee-finder; personal hobby project)";
const REQUEST_INTERVAL_MS = 1100;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// 住所文字列から段階的に候補を生成する。ビル名・階数などNominatimが認識しにくい
// 補足情報を削り、最終的には丁目・番地レベルまで粗くした候補も試す。
// (架空の情報を作るのではなく、実際の住所文字列の一部を段階的に使うだけ)
function addressCandidates(address) {
  if (!address) return [];
  const candidates = [address];

  // 末尾の建物名・階数(例:「シャポー船橋南館内1階」「GREEN TERRACE表参道B1F」)を除去し、
  // 番地の数字列で終わる形に切り詰める
  const trimmedToBanchi = address.match(/^.*?\d+(?:丁目)?[-－]\d+(?:[-－]\d+)?/);
  if (trimmedToBanchi && trimmedToBanchi[0] !== address) {
    candidates.push(trimmedToBanchi[0]);
  }

  // さらに粗く、丁目までに切り詰める(番地レベルがOSMに存在しない場合のフォールバック)
  const trimmedToChome = address.match(/^.*?\d+丁目/);
  if (trimmedToChome) {
    candidates.push(trimmedToChome[0]);
  }

  // 最後の手段として、最初の数字より前(町名までの部分)だけを候補にする
  const wardOnly = address.match(/^[^\d]+/);
  if (wardOnly && wardOnly[0].trim() && wardOnly[0].trim() !== address) {
    candidates.push(wardOnly[0].trim());
  }

  // さらに粗く、市区町村レベルまで切り詰める(「字」を含む農村部の大字・
  // 小字名はOSMに存在しないことが多く、上記のwardOnlyでも解決できない
  // 場合がある。最終手段として市区町村の代表座標に丸める)
  const cityOnly = address.match(/^.+?[市区町村]/);
  if (cityOnly && cityOnly[0] !== address) {
    candidates.push(cityOnly[0]);
  }

  return [...new Set(candidates)];
}

async function geocode(query) {
  const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=jp&q=${encodeURIComponent(query)}`;
  const res = await fetch(url, {
    headers: { "User-Agent": USER_AGENT, "Accept-Language": "ja" },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const results = await res.json();
  if (!Array.isArray(results) || results.length === 0) return null;
  const [{ lat, lon }] = results;
  return {
    lat: Math.round(parseFloat(lat) * 1e6) / 1e6,
    lng: Math.round(parseFloat(lon) * 1e6) / 1e6,
  };
}

// address(段階的に粗くした候補を含む)→mapQueryの順に試す共通ヘルパー。
// 見つかった時点で打ち切り、都度レート制限のsleepを挟む。
async function geocodeWithFallback(logLabel, address, mapQuery) {
  const candidates = [...new Set([...addressCandidates(address), mapQuery].filter(Boolean))];
  if (candidates.length === 0) {
    console.log(`SKIP(no address/map_query): ${logLabel}`);
    return null;
  }
  for (const query of candidates) {
    process.stdout.write(`Geocoding: ${logLabel} / "${query}" ... `);
    try {
      const result = await geocode(query);
      await sleep(REQUEST_INTERVAL_MS);
      if (result) {
        console.log(`OK (${result.lat}, ${result.lng})`);
        return result;
      }
      console.log("NOT FOUND");
    } catch (err) {
      console.log(`ERROR: ${err.message}`);
      await sleep(REQUEST_INTERVAL_MS);
    }
  }
  return null;
}

async function geocodeShopsJson() {
  const shops = JSON.parse(fs.readFileSync(SHOPS_PATH, "utf8"));
  let geocodedCount = 0;
  let skippedCount = 0;
  let notFoundCount = 0;

  for (const shop of shops) {
    if (Array.isArray(shop.locations) && shop.locations.length > 0) {
      // 複数拠点店舗: 拠点ごとにlocations[].lat/lngを埋める
      for (const loc of shop.locations) {
        if (typeof loc.lat === "number" && typeof loc.lng === "number") {
          skippedCount++;
          continue;
        }
        const result = await geocodeWithFallback(`${shop.name} / ${loc.label ?? "(single)"}`, loc.address, loc.map_query);
        if (result) {
          loc.lat = result.lat;
          loc.lng = result.lng;
          geocodedCount++;
        } else {
          notFoundCount++;
        }
      }
      // 単一拠点店舗もトップレベルから代表座標を参照できるよう複製しておく
      // (先頭拠点の座標を代表値とする。aggregate_shops.py側もこの方針に合わせている)
      shop.lat = shop.locations[0].lat ?? null;
      shop.lng = shop.locations[0].lng ?? null;
    } else {
      // 単一拠点店舗: トップレベルのlat/lngを直接埋める
      if (typeof shop.lat === "number" && typeof shop.lng === "number") {
        skippedCount++;
        continue;
      }
      const result = await geocodeWithFallback(shop.name, shop.address, shop.map_query);
      if (result) {
        shop.lat = result.lat;
        shop.lng = result.lng;
        geocodedCount++;
      } else {
        notFoundCount++;
      }
    }
  }

  fs.writeFileSync(SHOPS_PATH, JSON.stringify(shops, null, 2) + "\n", "utf8");
  console.log(
    `\n[shops.json] geocoded=${geocodedCount} skipped(cached)=${skippedCount} not_found=${notFoundCount}\nWrote ${SHOPS_PATH}`
  );
}

async function geocodeManualShops() {
  if (!fs.existsSync(MANUAL_SHOPS_DIR)) return;
  const files = fs.readdirSync(MANUAL_SHOPS_DIR).filter((f) => f.endsWith(".json"));
  let geocodedCount = 0;
  let skippedCount = 0;
  let notFoundCount = 0;

  for (const file of files) {
    const filePath = path.join(MANUAL_SHOPS_DIR, file);
    const data = JSON.parse(fs.readFileSync(filePath, "utf8"));
    const shop = data.shop;
    if (!shop) continue;
    if (typeof shop.lat === "number" && typeof shop.lng === "number") {
      skippedCount++;
      continue;
    }
    const result = await geocodeWithFallback(shop.name, shop.address, shop.google_maps_query);
    if (result) {
      shop.lat = result.lat;
      shop.lng = result.lng;
      geocodedCount++;
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + "\n", "utf8");
    } else {
      notFoundCount++;
    }
  }

  console.log(
    `\n[manual/shops] geocoded=${geocodedCount} skipped(cached)=${skippedCount} not_found=${notFoundCount}`
  );
}

async function main() {
  await geocodeShopsJson();
  await geocodeManualShops();
  console.log("\nDone.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
