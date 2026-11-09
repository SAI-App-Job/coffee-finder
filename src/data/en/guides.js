// 国内競技会・精選方法の解説・特定銘柄・品種ガイドの英訳。内容は元の日本語の訳で、事実や出典は変えていない。

// 国内競技会(src/data/japanCompetitions.js)。キーは id
export const JAPAN_COMPETITIONS_EN = {
  jbc: {
    name: "Japan Barista Championship",
    tagline: "The pinnacle of the domestic competitions, contesting espresso, milk beverage and signature beverage",
    history:
      "A competition run by the SCAJ since 2003. Within the time limit, competitors serve three kinds of drinks - \"espresso,\" \"milk beverage\" and \"signature beverage (an original drink)\" - and are judged not only on taste but on the appropriateness, accuracy and consistency of the whole process up to serving. The rules follow those of the world competition, the World Barista Championship (WBC), and the JBC winner represents Japan at the WBC. In 2007, when the WBC was held in Asia for the first time in Tokyo, Miyamae finished 4th in the world and won the Best Cappuccino award at the same time.",
    latestResult:
      "In 2024, Hiroki Ito (伊藤大貴) of Sarutahiko Coffee won (the company's first JBC win). He represented Japan at the WBC the following year, 2025. Ito also won the 2026 competition (October).",
  },
  jhdc: {
    name: "Japan Hand Drip Championship",
    tagline: "A competition specializing in \"hand drip,\" the brewing method most familiar in Japan",
    history:
      "A competition run by the SCAJ that began in 2012. It is characterized by original rules that incorporate Japan's own culture and the background of the times; it adopted a tournament format in 2014, and in 2016 the score sheet was greatly improved to incorporate expressions unique to Japan, such as flavor and texture. The same beans are used in both the qualifying rounds and the final, and the final is contested in two parts: a blind-judged drip competition and a free competition with a presentation.",
    format:
      "Judging centers on the taste evaluation of drip coffee with no additives. In the qualifying round, the uniformity of two brews of different amounts is an important evaluation item, testing the skill of finishing coffee of different amounts to the same taste through pouring technique alone. In the final, beans distributed before the event are used, and overall professional skill, including uniformity of extraction, is evaluated.",
    latestResult:
      "After 新田和雄 (Nitta; Nitta Coffee, Fukui Prefecture) won in 2023 and 2024, his eldest daughter 新田衣祥 (Nitta) won in 2025 and his wife 新田千香子 (Nitta) in 2026, the first time in JHDC history that members of one family have won four years in a row (the family relationships are from Nitta Coffee's press release).",
  },
  jsc: {
    name: "Japan Siphonist Championship",
    tagline: "A competition contesting siphon brewing skills and original drinks, linked to a world championship that originated in Japan",
    history:
      "Began in 2003 as the siphon division of the JBC (Japan Barista Championship). Competitors contest the brewing skills of regular blend coffee and of each competitor's own signature beverage made with it. It grew year by year, and in 2007 was reborn as an independent competition, the \"Japan Siphonist Championship.\" In 2009 the world-scale \"World Siphonist Championship (WSC)\" was held for the first time anywhere, making it a world competition that originated in Japan. The winner competes in the world championship as Japan's representative, together with representatives of other countries.",
  },
  jlac: {
    name: "Japan Latte Art Championship",
    tagline: "A competition of artistry, originality and reproducibility in latte art",
    history:
      "It originated in a latte art competition held as an exhibition at the SCAJ trade show from 2006. In 2008, JBC 2008 runner-up 岡田章宏 (Okada) represented Japan at the WLAC (the world competition) and placed 3rd in the world, which led to its launch in 2009 as the official competition \"JLAC.\"",
    format:
      "Within an 8-minute competition time, competitors serve two each of three kinds of drinks: caffè latte / cappuccino, caffè macchiato and a designer's beverage. In addition to the artistry, originality, reproducibility and complexity of the design, making the two served designs as symmetrical as possible is also a factor in scoring high. The winner competes in the World Latte Art Championship as Japan's representative.",
  },
  jctc: {
    name: "Japan Cup Tasters Championship",
    tagline: "A competition of the skill and speed of \"cupping,\" picking the one different-tasting cup out of three",
    history:
      "Inspired by a world competition that made the cupping skill basic to specialty coffee into a contest, the first JCTC was held in Japan in September 2009. In the world competition that year (Cologne, Germany), a Japanese competitor took part, and Goto placed 3rd in the world.",
    format:
      "For each question three cups are lined up, and only one of them contains a coffee of a different taste. Competitors identify this one using the \"cupping\" method. They compete on the number of correct answers within 1 minute per question and 8 questions in total (8 minutes in all), and when the number of correct answers is equal, the shorter time taken to answer decides.",
  },
  jcrc: {
    name: "Japan Coffee Roasting Championship",
    tagline: "A competition with a unique judging method found in no other event, in which competitors declare the flavor they aim for before roasting",
    history:
      "Started as the Japan selection for the new competition \"Coffee Roasting Challenge (CRC)\" (renamed the \"World Coffee Roasting Championship\" in 2013), which WCE (World Coffee Events) introduced at its Vienna event in 2012. The SCAJ holds it for the domestic market in order to send the winner to the world competition.",
    format:
      "In conventional roasting competitions (such as the SCAA Roaster's Guild Retreat and the SCAJ Roast Masters Retreat), only the cup quality of the result was judged, with no advance declaration. In the JCRC, competitors declare in advance, in a \"roast log,\" what flavor characteristics they will aim for, and then roast. On the final day, the competitor whose actual roast result comes closest to the declaration wins.",
    latestResult:
      "In 2016, Hiraku Kondo (近藤啓) of Itsuka Kohiya (Hiratsuka, Kanagawa Prefecture) won on his first appearance. He represented Japan at the World Coffee Roasting Championship the following year, 2017, and placed 7th.",
  },
  jcigsc: {
    name: "Japan Coffee in Good Spirits Championship",
    tagline: "A competition of original cocktails that combine coffee and liquor",
    history:
      "To send a Japanese representative to the Europe-born world competition, the \"World Coffee In Good Spirits Championship (WCIGSC),\" the first JCIGSC was held in 2013, after a demonstration competition in February 2012.",
    format:
      "Within a 10-minute competition time, competitors make a total of four drinks: two Irish coffees and two alcohol-based designer drinks (hot or cold) made with coffee. The rules follow those of the WCIGSC, and the winner competes in the world competition as Japan's representative.",
  },
  jbrc: {
    name: "Japan Brewers Cup",
    tagline: "A competition contesting skill with a wide range of brewing tools, not limited to paper and flannel drip",
    history:
      "A competition run by the SCAJ that was newly established in 2014. In contrast to the JHDC, which specializes in paper and flannel drip, in the JBrC competitors can freely choose manual brewing tools without mechanical power, such as paper drip, flannel drip, French press and AeroPress. It is positioned as the domestic selection for the world competition, the \"World Brewers Cup (WBrC),\" and the winner earns the right to compete in the WBrC as Japan's representative. In 2014, JBrC 2014 winner Ichisei Obiro (尾籠一誠, Saza Coffee Co., Ltd.) competed as Japan's representative at the WBrC 2014 held in Rimini, Italy.",
    format:
      "In the qualifying rounds, the official roasted beans of the event are used in a \"compulsory service\" judged purely on taste, while in the semifinals and final, each competitor brings beans of their own choosing in an \"open service,\" showing off the appeal of those beans through brewing technique and presentation.",
  },
  kikikohi: {
    name: "Coffee Tasting Championship (Kiki-Kohi)",
    tagline: "Limited to SCAJ Coffee Meister qualification holders, a competition of the accuracy of sensory evaluation (cupping) of coffee",
    history:
      "A cupping competition held by the SCAJ Training Committee on the event stage of the SCAJ trade show, open to holders of the SCAJ Coffee Meister certification. The 10th was held in 2024 and the 11th in 2025, and the 12th is scheduled for 2026. The winner is honored as the \"Coffee Meister Kiki-Kohi King.\"",
    format:
      "In the qualifying round and final, competitors contest the accuracy of their cupping, and the winner is decided by sudden death among those with the most correct answers. Questions are themed around differences in producing country, processing method and grading. According to past winners, all kinds of beans are asked, including commercial coffee as well as specialty coffee, and canephora (Robusta) as well as Arabica has been asked.",
  },
};

