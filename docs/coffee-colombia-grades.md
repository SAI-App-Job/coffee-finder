# コロンビア グレード規格 調査まとめ

ORIGIN_GUIDEのコロンビアにgradeSystemを追加するための出典整理。2つの一次/準一次資料を突き合わせている。

## 出典1: cafedecolombia.jp「コロンビアコーヒーの等級」

[cafedecolombia.jp/colombia/specialty/grade/](https://cafedecolombia.jp/colombia/specialty/grade/)(FNC=コロンビアコーヒー生産者連合会、および関連会社Almacaféの基準に基づくと明記)

「エクセルソ(Excelso)」は7段階の等級群に共通する親カテゴリ名で、単独では意味をなさず、常に「エクセルソ+サブ名」の複合語として使われる。

| 名称 | スクリーンサイズ | 許容範囲 |
|---|---|---|
| Excelso Premium | 18 | スクリーン14-18、最大5% |
| Excelso Supremo | 17 | スクリーン14-17、最大5% |
| Excelso Extra | 16 | スクリーン14-16、最大5% |
| Excelso Europa | 15 | スクリーン12-15、複数カテゴリー |
| Excelso UGQ | 15全体50%以上、残り14 | スクリーン12-14、最大5% |
| Excelso Maragogipe | 17 | スクリーン14-17、最大5% |
| Excelso Caracol | 12 | 平豆最大10% |

スクリーン16以上とピーベリー(カラコル)のみがスペシャルティコーヒーに分類される。

## 出典2: FNC決議第5号(2002年)/ Comité Nacional de Cafeteros

ICO(国際コーヒー機関)「National Quality Standards」(ICC 122-12、2018年)所収のコロンビア提出情報によれば、法的な最低輸出品質基準はComité Nacional de Cafeteros(国家コーヒー生産者委員会。FNCとコロンビア政府代表で構成)決議第5号(2002年)が定めており、5段階で分類される:

| 名称 | 説明 |
|---|---|
| Premium | スクリーン18、スクリーン14で最大5%許容 |
| Supremo | スクリーン17、スクリーン14で最大5%許容 |
| Extra | スクリーン16、スクリーン14で最大5%許容 |
| Excelso | スクリーン14、スクリーン12で最大1.5%許容、50%以上がスクリーン15 |
| Caracol | スクリーン12、平豆最大10%許容 |
| _欠点_ | 500gサンプルで最大72欠点(うちグループ1の欠点は最大12個まで) |

出典1(cafedecolombia.jp)にあるEuropaとMaragogipeの2グレードは、この2002年の法定最低基準の表には含まれていない。業界で商業的に使われる追加区分、または後年の改訂によるものと考えられるが、確定的な出典は確認できていない。

## ORIGIN_GUIDEへの反映方針

法定の最低輸出基準(Excelso以上のみ輸出可能)という既存officialBodyの記述と整合させつつ、7段階のサブグレード名を列挙する形でgradeSystemを構成する。「エクセルソ」単独ではなく必ず複合語になる点を明記する(スクレイパー側のグレード判定ロジック[data/colombia_grade_synonyms.json](../data/colombia_grade_synonyms.json)と同じ理解に基づく)。
