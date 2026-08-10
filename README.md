# Coffee Finder(自家焙煎豆情報アプリ)

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