// 競技会の出典リンクの名前(日本語 → 英語)
export const COMPETITION_SOURCE_LABELS_EN = {
  "JBC概要": "JBC overview",
  "JHDC概要": "JHDC overview",
  "JSC概要": "JSC overview",
  "JLAC概要": "JLAC overview",
  "JCTC概要": "JCTC overview",
  "JCRC概要": "JCRC overview",
  "JCIGSC概要": "JCIGSC overview",
  "JBrC概要": "JBrC overview",
  "過去の競技結果": "Past results",
  "審査員プログラム(競技詳細)": "Judge program (competition details)",
  "第12回利き珈琲選手権(概要・歴代王者インタビュー)": "12th Coffee Tasting Championship (overview and interviews with past champions)",
  "2026年の競技結果": "2026 results",
};

// 競技会の略称(日本語 → 英語)。"利き珈琲" だけが日本語表記
export const COMPETITION_ABBR_EN = { "利き珈琲": "Kiki-Kohi" };

// 精選方法の解説(src/data/explanations.js の PROCESSING_EXPLANATIONS)
export const PROCESSING_EXPLANATIONS_EN = {
  "ウォッシュド": "The steps are: remove the pulp, ferment in a tank and remove the mucilage, wash with water, and dry. Characterized by clean, clear acidity with few off-flavors.",
  "ナチュラル": "A method in which the cherries are dried whole in the sun or by machine and then hulled all together. Fruity, with strong sweetness and a distinctive character.",
  "ハニー": "A method in which only the pulp is removed and the mucilage is left on during drying. Intermediate in character between washed and natural.",
  "ウェットハルド": "A two-stage drying method specific to Indonesia. The green bean is hulled at high moisture, producing a heavy body and earthy flavor.",
  "アナエロビック": "A process that ferments the cherries in a sealed container. A relatively new technique that tends to produce strong, distinctive wine- and fruit-like flavors.",
  "マウンテンウォータープロセス(デカフェ用)": "A decaffeination method in which green coffee is soaked in water saturated with flavor components other than caffeine, so that only the caffeine dissolves and is extracted.",
  "インフューズド": "A technique in which fruit or spices are added to a sealed container during processing (fermentation) and fermented together with the coffee cherries. The aroma from the fruit transfers to the beans. Unlike \"flavored coffee,\" in which flavoring is added after roasting, it is considered one of the techniques of specialty coffee, as a flavor created during processing.",
  "インフューズドハニー": "A technique combining the honey process (only the pulp is removed and the mucilage is left on during drying) with a step in which fruit or spices are added and fermented. Unlike \"flavored coffee,\" in which flavoring is added after roasting, it is considered one of the techniques of specialty coffee, as a flavor created during processing.",
};

