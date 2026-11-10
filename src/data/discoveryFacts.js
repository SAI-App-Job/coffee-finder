// ---------------------------------------------------------------------------
// 豆知識(Discovery Facts)。これまでの調査全体から、商品を探している最中にも
// ふと発見・学びが得られるよう、短いトリビアとして抜粋している。
// ---------------------------------------------------------------------------

/**
 * @typedef {Object} DiscoveryFact
 * @property {string} title
 * @property {string} text
 * @property {string} source - 出典(docs/配下の調査資料ファイル名、または一次資料の
 *   名称・URL)。validateDiscoveryFacts()が読み込み時に必須チェックする。
 */

/** @type {DiscoveryFact[]} */
export const DISCOVERY_FACTS = [
  {
    title: "「精選」と「精製」は別の言葉",
    text: "コーヒーチェリーを生豆にする工程は本来「精選」。「精製」は化学用語(混合物を純物質にする工程)からの誤用・慣用表記だが、実店舗ではどちらの表記も使われている。",
    source: "docs/coffee-processing-and-grades.md",
  },
  {
    title: "クリスタルマウンテンはジャマイカ産ではない",
    text: "名前がブルーマウンテンと似ているため誤解されやすいが、特定銘柄としての「クリスタルマウンテン」はキューバ産のコーヒーを指す。",
    source: "docs/coffee-designated-brands.md",
  },
  {
    title: "マンデリンとガヨマウンテンは排他的な関係",
    text: "どちらも北スマトラ島産だが、タケンゴン周辺(ガヨマウンテン地区)産かどうかで名乗れる特定銘柄名が変わる。同じ島でも重ならない。",
    source: "docs/coffee-designated-brands.md",
  },
  {
    title: "スマトラ式は2段階で乾燥させる",
    text: "マンデリン等で使われる「ウェットハルド」は、農家段階での1次乾燥→高含水率のまま脱穀→2次乾燥という独自工程。生豆が深緑色になるのもこのため。",
    source: "docs/coffee-processing-and-grades.md",
  },
  {
    title: "同じ「G1」でも国が違えば意味が違う",
    text: "エチオピアのG1は欠点0〜3個(300gあたり)の最高等級。インドネシアのG1は欠点0〜11個程度と、同じ表記でも基準の厳しさが異なる。",
    source: "docs/coffee-processing-and-grades.md",
  },
  {
    title: "ブルーマウンテンは商標で守られている",
    text: "ジャマイカのJACRA(農産物規制庁)が「ブルーマウンテン」の名称を商標として独占保有し、認証を受けた業者しか名乗れない。",
    source: "docs/coffee-country-associations.md",
  },
  {
    title: "ゲイシャはエチオピア原産",
    text: "華やかな香りで知られる「ゲイシャ(Geisha/Gesha)」種は、実はパナマではなくエチオピア原産。パナマの農園で栽培されたロットがオークションで高値を記録し有名になった。",
    source: "docs/coffee-origin-new5-countries.md",
  },
  {
    title: "フレーバーホイールの生みの親",
    text: "SCAのコーヒーテイスターズフレーバーホイールは、カンザス州立大学が作成したWCR(ワールドコーヒーリサーチ)のセンサリーレキシコンが基になっている。",
    source: "docs/coffee-world-coffee-research.md",
  },
  {
    title: "スペシャルティの基準は「点数」から「4つの軸」へ",
    text: "SCAは2024年、従来の「カッピングスコア80点以上」という単一基準から、物理・記述・嗜好・外的要因の4つを組み合わせるCVAという評価体系に移行した。",
    source: "docs/coffee-value-assessment.md",
  },
  {
    title: "ハワイには「ハワイ産と名乗れる最低ライン」がある",
    text: "ハワイ州の行政規則で、ハワイ産の緑豆はHawaii No.3の品質基準を満たさなければ、ハワイの地域名を付けて売ることができない。満たさない場合は、地域名を付けず「offgrade」または単に「coffee」と表示する必要がある。",
    source: "ハワイ州行政規則 §4-143-1 https://www.law.cornell.edu/regulations/hawaii/Haw-Code-R-SS-4-143-1 / Hawaii Coffee Association「Grading Standards」https://hawaiicoffeeassoc.org/page-1771566",
  },
  {
    title: "タンザニアは輸出まで一つの機関が管理",
    text: "Tanzania Coffee Board(タンザニアコーヒー局)は、法律により豆の格付け・オークション運営・輸出許可までを一元的に管理する、珍しいタイプの政府機関。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "ブラジルは世界初の格付け国",
    text: "1836年、ブラジルは世界で初めて標準化されたコーヒーの格付け制度を導入した。今のCOB(ブラジル公式分類)の原型はここまでさかのぼる。",
    source:
      "Daily Coffee News「COB: The Complex History of the 'Brazilian Official Classification' System」(2019) https://dailycoffeenews.com/2019/02/21/cob-the-complex-history-of-the-brazilian-official-classification-system/",
  },
  {
    title: "ブラジルの「タイプ1」は実在しない",
    text: "ブラジルの欠点数グレード(No.2〜8)は、最上位表記の「No.1」が理論上の基準として存在するのみで、実際の流通ではNo.2が事実上の最高等級として扱われる。",
    source: "docs/coffee-processing-and-grades.md",
  },
  {
    title: "グアテマラだけの輸出税",
    text: "グアテマラでは輸出額の1%が唯一の輸出税として課され、Anacafé(全国コーヒー協会)の運営財源になっている。他国にはあまり見られない仕組み。",
    source: "docs/coffee-country-associations.md",
  },
  {
    title: "最低輸出基準がある国とない国",
    text: "コロンビアは法律で「エキセルソ以上でなければ輸出できない」と定めているが、隣国グアテマラには最低輸出等級の定めがなく、低品質でも輸出自体は可能という対照的な制度。",
    source: "docs/coffee-country-associations.md",
  },
  {
    title: "インドネシアには輸出者団体が2つある",
    text: "「AEKI」と「GAEKI」という似た名前の輸出者団体が存在するのは、内部対立から一方が分裂して生まれたため。どちらが正式な代表団体かは今も係争中とされる。",
    source:
      "Neilson et al.「Hilirisasi: Resource-based industrialisation and Global Production Networks in the Indonesian coffee and cocoa sectors」(ResearchGate, 2018)、Telegraf.co.id「Perselisihan Organisasi Kopi Meruncing」(2016) https://telegraf.co.id/perselisihan-organisasi-kopi-meruncing/、GAEKI公式サイト https://gaeki.or.id/",
  },
  {
    title: "イエメンには公的な等級認証機関が事実上ない",
    text: "内戦の影響で標準計量局(SMA)が機能しておらず、モカマタリのような有名銘柄でも公式な等級規格・分類が存在しない。品質検証は民間団体や輸入業者に頼っている。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "ベトナムはロブスタが9割超",
    text: "世界第2位のコーヒー生産国ベトナムは、生産の9割超をロブスタ種が占める数少ない主要生産国。缶コーヒーやインスタントコーヒーの原料として世界中で使われている。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "「フレーバー」には2つの意味がある",
    text: "風味を表す「フレーバー」と、人工的に香り付けした「フレーバーコーヒー」の略としての「フレーバー」は、まったく別の意味。パーサー開発中、この2つを混同しかけたことがある。",
    source: "docs/coffee-flavor-notes.md",
  },
  {
    title: "香りにも専門用語の使い分けがある",
    text: "挽いた粉から香る「フレグランス」と、抽出液から立ち上る「アロマ」は、専門的には別の香りとして区別される。",
    source: "docs/coffee-flavor-notes.md",
  },
  {
    title: "「シティロースト」はニューヨーク発祥",
    text: "焙煎度の呼び名「シティロースト」は、この焙煎度がニューヨーク・シティで最も好まれたことに由来する。",
    source: "docs/coffee-roast-levels.md",
  },
  {
    title: "昔はヨーロッパの国ごとに好みの焙煎度が違った",
    text: "20世紀初頭、イギリスは浅煎り好み、フランス・イタリアは深煎り好みと、国によってコーヒーの焙煎文化がはっきり分かれていた。",
    source: "docs/coffee-roast-levels.md",
  },
  {
    title: "「ヘアルーム」は品種名ではない",
    text: "エチオピア産の説明でよく見る「heirloom(ヘアルーム)」は、特定の品種名ではなく、数千種にのぼるとされるエチオピア在来種の総称。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "コーヒーの木の寿命は20〜30年",
    text: "一度植えた品種は長期間栽培し続けることになるため、生産者にとって品種選びは20〜30年先まで影響する重い判断になる。",
    source: "docs/coffee-world-coffee-research.md",
  },
  {
    title: "ジャマイカは2025年のハリケーンで収穫の4割を失った",
    text: "2025年10月のハリケーンMelissaにより、ジャマイカでは成熟した作物の約4割が失われたと報告されている。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "グアテマラには300を超える微気候がある",
    text: "活火山・休火山と豊かな生物多様性により、グアテマラ国内には300を超える微気候が存在するとされる。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "コロンビアは地域で収穫期が真逆になる",
    text: "赤道に近いコロンビアでは、北部のウイラと南部のナリーニョ等で主収穫・副次収穫の時期が入れ替わり、国全体では実質通年で収穫がある。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "ケニアのSL28はカシス風味の立役者",
    text: "1930年代に選抜された品種SL28は、干ばつに強い深い根を持ち、リンゴ酸主体の構造がケニアコーヒー特有のカシス(黒スグリ)様の風味を生み出す。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "ブラジルの生産地はある年の大霜害で移動した",
    text: "1975年の大霜害をきっかけに、被害の大きかった南部の生産者が霜の少ないミナスジェライス州へ移動し、今の主要産地の構図ができた。",
    source: "docs/coffee-discovery-facts-sources-9countries.md",
  },
  {
    title: "コロンビア・ケニア・タンザニアは「同じ仲間」",
    text: "世界のコーヒー価格指標(I-CIP)では、地理的に離れたこの3カ国だけで「Colombian Milds」という一つの価格グループを構成する。共通点は地理ではなく、完全ウォッシュド・高地栽培という精選品質。",
    source: "docs/coffee-ico.md",
  },
  {
    title: "エチオピアは価格上「ブラジルの仲間」",
    text: "国際コーヒー機関(ICO)の価格指標では、エチオピアはブラジルと同じ「Brazilian Naturals」グループに分類される。産地の性格は正反対だが、「ナチュラル精選」という製法軸でグループ化されているため。",
    source: "docs/coffee-ico.md",
  },
  {
    title: "コーヒー価格の重み付けは生きている",
    text: "世界のコーヒー価格指標(I-CIP)を構成する4グループの重み付けは、2005年に「13/24/29/34%」だったものが2007年には「14/20/31/35%」に改定されるなど、世界の生産構造の変化に応じて定期的に見直される。",
    source: "docs/coffee-ico.md",
  },
  {
    title: "「80点基準」はSCA自身が2021年に卒業していた",
    text: "「スペシャルティコーヒー=カッピング80点以上」という基準は、実はSCA自身が2021年に「特性ゆえに市場で高い価値を持つコーヒー」という定性的な定義に置き換えている。ただし旧基準は業界の通説として今も根強く使われ続けている。",
    source: "docs/coffee-value-assessment.md",
  },
  {
    title: "コーヒー鑑定士資格「Qグレーダー」の運営元が変わった",
    text: "コーヒーの品質を国際基準で鑑定する資格「Qグレーダー」は、2003年からCQI(コーヒー品質協会)が運営してきたが、2025年10月からSCAへ完全移管された。新制度はCVA(4軸評価体系)を基盤にしている。",
    source: "docs/coffee-industry-bodies.md",
  },
  {
    title: "ロブスタの鑑定士はウガンダが認定する",
    text: "アラビカ用のQグレーダー資格とは別に、ロブスタ版のQグレーダーは、ウガンダコーヒー開発公社(UCDA)という一国の政府機関が国際的な認定を担っている。",
    source: "docs/coffee-industry-bodies.md",
  },
  {
    title: "「コーヒーのオリンピック」はブラジルのオークションから始まった",
    text: "国際品評会Cup of Excellenceは、1999年にブラジルで行われた「Best Brazil」というオンラインオークション企画が起源。設立時の資金にはICO(国際コーヒー機関)も関わっていた。",
    source: "docs/coffee-industry-bodies.md",
  },
  {
    title: "「緑のカエル」は合併で生まれたロゴ",
    text: "サステナビリティ認証でおなじみの「緑のカエル」ことRainforest Allianceは、2018年にUTZ(グアテマラ人生産者とオランダ人ロースターが創設)と合併して生まれた統合ブランド。",
    source: "docs/coffee-industry-bodies.md",
  },
  {
    title: "SCAJ誕生のきっかけは「コーヒークライシス」だった",
    text: "日本スペシャルティコーヒー協会(SCAJ、2003年設立)が生まれた背景には、2001〜02年に国際相場が史上最低価格をつけ、生産国も消費国も疲弊した「コーヒークライシス」への危機感があった。",
    source: "docs/coffee-industry-bodies.md",
  },
  {
    title: "サパティスタ運動が今のメキシココーヒーの姿を作った",
    text: "1994年のサパティスタ民族解放軍(EZLN)蜂起は、土地制度をめぐる反発から起きた。蜂起後の土地再分配により、チアパス州では大農園化が進まず、今日まで続く小規模農家中心の生産構造が形づくられた。",
    source: "docs/coffee-origin-new5-countries.md",
  },
  {
    title: "内戦が皮肉にも伝統品種を守った",
    text: "1979〜1992年のエルサルバドル内戦下、多くの中米諸国が高収量品種への植え替えを進めていた1980年代、同国の農園は放置されたことで、結果的に伝統品種のティピカ・ブルボンやパカマラが高い比率で温存された。",
    source: "docs/coffee-origin-new5-countries.md",
  },
  {
    title: "ルワンダのコーヒー復興を導いたのは女性たちだった",
    text: "1994年のジェノサイド後、夫を失った女性たちの自立支援を目的にマラバの協同組合が発足するなど、女性たちが協同組合の主要な運営者としてコーヒー産業の復興を牽引してきた。",
    source: "docs/coffee-origin-new5-countries.md",
  },
  {
    title: "パナマゲイシャは1kgあたり3万ドルを超えた",
    text: "2004年、ハシエンダ・ラ・エスメラルダのゲイシャ種ロットが当時の記録価格で落札され「業界を一変させた」と評された。その後も記録は更新を重ね、2025年には1kgあたり30,204ドルという世界記録を樹立している。",
    source: "docs/coffee-origin-new5-countries.md",
  },
  {
    title: "タンザニアには「自国だけの」等級規格がない",
    text: "タンザニアは独自のコーヒー等級規格を持たず、東アフリカコミュニティ(EAC)共通規格「EAS 130:1999」を採用している。事務局は実はタンザニアのアルーシャに置かれているが、ウガンダも同じ規格に準拠していることをICOへの提出資料で明らかにしており、東アフリカの複数国が規格を共有している実例になっている。",
    source: "docs/coffee-tanzania-grades.md",
  },
  {
    title: "「モカ」は港の名前でもある",
    text: "コーヒーの「モカ」は、イエメンの港の名前でもある。FAOとIFCの2023年の報告は、モカ(Al Mokha)港を、歴史的にイエメンからのコーヒー輸出の主要な拠点と記し、「モカ」コーヒーはこの港と結びつけられていると述べる。ICOの歴史解説も、当時の大きな港だったモカの名が、いまではコーヒーの一種を指す言葉になっていると記している。",
    source: "FAO/IFC「Coffee value chain in Yemen」(2023)、ICO「A história do café」",
  },
  {
    title: "コスタリカは独立の年に、貧しい人々へコーヒーの苗を配った",
    text: "コスタリカのコーヒー協会ICAFEの地理的表示の仕様書(Pliego de Condiciones)によると、最初の種子は18世紀末に届いたが、重要なコーヒー栽培の活動が始まったと歴史的な証拠で確実にいえるのは1808年以降。独立の年の1821年には、サンホセの自治体(corporación josefina)が、貧しい人々にコーヒーの苗を無償で配った。",
    source: "ICAFE「Pliego de Condiciones: Indicación Geográfica」",
  },
  {
    title: "「AA」はふるいの番号で決まる等級(ケニア・タンザニア)",
    text: "ケニアのコーヒー規則(2019年)では、AAは平豆で、スクリーン21を通過して18に残る豆(7.2mm)。タンザニアのコーヒー産業規則(2013年)では、AAはスクリーン18に最低90%が残る豆(スクリーン17は最大8〜10%)。どちらも、AAはふるいの番号による大きさの等級で、書き方は違う。東アフリカ規格(EAS 130:1999)は、大きさと形による格付けは、品質のおおよその目安にすぎないと述べている。",
    source: "ケニア Crops (Coffee)(General) Regulations 2019、タンザニア Coffee Industry Regulations 2013、東アフリカ規格 EAS 130:1999",
  },
  {
    title: "グアテマラの「SHB」は、標高1,370m超のコーヒー",
    text: "グアテマラのコーヒー協会Anacaféの図では、コーヒーのタイプが標高で分けられている。SHBは標高4,500フィート(1,370m)超、Semi-Hard / Hardは3,500〜4,500フィート(1,066〜1,370m)、Extra Prime / EPWは2,500〜3,500フィート(764〜1,066m)。",
    source: "Anacafé(Guatemalan Coffees)「Coffee types」",
  },
  {
    title: "ルワンダは、アフリカで最初にCOEを開いた国",
    text: "COEを運営するACE(Alliance for Coffee Excellence)のブログ(2018年8月)は、ルワンダがアフリカで最初にカップ・オブ・エクセレンス(COE)を開催した国で、最初のCOEは2008年にさかのぼると記している。",
    source: "ACEブログ(2018-08-23)",
  },
  {
    title: "コーヒーに「生産の割当」があった時代",
    text: "ICO(国際コーヒー機関)のFAQによると、ICOは、消費の必要量を超えるコーヒーの供給を市場から保留する「割当制度」を、1962年から1989年まで、断続的に運用した。1989年に、割当の配分で合意できず、制度は停止された。現在、ICOは割当制度を運用していない。",
    source: "ICO「FAQs」",
  },
  {
    title: "エチオピアは2019年に、一部の小農の直接輸出を認めた",
    text: "USDA(米国農務省)FASの報告によると、エチオピアのコーヒー生産の90%は小農が占める(2026年版)。エチオピア商品取引所(ECX)は2008年に設立された(2019年版)。2019年の政策改革で、2ha以上の土地を持つ小農が輸出許可を得て、コーヒーを国際市場へ直接販売できるようになった(2025年版)。",
    source: "USDA FAS「Coffee Annual - Ethiopia」(2019年版、2025年版、2026年版)",
  },
  {
    title: "ペルーのCOEは、2022〜2026年の1位がすべてカハマルカ産",
    text: "COEを運営するACEの結果ページによると、ペルーのカップ・オブ・エクセレンス(COE)の1位は、2022年から2026年まで5年連続で、カハマルカ地方の農園だった(2026年は審査の結果で、オークションは12月の予定)。2017年と2019年の1位もカハマルカ。2018年と2021年の1位は、クスコの農園だった。",
    source: "ACE「Perú 2017〜2026」結果ページ",
  },
];

function validateDiscoveryFacts() {
  const missing = DISCOVERY_FACTS.filter((fact) => !fact.source);
  if (missing.length > 0) {
    throw new Error(
      "[discoveryFacts] source未設定のエントリが見つかりました。出典を明記してください: " +
        missing.map((fact) => fact.title).join(" / ")
    );
  }
}

validateDiscoveryFacts();
