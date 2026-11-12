# 利用者のデータの保存と、バックアップの規則

利用者が作ったデータ(コレクション・★評価・テイスティングログ・ノート・マイツール・写真など)は、**端末の中(ブラウザの localStorage と IndexedDB)だけ**に保存される。運営者は、取得も復元もできない。
そのため、アプリを更新しても、利用者のデータが失われない・読めなくなることが無いように、次の規則を守る。

## 保存しているもの

| 保存先 | キー | 中身 | バックアップ |
|---|---|---|---|
| localStorage | `coffee-finder:favorites` / `favorite-dates` | お気に入りの商品ID / 保存日 | ○ |
| | `coffee-finder:ratings` | ★評価 `{ [商品ID]: { rating, ratedAt } }` | ○ |
| | `coffee-finder:tasting-logs` | テイスティングログ `{ [商品ID]: 記録[] }`(自宅抽出の豆の記録) | ○ |
| | `coffee-finder:shop-tasting-notes` | テイスティングノート `{ [店名]: 記録[] }`(店舗で飲んだ1杯) | ○ |
| | `coffee-finder:user-collection` | 手動で登録した店舗・商品 | ○ |
| | `coffee-finder:my-tools` | マイツール(器具の登録) | ○ |
| | `coffee-finder:product-snapshots` | 保存・評価・記録した商品の、名前・店名・産地の控え | ○ |
| | `coffee-finder:achievements` / `photo-dates` | 実績の獲得日 / 写真を追加した日 | × 実績は記録から再計算される |
| | `coffee-finder:view-history` / `alerts` / `alert-snapshot` | 閲覧履歴・新着や在庫の変化の通知 | × |
| | `coffee-finder:color-theme` / `accent-theme` / `language` / `display-radius` / `favorite-area` | 設定 | × |
| | `coffee-finder:is-premium` | プレミアムの状態 | **×(意図的)**。ファイルを編集すれば課金を回避できてしまうため。課金を実装するときは、ストア・サーバー側で復元できる作りにする |
| IndexedDB `coffee-finder-photos` | (商品ID) | パッケージ写真(縮小済みのJPEG) | △ 書き出すときに選んだ場合だけ |
| localStorage | `coffee-finder:schema-version` | 保存形式の版(いまは `1`) | × |

利用者のデータのキーの一覧は、`src/utils/storage.js` の `USER_DATA_KEYS`。

## 規則

1. **キー名を変えない。** 変えると、既存の利用者のデータが見えなくなる。
2. **保存の形は、足すだけにする。** 新しい項目を足すのは自由(読むときに、無ければ既定値にする)。項目の削除・名前の変更・意味の変更は、移行(下記)が要る。
3. **読み込みで、データを捨てない・上書きしない。** 読み込みは `loadStoredJson`(`src/utils/storage.js`)を使う。
   - 壊れた値・形が違う値は、元の文字列を `<キー>:unreadable`(最大3件まで `-2`・`-3`)に残してから、空で始める。
   - 一部を捨てるとき(知らない種類のマイツールなど)は、`lossy: true` を返す。元の文字列を、残す。
4. **保存形式を変えるときは、移行を書く。** `src/utils/storage.js` の `MIGRATIONS` に `{ to: 版, run() {…} }` を足し、`SCHEMA_VERSION` を上げる。
   - `run()` の前に、利用者のデータが、`<キー>:before-v<版>` に、自動で残る。
   - 古い版のアプリで作ったデータ(版が無い=版1)を、読めること。
   - バックアップファイルの版(`BACKUP_VERSION`)も、同時に見直す。古い版のファイルも、読み込めるようにする。
5. **公開URL(オリジン)を変えない。** localStorage・IndexedDB は、ドメインごと。URLが変わると、全データが見えなくなる。やむを得ず変えるときは、先に、書き出し→新しいURLで読み込み、の手順を案内する。
6. **新しい種類のデータを足したら、同時に直す**: ①この表 ②`USER_DATA_KEYS` ③バックアップ(`DataBackup.jsx`・`utils/backupMerge.js`) ④プライバシーポリシー(`public/privacy-policy*.html`)と `AboutView.jsx` ⑤英語訳(`npm run i18n:check`)。

## バックアップファイル(設定の「データのバックアップ」)

- JSON1ファイル。`version` が版。**版 1**: お気に入りのみ / **版 2**: + 登録した店舗・商品・写真 / **版 3**: + ★評価・テイスティングログ・テイスティングノート・マイツール・商品名の控え。
- 読み込みは**追加のみ**(上書きしない)。評価だけは、同じ商品なら、日時が新しい方を残す。ログ・ノートは、記録の `id` で重複を判断する。
- ファイルは、利用者が編集できる外部の入力として扱う(`utils/backupMerge.js` が、形を確かめて、合わないものを飛ばす)。
- ファイルには、メモ・感想が入る。画面にも、渡すときの注意を出している。

## 端末側の自動削除への備え

- ブラウザは、空き容量が足りないときなどに、サイトのデータを自動で消すことがある。利用者のデータができたら、1回だけ `navigator.storage.persist()` で、消さないよう求める(`requestPersistentStorage`)。ブラウザが断ることもあるため、**バックアップの代わりにはならない**。
- Android(TWA)でも、アプリのストレージ消去・アンインストールで消える。

## 商品データから消えた商品

商品データ(`data/products.json`)は、取得し直すと、販売が終わった商品が消えることがある。利用者のお気に入り・★・ログは、端末に残るが、商品が見えなくなる。
そのため、商品が見えているうちに、名前・店名・産地を `product-snapshots` に控えている(`hooks/useProductSnapshots.js`)。日記などの題名は、商品が消えても、この控えから出る。
**未対応(公開後に、必要に応じて判断)**: 消えた商品を、コレクションなどの一覧に「現在は収録されていない商品」として出す表示。