// 特定銘柄の解説(DESIGNATED_BRAND_EXPLANATIONS)。キーは銘柄名(日本語)
export const DESIGNATED_BRAND_EXPLANATIONS_EN = {
  "ブルーマウンテン": "A designated brand defined as Arabica coffee beans produced in Jamaica's Blue Mountain district. JACRA (the Jamaica Agricultural Commodities Regulatory Authority) holds the trademark, and only certified companies may use the name.",
  "ハイマウンテン": "A designated brand defined as Arabica coffee beans produced in Jamaica's High Mountain district.",
  "ジャマイカ": "A designated brand that refers to Jamaican-grown Arabica coffee beans other than Blue Mountain and High Mountain.",
  "クリスタルマウンテン": "Arabica coffee beans produced in Cuba under that country's export standard. Despite the similar name, it has no relation to Jamaica's Blue Mountain.",
  "グアテマラアンティグア": "A designated brand defined as Arabica coffee beans produced in the Antigua district of Guatemala.",
  "コロンビアスプレモ": "Arabica coffee beans produced in Colombia under that country's export standard. \"Supremo\" is also Colombia's own grade label, so the word has a double meaning.",
  "モカ・ハラー": "A designated brand defined as Arabica coffee beans produced in the Harar district of Ethiopia. Names such as \"Mocha Sidamo\" are not legal designated brands but customary industry nicknames.",
  "モカ・マタリ": "A designated brand defined as Arabica coffee beans produced in Yemen.",
  "キリマンジャロ": "A designated brand defined as Arabica coffee beans produced in Tanzania (excluding those from the Bukoba district).",
  "トラジャ": "A designated brand defined as Arabica coffee beans produced in the Toraja district of Sulawesi, Indonesia.",
  "カロシ": "A designated brand defined as Arabica coffee beans produced in the Kalossi district of Sulawesi, Indonesia.",
  "ガヨマウンテン": "A designated brand defined as Arabica coffee beans produced in the Takengon district of Sumatra, Indonesia.",
  "マンデリン": "A designated brand defined as Arabica coffee beans produced in North Sumatra and Aceh, Indonesia (excluding the Gayo Mountain district).",
  "ハワイコナ": "A designated brand defined as Arabica coffee beans produced in the South Kona and North Kona districts of Hawaii, USA.",
};

