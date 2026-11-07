// 「登録した商品」の使い方を見てもらうためのサンプル(店舗・商品・パッケージ写真・★評価・テイスティングログ)。
// 登録した商品が空のときに、ボタンで追加できる。架空のお店・商品で、実在のものではない。
// ID に "-sample-" を含めることで、サンプルかどうかを見分ける(バックアップに入れても、復元後も「サンプル」と分かる)。
import { ROAST_LEVELS } from "./roastLevels";

export const SAMPLE_SHOP_ID = "user-shop-sample-1";

export const isSampleId = (id) => typeof id === "string" && id.includes("-sample-");

const DAY_MS = 24 * 60 * 60 * 1000;

// 商品の定義。daysAgo: 何日前に登録したことにするか。logs の daysAfter: 登録から何日後の記録か。
const SAMPLE_PRODUCTS = [
  {
    id: "user-product-sample-1",
    name: "エチオピア イルガチェフェ",
    price: 1600,
    weightG: 200,
    originCountry: "エチオピア",
    roast: "ライト",
    processingMethod: "ウォッシュド",
    flavors: ["ジャスミン", "レモン", "はちみつ"],
    note: "店頭で試飲して購入。花のような香りと、レモンのような明るい酸。",
    daysAgo: 14,
    rating: 4,
    bag: { base: "#d9b98c", band: "#e8c89a", ink: "#3b2211" },
    logs: [
      {
        id: "sample-log-1a",
        daysAfter: 1,
        entry: {
          place: "home",
          brewMethod: "V60",
          doseG: 15,
          waterG: 240,
          grindSize: "中細挽き",
          waterTempC: 92,
          brewTime: "2:45",
          dialInScore: 72,
          note: "酸が少し立ちすぎ。ジャスミンの香りは出ている。",
          flavors: ["ジャスミン", "レモン"],
        },
      },
      {
        id: "sample-log-1b",
        daysAfter: 3,
        entry: {
          place: "home",
          brewMethod: "V60",
          doseG: 15,
          waterG: 240,
          grindSize: "中細挽き(1段細かく)",
          waterTempC: 90,
          brewTime: "3:00",
          dialInScore: 86,
          note: "湯温を下げて挽き目を細かくしたら、酸が丸くなって甘さが出た。",
          flavors: ["ジャスミン", "はちみつ", "桃"],
        },
      },
    ],
  },
  {
    id: "user-product-sample-2",
    name: "コロンビア ウイラ",
    price: 1450,
    weightG: 200,
    originCountry: "コロンビア",
    roast: "ミディアム",
    processingMethod: "ウォッシュド",
    flavors: ["カラメル", "オレンジ", "ヘーゼルナッツ"],
    note: "バランスがよく、毎日飲みやすい。ネットでは売っていない店頭限定の豆。",
    daysAgo: 9,
    rating: 5,
    bag: { base: "#b98a52", band: "#a97a3e", ink: "#2a180b" },
    logs: [
      {
        id: "sample-log-2a",
        daysAfter: 2,
        entry: {
          place: "home",
          brewMethod: "エアロプレス",
          doseG: 16,
          waterG: 200,
          grindSize: "中挽き",
          waterTempC: 88,
          brewTime: "1:30",
          dialInScore: 90,
          note: "カラメルの甘さとオレンジの酸がきれいに出た。",
          flavors: ["カラメル", "オレンジ"],
        },
      },
    ],
  },
  {
    id: "user-product-sample-3",
    name: "ブラジル 深煎りブレンド",
    price: 1200,
    weightG: 250,
    originCountry: "ブラジル",
    roast: "フレンチ",
    processingMethod: "ナチュラル",
    flavors: ["ダークチョコレート", "ピーナッツ"],
    note: "ミルクと合わせるとおいしい。",
    daysAgo: 3,
    rating: 3,
    bag: { base: "#6b4a30", band: "#3b2211", ink: "#f3e4cc" },
    logs: [
      {
        id: "sample-log-3a",
        daysAfter: 1,
        entry: {
          place: "home",
          brewMethod: "エスプレッソ",
          doseG: 18,
          waterG: 36,
          grindSize: "極細挽き",
          waterTempC: 93,
          brewTime: "0:28",
          dialInScore: 65,
          note: "苦味が強め。もう少し抽出量を増やして試したい。",
          flavors: ["ダークチョコレート"],
        },
      },
    ],
  },
];

