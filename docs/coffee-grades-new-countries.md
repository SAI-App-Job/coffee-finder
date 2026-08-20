# 新規5ヶ国(メキシコ・ペルー・エルサルバドル・ルワンダ・パナマ)グレード規格 調査まとめ

coffee-processing-and-grades.md(既存の各国グレード規格調査)を補完し、ORIGIN_GUIDEに後から追加した5ヶ国のうちペルー・エルサルバドル・ルワンダのgradeSystem(グレード基準)フィールドの出典を記録する。メキシコは既存の`officialBody`に等級名の記載がなく、今回追加した3ヶ国と異なり公式一次資料も確認できていないため対象外。パナマは調査したが後述の通り一次資料が確認できず、gradeSystemの追加を見送った。

---

## 1. ペルー

**一次資料**: [INACAL(ペルー国立品質院)GIP 101:2021 - NTP 209.027:2018「CAFÉ. Café verde. Requisitos」実施ガイド](https://www.cooperacionsuiza.pe/wp-content/uploads/2021/09/GQSP-PERU-Guia-101-NTP-209.027-2018-CAFE.-Cafe-verde.-Requisitos-2.pdf)(GQSP Perú/ONUDI/Cooperación Suiza SECO共同刊行、INACAL公式)

コロンビアのFNCやエルサルバドルのCSCと異なり、ペルーの生豆等級は「エクセルソ」のような商業銘柄名ではなく、**カッピング品質+欠点数による3段階の番号グレード**(Grado 1〜3、INACAL=ペルー国立品質院が運用)。

| 等級 | 説明 | カッピング | 欠点数(300g中) |
|---|---|---|---|
| Grado 1 | 当期収穫、色・粒サイズ均一、非常にフレッシュな香り | 優〜秀逸。香り強く典型的、際立つ風味、酸味高い、コク良好 | 最大15 |
| Grado 2 | 当期収穫、色均一、フレッシュな香り | 良好。香り良好、酸味良好、コク中程度 | 最大23 |
| Grado 3 | 粒サイズ・色にばらつき、香りは弱〜中程度 | 中程度 | 最大30 |

3等級共通の基準: 水分10〜12.5%、粒度は50%以上がマラ15(6.0mm)以上、マラ14(5.6mm)未満は5%以下。

別途、より厳格な基準の**NTP 209.311:2019「CAFÉS ESPECIALES」**(スペシャルティコーヒー規格)が存在し、Grado 1よりさらに上位の輸出向け区分として機能する: 主要欠点0個、副次欠点最大5個(350gサンプル)、水分10〜12%。

---

## 2. エルサルバドル

**一次資料**: [OSARTEC(エルサルバドル技術規制機構)RTS 67.08.01:18「CAFÉ. CAFÉ VERDE (CAFÉ ORO). REQUISITOS DE CALIDAD」](https://members.wto.org/crnattachments/2018/SPS/SLV/18_6014_00_s.pdf)(WTO SPS通報経由で入手。運用機関はConsejo Salvadoreño del Café=CSC)

**既存のORIGIN_GUIDE記載の訂正**: `terroir`フィールドに「SHB=1,200m以上、HG=900〜1,200m、CS=500〜900m」とあったが、一次資料で正しくは**SHG**(Strictly High Grown、直訳は「厳格な高地栽培」)であり「SHB」ではない(SHBはグアテマラのStrictly Hard Beanの略で無関係)。既存のdocs/coffee-processing-and-grades.md(43行目)でも「エルサルバドル | SHG」と正しく記載されており、今回originGuide.js側の表記も訂正した。標高帯もRTS原文に基づき修正:

| 等級 | 標高 |
|---|---|
| CS(Central Standard、中央標準) | 800m.s.n.m.以下 |
| HG(High Grown、中高地栽培) | 801〜1,200m.s.n.m. |
| SHG(Strictly High Grown、厳格高地栽培) | 1,201m.s.n.m.超 |

標高のほか精選方法(水洗/非水洗)・欠点数(Brasil/Nueva York方式、300gサンプル)の3基準で分類される。

---

## 3. ルワンダ

**一次資料**: [ICO(国際コーヒー機関)ICC 122-12「National Quality Standards」(2018年8月23日付、第122回国際コーヒー理事会提出資料)](https://www.ico.org/documents/cy2017-18/icc-122-12e-national-quality-standards.pdf)所収のルワンダ提出情報。運用機関はRwanda Standards Board(ルワンダ規格協会)とNAEB(国家農業輸出開発庁)。

ルワンダはウォッシュド(フリーウォッシュド)/セミウォッシュド/ロブスタで別体系を持ち、350gサンプルのカッピングスコアと欠点数で格付けする:

**アラビカ・フリーウォッシュド**
| 等級 | スコア | 主要欠点 | 欠点数上限(350g) |
|---|---|---|---|
| Super Specialty | 90〜100点 | 不可 | 5 |
| Specialty | 80〜90点 | 許容 | 5 |
| Grade 1 | 70〜79点 | 不可 | 9〜23 |
| Grade 2 | 60〜69点 | - | 24〜86 |
| Grade 3 | 50〜59点 | - | 86超 |

**アラビカ・セミウォッシュド**はGrade 1〜4(スコア40〜80%)、**ロブスタ**はGrade 1(フリーウォッシュド)/Grade 2(セミウォッシュド)の2区分のみ。

---

## 4. パナマ(見送り)

SCAP(パナマ・スペシャルティコーヒー協会、コーヒー品評会「ベスト・オブ・パナマ」の主催団体)は品評会・オークションの運営機関であり、コロンビアFNCやエルサルバドルCSCのような法定の生豆等級規格(標高別・スクリーンサイズ別の商業区分)を定めているという記載は見つからなかった。ICOの「National Quality Standards」(ICC 122-12、2018年)の回答国リストにもパナマは含まれていない。パナマ商工省規格局(DGNTI)傘下のCOPANIT規格群も確認したが、コーヒー生豆の等級を定めたものは見当たらなかった(COPANIT 24-99は排水処理基準で無関係)。

不確かな情報を断定的に載せることを避けるため、ORIGIN_GUIDEのパナマにはgradeSystemを追加していない。将来、SCAPまたはMIDA(パナマ農牧開発省)による公式な等級規格の一次資料が見つかった場合に追記する。
