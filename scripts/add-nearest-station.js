// data/shops.json の各店舗(単一拠点店舗はトップレベルlat/lng、複数拠点店舗は
// locations[0]の代表座標)と、scraper/manual/shops/*.json の各店舗について、
// HeartRails Express API(http://express.heartrails.com/api/json?method=getStations)
// で最寄り駅を求め、nearest_station({name, lines, distance_m, walk_min})として
// 書き戻す一回限りのバッチスクリプト。geocode-shops.jsと同じく、lat/lngが
// 既に分かっている店舗のみを対象にする(座標が無い店舗は先にgeocode-shops.jsを
// 実行する必要がある)。
//
// 【代表座標のみを対象にする理由】
// 既存のlat/lng(近い順ソートが参照する代表座標。複数拠点店舗は先頭拠点を採用)と
// 同じ方針で、nearest_stationもトップレベルの代表値のみを持たせる。拠点ごとの
// 最寄り駅が必要になった場合はlocations[]側に個別追加する形で拡張できる。
//
// 【distanceの単位について】
// 実データ確認済み(2026-09): HeartRails Express APIのdistanceは常に
// "<数値>m"形式(例: "50m", "780m")。km表記は確認されていないが、念のため
// 正規表現にマッチしない場合はその駅候補を除外する。
//
// 【エリアを絞った段階的な適用について】
// ユーザーの指示により、高田馬場・早稲田エリア→渋谷エリア→京都エリアの順に
// 段階適用する。--only=店舗名1,店舗名2 で対象店舗を絞り込める(未指定時は
// lat/lngがありnearest_stationが未設定の全店舗が対象になる)。
//
// 実行方法: node scripts/add-nearest-station.js --only="早苗,焙煎工場さかいち"
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOPS_PATH = path.join(__dirname, "..", "data", "shops.json");
const MANUAL_SHOPS_DIR = path.join(__dirname, "..", "scraper", "manual", "shops");
const REQUEST_INTERVAL_MS = 400;
const WALK_METERS_PER_MIN = 80;

const onlyArg = process.argv.find((a) => a.startsWith("--only="));
const onlyNames = onlyArg ? new Set(onlyArg.slice("--only=".length).split(",").map((s) => s.trim())) : null;
const forceArg = process.argv.includes("--force");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchNearestStation(lat, lng) {
  const url = `http://express.heartrails.com/api/json?method=getStations&x=${lng}&y=${lat}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const stations = data?.response?.station;
  if (!Array.isArray(stations) || stations.length === 0) return null;

  const groups = new Map();
  for (const st of stations) {
    const m = /^(\d+)m$/.exec(st.distance || "");
    if (!m) continue;
    const distanceM = parseInt(m[1], 10);
    if (!groups.has(st.name)) groups.set(st.name, { name: st.name, lines: [], minDistanceM: Infinity });
    const g = groups.get(st.name);
    if (!g.lines.includes(st.line)) g.lines.push(st.line);
    if (distanceM < g.minDistanceM) g.minDistanceM = distanceM;
  }
  if (groups.size === 0) return null;

  const nearest = [...groups.values()].sort((a, b) => a.minDistanceM - b.minDistanceM)[0];
  return {
    name: nearest.name,
    lines: nearest.lines,
    distance_m: nearest.minDistanceM,
    walk_min: Math.max(1, Math.round(nearest.minDistanceM / WALK_METERS_PER_MIN)),
  };
}

async function resolveWithRetry(logLabel, lat, lng) {
  process.stdout.write(`Looking up station: ${logLabel} (${lat}, ${lng}) ... `);
  try {
    const result = await fetchNearestStation(lat, lng);
    await sleep(REQUEST_INTERVAL_MS);
    if (result) {
      console.log(`OK ${result.name}(${result.lines.join("/")}) ${result.distance_m}m/徒歩${result.walk_min}分`);
      return result;
    }
    console.log("NOT FOUND");
    return null;
  } catch (err) {
    console.log(`ERROR: ${err.message}`);
    await sleep(REQUEST_INTERVAL_MS);
    return null;
  }
}

function hasCoords(obj) {
  return typeof obj?.lat === "number" && typeof obj?.lng === "number";
}

async function processShopsJson() {
  const shops = JSON.parse(fs.readFileSync(SHOPS_PATH, "utf8"));
  let updated = 0, skipped = 0, notFound = 0, outOfScope = 0;

  for (const shop of shops) {
    if (onlyNames && !onlyNames.has(shop.name)) {
      outOfScope++;
      continue;
    }
    if (!forceArg && shop.nearest_station) {
      skipped++;
      continue;
    }
    if (!hasCoords(shop)) {
      console.log(`SKIP(no lat/lng): ${shop.name}`);
      skipped++;
      continue;
    }
    const result = await resolveWithRetry(shop.name, shop.lat, shop.lng);
    if (result) {
      shop.nearest_station = result;
      updated++;
    } else {
      notFound++;
    }
  }

  fs.writeFileSync(SHOPS_PATH, JSON.stringify(shops, null, 2) + "\n", "utf8");
  console.log(
    `\n[shops.json] updated=${updated} skipped=${skipped} not_found=${notFound} out_of_scope=${outOfScope}\nWrote ${SHOPS_PATH}`
  );
}

async function processManualShops() {
  if (!fs.existsSync(MANUAL_SHOPS_DIR)) return;
  const files = fs.readdirSync(MANUAL_SHOPS_DIR).filter((f) => f.endsWith(".json"));
  let updated = 0, skipped = 0, notFound = 0, outOfScope = 0;

  for (const file of files) {
    const filePath = path.join(MANUAL_SHOPS_DIR, file);
    const data = JSON.parse(fs.readFileSync(filePath, "utf8"));
    const shop = data.shop;
    if (!shop) continue;
    if (onlyNames && !onlyNames.has(shop.name)) {
      outOfScope++;
      continue;
    }
    if (!forceArg && shop.nearest_station) {
      skipped++;
      continue;
    }
    if (!hasCoords(shop)) {
      console.log(`SKIP(no lat/lng): ${shop.name}`);
      skipped++;
      continue;
    }
    const result = await resolveWithRetry(shop.name, shop.lat, shop.lng);
    if (result) {
      shop.nearest_station = result;
      updated++;
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + "\n", "utf8");
    } else {
      notFound++;
    }
  }

  console.log(
    `\n[manual/shops] updated=${updated} skipped=${skipped} not_found=${notFound} out_of_scope=${outOfScope}`
  );
}

async function main() {
  await processShopsJson();
  await processManualShops();
  console.log("\nDone.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