// 追加するレコード一式を作る(日付は「いま」からの相対で決める)。
// 返り値: { shops, products, ratings: { [id]: ★ }, logs: { [id]: { id, recordedAt, ...entry }[] } }
export function buildSampleCollection(now = new Date()) {
  const at = (daysAgo) => new Date(now.getTime() - daysAgo * DAY_MS).toISOString();
  const shops = [
    {
      id: SAMPLE_SHOP_ID,
      name: "サンプル珈琲店",
      address: "",
      appShopName: "",
      createdAt: at(Math.max(...SAMPLE_PRODUCTS.map((p) => p.daysAgo))),
    },
  ];
  const products = SAMPLE_PRODUCTS.map((p) => ({
    id: p.id,
    shopId: SAMPLE_SHOP_ID,
    name: p.name,
    price: p.price,
    weightG: p.weightG,
    originCountry: p.originCountry,
    roast: p.roast,
    processingMethod: p.processingMethod,
    flavors: p.flavors,
    note: p.note,
    createdAt: at(p.daysAgo),
  }));
  const ratings = Object.fromEntries(SAMPLE_PRODUCTS.map((p) => [p.id, p.rating]));
  const logs = Object.fromEntries(
    SAMPLE_PRODUCTS.map((p) => [
      p.id,
      p.logs.map((l) => ({
        id: l.id,
        // 登録日より後で、未来にならない日時にする
        recordedAt: at(Math.max(0, p.daysAgo - l.daysAfter)),
        ...l.entry,
      })),
    ])
  );
  return { shops, products, ratings, logs };
}

// 文字を、指定した幅で折り返して描く。まず半角スペースの位置で区切り(単語の途中では切らない)、
// 1語だけで幅を超えるときだけ、1文字ずつ区切る。描いた行数を返す。
function drawWrapped(ctx, text, x, y, maxWidth, lineHeight) {
  const rows = [];
  let line = "";
  const push = () => {
    if (line) rows.push(line);
    line = "";
  };
  for (const word of text.split(" ")) {
    const candidate = line ? `${line} ${word}` : word;
    if (ctx.measureText(candidate).width <= maxWidth) {
      line = candidate;
      continue;
    }
    push();
    if (ctx.measureText(word).width <= maxWidth) {
      line = word;
      continue;
    }
    for (const ch of word) {
      if (ctx.measureText(line + ch).width > maxWidth) push();
      line += ch;
    }
  }
  push();
  rows.forEach((r, i) => ctx.fillText(r, x, y + i * lineHeight));
  return rows.length;
}

const roundRect = (ctx, x, y, w, h, r) => {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
};

