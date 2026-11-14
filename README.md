# Coffeection(コーヒーの検索とレシピの記録)

コーヒー専門店・焙煎豆販売店の位置情報や価格比較、産地ごとの豆の特徴を収集するアプリ。
Vite + React + Tailwind CSS v4 で構築。

## セットアップ

```bash
npm install
npm run dev
```

`http://localhost:5173` で開発サーバーが起動します。

## ビルド

```bash
npm run build
npm run preview
```

## フォルダ構成

```
src/App.jsx      … アプリ本体(単一ファイル。今後コンポーネント分割を推奨)
docs/            … これまでの調査資料(産地・グレード・団体・フレーバーホイール等)
scraper/         … 店舗・大会情報のスクレイパー(Python)
```

## 経緯・注意事項

- `src/App.jsx` は claude.ai のチャット内アーティファクトとして育ってきた経緯があり、
  現在3,000行超の単一ファイル。claude.ai のアーティファクトプレビュー環境では、
  このサイズがネックとなりTailwindのスタイルが適用されないという不具合が発生した
  (Viteでの実ビルドでは問題なく動作することを確認済み)。
- 今後の開発では、`src/App.jsx` を機能単位(ProductCard, OriginMapView,
  TriviaView 等)でコンポーネントファイルに分割していくことを推奨する。
- `scraper/` 内のPythonスクレイパーは、実行前に対象サイトのrobots.txtを
  改めて確認すること(調査時点の状態を`docs/coffee-country-associations.md`
  等に記録済みだが、サイト側の更新により変わっている可能性がある)。
- データは現状すべてモック(`MOCK_PRODUCTS`等のハードコード)。実運用には
  `scraper/`の出力を読み込むデータ層の実装が必要。

## ライセンス

All Rights Reserved。閲覧は自由ですが、著作権者の書面による許可なく複製・
再配布・改変・商用利用を行うことはできません。詳細は[LICENSE](./LICENSE)を
参照してください。

## CoffeeFinderBot について(店舗・サイトの運営者の方へ)

このリポジトリのスクレイパー(`scraper/`)は、User-Agent `CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)` を名乗って、各店舗の公式サイトの、公開されている商品ページ・店舗情報を取得します。

- 目的: 近くの自家焙煎店とコーヒー豆の情報を、見やすく表示するアプリ(Coffeection)のため。
- 頻度: 週1回程度(GitHub Actions で実行)。取得するのは、公開されている商品ページ・店舗情報です。
- robots.txt を確認し、禁止されている店舗は取得しません(確認の記録: `docs/robots-audit.md`)。
- 載せるのは、名前・価格・産地などの事実と短い記述、アプリが抽出した情報だけです。店舗の長い説明文や写真は、載せません(`docs/coffee-app-data-model.md`)。
- **取得の停止・掲載内容の修正や削除**をご希望の場合は、X の [@SaiCoffea](https://x.com/SaiCoffea) までDMでご連絡ください。速やかに対応します。

