// data/shops.json の各拠点(locations[].map_query)を、Nominatim(OpenStreetMapの
// ジオコーディングAPI)で緯度経度に変換し、同ファイルにlat/lngとして書き戻す一回限りの
// バッチスクリプト。アプリ実行時(エンドユーザーのブラウザ)からは一切呼び出さない
// ―― Nominatimの利用ポリシー(https://operations.osmfoundation.org/policies/nominatim/)は
// 大量の即時リクエストや正体不明なUser-Agentでのアクセスを禁じており、
// 「ビルド時に一度だけジオコーディングし、結果を静的データとしてキャッシュする」運用が
// 推奨されているため。1リクエスト/秒のレート制限を守り、有効なUser-Agentを付与する。
//
// 実行方法: node scripts/geocode-shops.js
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOPS_PATH = path.join(__dirname, "..", "data", "shops.json");
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

async function main() {
  const shops = JSON.parse(fs.readFileSync(SHOPS_PATH, "utf8"));
  let geocodedCount = 0;
  let skippedCount = 0;
  let notFoundCount = 0;

  for (const shop of shops) {
    if (!Array.isArray(shop.locations)) {
      console.log(`SKIP(no locations): ${shop.name}`);
      continue;
    }
    for (const loc of shop.locations) {
      if (typeof loc.lat === "number" && typeof loc.lng === "number") {
        skippedCount++;
        continue;
      }
      // Nominatimは事業者名(map_query)より、番地を含む住所文字列(address)のほうが
      // 解決精度が高いため、address(段階的に粗くした候補を含む)→map_queryの順に試す。
      const candidates = [...new Set([...addressCandidates(loc.address), loc.map_query].filter(Boolean))];
      if (candidates.length === 0) {
        console.log(`SKIP(no address/map_query): ${shop.name} / ${loc.label ?? "(single)"}`);
        continue;
      }
      let found = false;
      for (const query of candidates) {
        process.stdout.write(`Geocoding: ${shop.name} / ${loc.label ?? "(single)"} / "${query}" ... `);
        try {
          const result = await geocode(query);
          if (result) {
            loc.lat = result.lat;
            loc.lng = result.lng;
            geocodedCount++;
            found = true;
            console.log(`OK (${result.lat}, ${result.lng})`);
          } else {
            console.log("NOT FOUND");
          }
        } catch (err) {
          console.log(`ERROR: ${err.message}`);
        }
        await sleep(REQUEST_INTERVAL_MS);
        if (found) break;
      }
      if (!found) notFoundCount++;
    }
    // 単一拠点店舗もトップレベルから代表座標を参照できるよう複製しておく
    if (shop.locations.length > 0) {
      shop.lat = shop.locations[0].lat ?? null;
      shop.lng = shop.locations[0].lng ?? null;
    }
  }

  fs.writeFileSync(SHOPS_PATH, JSON.stringify(shops, null, 2) + "\n", "utf8");
  console.log(
    `\nDone. geocoded=${geocodedCount} skipped(cached)=${skippedCount} not_found=${notFoundCount}\nWrote ${SHOPS_PATH}`
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
