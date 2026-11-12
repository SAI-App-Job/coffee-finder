// Shopify製の公式ショップから、器具のデータを書き出す(ブラウザのコンソール用)。
//
// 使い方(docs/tool-catalog.md):
//   1. ブラウザで、公式ショップのトップページを開く(例: https://shop.hariocorp.co.jp/)。そのサイトの上で実行する必要がある
//   2. F12 キーで開発者ツールを開き、「コンソール」に、このファイルの中身を、すべて貼り付けて、Enter
//   3. 数分かかる(進み具合が、コンソールに出る)。終わると、JSONファイルが、自動でダウンロードされる
//   4. そのファイルを、プロジェクトのフォルダに置き、次を実行する:
//        py -X utf8 scripts/build_tools_catalog.py <メーカー> --from-file <ファイル名>
//
// ブラウザからの取得は、ふつうの閲覧と同じ見え方で、取得制限がかかりにくい。取得の間隔は、1.5秒(取得制限のときは、待ってやり直す)。
// ここでの絞り込みは、ゆるい(取りこぼさないための候補)。最終的な種類の判定と、除外は、Python側(build_tools_catalog.py)で行う。

(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const host = location.hostname;
  const MAKERS = {
    "shop.hariocorp.co.jp": { key: "hario-shop", collection: "coffee" },
    "www.timemore.com": { key: "timemore" },
    "timemore.com": { key: "timemore" },
    "fellowproducts.com": { key: "fellow" },
    "origami-kai.com": { key: "origami" },
    "oc-shop.co.jp": { key: "ogawa", collection: "coffee-goods" },
  };
  const cfg = MAKERS[host];
  if (!cfg) {
    console.error(`このサイト(${host})は、対象ではありません。公式ショップのトップページで実行してください。`);
    return;
  }
  // 候補にする語(ゆるい絞り込み)
  const CANDIDATE = /ドリッパー|ペーパー|フィルター|ミル|グラインダー|エアロプレス|サイフォン|フレンチプレス|dripper|filter|grinder|\bmill\b|aeropress/i;

  async function getJson(url) {
    for (let i = 0; i < 8; i++) {
      const res = await fetch(url, { credentials: "same-origin" });
      if (res.ok) return res.json();
      if (res.status === 429 || res.status === 503) {
        const wait = Math.min(30 * (i + 1), 180);
        console.warn(`取得制限(${res.status})のため、${wait}秒待ってから、やり直します`);
        await sleep(wait * 1000);
        continue;
      }
      throw new Error(`${url}: HTTP ${res.status}`);
    }
    throw new Error(`${url}: 取得制限が続いたため、中止しました`);
  }

  // 1. 商品の一覧
  const path = cfg.collection ? `/collections/${cfg.collection}/products.json` : "/products.json";
  const listing = [];
  for (let page = 1; page <= 30; page++) {
    const data = (await getJson(`${path}?limit=250&page=${page}`)).products;
    if (!data.length) break;
    listing.push(...data);
    console.log(`一覧 ${page}ページ目: 累計 ${listing.length} 件`);
    if (data.length < 250) break;
    await sleep(5000);
  }
  const picked = listing.filter((p) => CANDIDATE.test(`${p.title} ${p.product_type ?? ""}`));
  console.log(`商品 ${listing.length} 件のうち、候補 ${picked.length} 件。商品ごとのデータ(JAN)を取ります。`);

  // 一覧(/products.json)に出ない商品(販売終了間近・限定在庫など)でも、ページのアドレスが分かっているものは、直接取る。
  // 存在しないアドレスは、404になるだけ(警告を出して、とばす)。
  const EXTRA_HANDLES = {
    timemore: [
      "timemore-chestnut-c2-max-manual-coffee-grinder", // 2026-11-12 時点で、公式ページは、404(販売終了で、削除された)。復活したときのために残す
      "timemore-chestnut-c3-max-manual-coffee-grinder", // 同じ名前の付け方からの推測(無ければ404)
      "timemore-chestnut-c2s-manual-coffee-grinder", // 同上
    ],
  };
  for (const h of EXTRA_HANDLES[cfg.key] ?? []) {
    if (!picked.some((p) => p.handle === h)) picked.push({ handle: h, title: h, product_type: "" });
  }

  // 2. 商品ごとのデータ(.js)。型番ごとのJAN(barcode)がある
  const records = [];
  for (let i = 0; i < picked.length; i++) {
    await sleep(1500);
    try {
      const js = await getJson(`/products/${picked[i].handle}.js`);
      records.push({ handle: picked[i].handle, js });
      console.log(`[${i + 1}/${picked.length}] ${picked[i].handle}  JAN ${js.variants.filter((v) => v.barcode).length}/${js.variants.length}`);
    } catch (e) {
      console.warn(`取得失敗 ${picked[i].handle}: ${e.message}`);
    }
  }

  // 3. ファイルとして、ダウンロードする
  const blob = new Blob([JSON.stringify({ maker: cfg.key, base: location.origin, exportedAt: new Date().toISOString(), records })], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `tools-${cfg.key}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  console.log(`完了: tools-${cfg.key}.json をダウンロードしました(${records.length}件)。`);
})();