// サンプル商品のパッケージ写真(コーヒー豆の袋のイラスト)を、その場で描いて JPEG にする。
// 画像ファイルを同梱せず、実在の商品のパッケージも使わない。"SAMPLE" の文字を入れて、実物と間違えないようにする。
export async function renderSamplePackage(productId) {
  const product = SAMPLE_PRODUCTS.find((p) => p.id === productId);
  if (!product) throw new Error("unknown-sample-product");
  const { bag } = product;
  const roastColor = ROAST_LEVELS.find((r) => r.key === product.roast)?.color ?? "#8B5E2E";

  const W = 800;
  const H = 1000;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  const sans = '"Hiragino Sans", "Yu Gothic", "Noto Sans JP", sans-serif';
  const serif = '"Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif';

  // 背景(木目調のテーブルを思わせる単色のグラデーション)
  const bg = ctx.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, "#efe6d8");
  bg.addColorStop(1, "#d8c9b2");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // 袋の影
  ctx.fillStyle = "rgba(60, 40, 20, 0.18)";
  roundRect(ctx, 150, 120, 520, 800, 26);
  ctx.fill();

  // 袋の本体
  const body = ctx.createLinearGradient(130, 0, 650, 0);
  body.addColorStop(0, bag.base);
  body.addColorStop(0.5, bag.base);
  body.addColorStop(1, "rgba(0,0,0,0.18)");
  roundRect(ctx, 130, 100, 520, 800, 26);
  ctx.fillStyle = bag.base;
  ctx.fill();
  ctx.fillStyle = body;
  ctx.fill();

  // 上部の折り返し(ジッパー部分)
  ctx.fillStyle = "rgba(0,0,0,0.14)";
  ctx.fillRect(130, 100, 520, 70);
  ctx.strokeStyle = "rgba(255,255,255,0.35)";
  ctx.lineWidth = 3;
  for (let x = 150; x < 640; x += 14) {
    ctx.beginPath();
    ctx.moveTo(x, 112);
    ctx.lineTo(x, 158);
    ctx.stroke();
  }

  // ラベル
  ctx.fillStyle = "#f7efe2";
  roundRect(ctx, 180, 250, 420, 520, 18);
  ctx.fill();
  ctx.strokeStyle = bag.ink;
  ctx.globalAlpha = 0.25;
  ctx.lineWidth = 2;
  roundRect(ctx, 192, 262, 396, 496, 12);
  ctx.stroke();
  ctx.globalAlpha = 1;

  ctx.fillStyle = "#3b2211";
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";

  ctx.font = `600 22px ${sans}`;
  ctx.fillText("SAMPLE COFFEE", 390, 318);

  // 豆のイラスト(楕円+中央の線)
  const bean = (cx, cy, angle) => {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.fillStyle = roastColor;
    ctx.beginPath();
    ctx.ellipse(0, 0, 26, 36, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#f7efe2";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(0, -30);
    ctx.bezierCurveTo(10, -10, -10, 10, 0, 30);
    ctx.stroke();
    ctx.restore();
  };
  bean(340, 395, -0.5);
  bean(390, 385, 0.2);
  bean(440, 395, 0.7);

  // 商品名
  ctx.fillStyle = "#2a180b";
  ctx.font = `700 44px ${serif}`;
  const nameLines = (() => {
    ctx.save();
    const y0 = 470;
    const n = drawWrapped(ctx, product.name, 390, y0, 360, 58);
    ctx.restore();
    return n;
  })();

  // 産地・焙煎度
  ctx.fillStyle = "#6b4a30";
  ctx.font = `400 26px ${sans}`;
  const infoY = 470 + nameLines * 58 + 8;
  ctx.fillText(`${product.originCountry}  /  ${product.processingMethod}`, 390, infoY);

  // 焙煎度のバー(8段階のうち、該当する段階を強調)
  const barX = 215;
  const barW = 350;
  const step = barW / ROAST_LEVELS.length;
  const barY = infoY + 40;
  ROAST_LEVELS.forEach((r, i) => {
    ctx.fillStyle = r.color;
    ctx.globalAlpha = r.key === product.roast ? 1 : 0.35;
    ctx.fillRect(barX + i * step, barY, step - 4, r.key === product.roast ? 22 : 12);
  });
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#6b4a30";
  ctx.font = `400 22px ${sans}`;
  ctx.fillText(`焙煎度: ${product.roast}`, 390, barY + 50);

  // 内容量
  ctx.font = `600 24px ${sans}`;
  ctx.fillText(`${product.weightG}g`, 390, barY + 92);

  // 袋の下部の帯
  ctx.fillStyle = bag.band;
  ctx.fillRect(130, 800, 520, 60);
  ctx.fillStyle = bag.ink;
  ctx.font = `600 22px ${sans}`;
  ctx.fillText("これはサンプルです(架空の商品)", 390, 838);

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.78));
  if (!blob) throw new Error("encode-failed");
  return blob;
}