// 特定銘柄の一覧(src/data/designatedBrands.js)。キーは銘柄名(日本語)
export const DESIGNATED_BRANDS_EN = {
  "ブルーマウンテン": { name: "Blue Mountain", note: null },
  "ハイマウンテン": { name: "High Mountain", note: null },
  "ジャマイカ": { name: "Jamaica", note: "Other than Blue Mountain and High Mountain" },
  "クリスタルマウンテン": { name: "Crystal Mountain", note: "From Cuba (not included in the map's countries)" },
  "グアテマラアンティグア": { name: "Guatemala Antigua", note: null },
  "コロンビアスプレモ": { name: "Colombia Supremo", note: null },
  "モカ・ハラー": { name: "Mocha Harar", note: "Only from the Harar district" },
  "モカ・マタリ": { name: "Mocha Mattari", note: null },
  "キリマンジャロ": { name: "Kilimanjaro", note: "Excluding the Bukoba district" },
  "トラジャ": { name: "Toraja", note: "From the Toraja district of Sulawesi" },
  "カロシ": { name: "Kalossi", note: "From the Kalossi district of Sulawesi" },
  "ガヨマウンテン": { name: "Gayo Mountain", note: "From the Takengon district of Sumatra" },
  "マンデリン": { name: "Mandheling", note: "Excluding the Gayo Mountain district" },
  "ハワイコナ": { name: "Hawaii Kona", note: null },
};

// 品種ガイド(src/data/varietyGuide.js)。キーは lineage(日本語)。varieties は元の表記から日本語の読みを除いたもの
export const VARIETY_GUIDE_EN = {
  "ティピカ系統": {
    lineage: "Typica lineage",
    tagline: "The origin of coffee. Elegant, clean taste but low yield",
    varieties: ["Typica", "Pache", "Kent", "Java"],
    note:
      "One of the oldest lineages, from when coffee originating in Ethiopia spread around the world via Yemen. Along with Bourbon, it is an ancestor of almost all cultivated varieties. Its low yield and weakness to disease put it at an economic disadvantage, but it has a lasting reputation for its elegant acidity and clean taste.",
  },
  "ブルボン系統": {
    lineage: "Bourbon lineage",
    tagline: "Sweeter than Typica, with a well-balanced taste",
    varieties: ["Bourbon", "SL28", "SL34", "Pacas", "Villa Sarchi"],
    note:
      "A natural mutation of Typica discovered on Réunion (formerly Bourbon Island). It has more body and sweetness than Typica and a relatively high yield. Countries have each carried out their own mutation selections, such as Kenya's SL28 and SL34 (known for a blackcurrant-like flavor), El Salvador's Pacas and Costa Rica's Villa Sarchi.",
  },
  "カトゥーラ/カトゥアイ系統": {
    lineage: "Caturra / Catuai lineage",
    tagline: "A lineage focused on productivity, with a compact tree shape and high yield",
    varieties: ["Caturra", "Catuai", "Mundo Novo", "Maragogype", "Pacamara"],
    note:
      "Caturra is a mutation of Bourbon, with a low, compact tree and a high yield. Catuai is an artificial cross of Mundo Novo (a natural cross of Typica and Bourbon) and Caturra, and is widely grown in Brazil. Maragogype is a mutation with very large beans (and a low yield). Pacamara is a cross of Pacas and Maragogype, tends to give large beans and complex flavors, and often earns high marks at El Salvador's COE (Cup of Excellence).",
  },
  "サルチモール/カティモール系統": {
    lineage: "Sarchimor / Catimor lineage",
    tagline: "Crossbreeds with resistance to coffee leaf rust",
    varieties: ["Catimor", "Sarchimor", "Ruiru 11", "Batian", "Parainema", "Marsellesa"],
    note:
      "A group of crossbreeds with the Timor Hybrid (a natural cross of Arabica and Robusta) as a parent, bred to resist coffee leaf rust (a serious disease that attacks the leaves). Marsellesa also belongs to this lineage: it was selected from a cross of the Timor Hybrid and Villa Sarchi (released in 2009). Their cup quality has been said to be inferior to the traditional Bourbon and Typica lineages, but advances in breeding are improving quality. The planted area is expanding as climate change raises the risk of disease.",
  },
  "特殊・高付加価値品種": {
    lineage: "Specialty varieties",
    tagline: "A standout floral quality reminiscent of jasmine and bergamot",
    varieties: ["Geisha/Gesha", "Starmaya", "Heirloom (Ethiopian native varieties)"],
    note:
      "Geisha originates in Ethiopia, and became famous overnight when lots grown on Panamanian farms (Hacienda La Esmeralda and others) set record auction prices among the highest ever. It is characterized by a showy aroma reminiscent of jasmine and bergamot. Starmaya is a recently developed F1 hybrid (a first-generation artificial cross that draws on genetic diversity, and can be propagated by seed), a new generation of variety aiming to combine high productivity and quality. Heirloom is a collective name for the countless native varieties traditionally grown in Ethiopia, not a single variety name.",
  },
};
