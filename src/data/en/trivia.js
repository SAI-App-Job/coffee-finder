// 豆知識・淹れ方・用語集の英訳。キーは、元データの日本語(豆知識=title、淹れ方=method / key / label、用語集=term)。
// 内容は元の日本語の訳で、事実や出典は変えていない(出典は元データのものをそのまま使う)。

// 豆知識(src/data/discoveryFacts.js)
export const DISCOVERY_FACTS_EN = {
  "「精選」と「精製」は別の言葉": {
    title: "\"Seisen\" and \"seisei\" are different words",
    text: "The process of turning coffee cherries into green beans is properly called \"seisen\" (精選). \"Seisei\" (精製) is a chemical term (turning a mixture into a pure substance) that is misused here by convention, but both spellings are used in actual shops.",
  },
  "クリスタルマウンテンはジャマイカ産ではない": {
    title: "Crystal Mountain is not from Jamaica",
    text: "Because the name resembles Blue Mountain it is easily misunderstood, but as a designated brand, \"Crystal Mountain\" refers to coffee from Cuba.",
  },
  "マンデリンとガヨマウンテンは排他的な関係": {
    title: "Mandheling and Gayo Mountain are mutually exclusive",
    text: "Both are from northern Sumatra, but which designated brand name you may use depends on whether the coffee is from around Takengon (the Gayo Mountain area). Even on the same island, they do not overlap.",
  },
  "スマトラ式は2段階で乾燥させる": {
    title: "The Sumatran method dries in two stages",
    text: "\"Wet-hulled\" processing, used for Mandheling and others, is a distinctive process: a first drying at the farm, hulling at high moisture, and then a second drying. This is also why the green beans turn dark green.",
  },
  "同じ「G1」でも国が違えば意味が違う": {
    title: "The same \"G1\" means different things in different countries",
    text: "Ethiopia's G1 is the top grade with 0-3 defects (per 300 g). Indonesia's G1 allows about 0-11 defects, so the same label has a different level of strictness.",
  },
  "ブルーマウンテンは商標で守られている": {
    title: "Blue Mountain is protected by a trademark",
    text: "Jamaica's JACRA (the agricultural commodities regulatory authority) exclusively holds the name \"Blue Mountain\" as a trademark, and only certified companies may use it.",
  },
  "ゲイシャはエチオピア原産": {
    title: "Gesha originates in Ethiopia",
    text: "The Gesha (Geisha / Gesha) variety, known for its showy aroma, actually originates in Ethiopia, not Panama. It became famous when lots grown on Panamanian farms fetched high prices at auction.",
  },
  "フレーバーホイールの生みの親": {
    title: "Where the flavor wheel came from",
    text: "The SCA's Coffee Taster's Flavor Wheel is based on the Sensory Lexicon of WCR (World Coffee Research), which was created at Kansas State University.",
  },
  "スペシャルティの基準は「点数」から「4つの軸」へ": {
    title: "The specialty standard moves from \"a score\" to \"four axes\"",
    text: "In 2024 the SCA moved from the single standard of \"a cupping score of 80 or above\" to an evaluation system called CVA, which combines four elements: physical, descriptive, affective and extrinsic.",
  },
  "ハワイには「ハワイ産と名乗れる最低ライン」がある": {
    title: "Hawaii has a minimum bar for calling coffee \"Hawaiian\"",
    text: "Under Hawaii state law, green coffee shipped out of state may not be labeled \"Hawaii coffee\" unless it meets Hawaii No. 3 grade or better. If it does not, it must be clearly labeled in large letters as \"OFFGRADE COFFEE.\"",
  },
  "タンザニアは輸出まで一つの機関が管理": {
    title: "Tanzania manages everything through export with one agency",
    text: "The Tanzania Coffee Board is an unusual type of government body that, by law, centrally manages bean grading, auction operation and even export permits.",
  },
  "ブラジルは世界初の格付け国": {
    title: "Brazil was the first country to grade coffee",
    text: "In 1836 Brazil introduced the world's first standardized coffee grading system. The origins of today's COB (Brazilian Official Classification) go back that far.",
  },
  "ブラジルの「タイプ1」は実在しない": {
    title: "Brazil's \"Type 1\" does not really exist",
    text: "In Brazil's defect-count grades (No. 2 to 8), the top label \"No. 1\" exists only as a theoretical standard; in actual distribution, No. 2 is effectively treated as the highest grade.",
  },
  "グアテマラだけの輸出税": {
    title: "An export tax unique to Guatemala",
    text: "In Guatemala, 1% of export value is charged as the only export tax and serves as the operating funds of Anacafé (the national coffee association). It is a system rarely seen in other countries.",
  },
  "最低輸出基準がある国とない国": {
    title: "Countries with and without a minimum export standard",
    text: "Colombia stipulates by law that coffee below Excelso cannot be exported, while neighboring Guatemala has no minimum export grade, and even low-quality coffee can be exported - a contrasting system.",
  },
  "インドネシアには輸出者団体が2つある": {
    title: "Indonesia has two exporters' associations",
    text: "The existence of two similarly named exporters' associations, \"AEKI\" and \"GAEKI,\" is because one split off after an internal dispute. Which is the official representative body is said to be still in dispute.",
  },
  "イエメンには公的な等級認証機関が事実上ない": {
    title: "Yemen effectively has no public grade certification body",
    text: "Because of the civil war, the Standardization, Metrology and Quality Control Organization (SMA) is not functioning, and even famous brands like Mocha Mattari have no official grade standard or classification. Quality verification relies on private organizations and importers.",
  },
  "ベトナムはロブスタが9割超": {
    title: "Over 90% of Vietnam's coffee is Robusta",
    text: "Vietnam, the world's second-largest coffee producer, is one of the few major producers where Robusta accounts for over 90% of production. It is used around the world as a raw material for canned and instant coffee.",
  },
  "「フレーバー」には2つの意味がある": {
    title: "\"Flavor\" has two meanings",
    text: "\"Flavor\" as in taste and aroma, and \"flavor\" as shorthand for \"flavored coffee\" (coffee with an artificial scent added) are entirely different things. While developing the parser for this app, we nearly confused the two.",
  },
  "香りにも専門用語の使い分けがある": {
    title: "Aromas have their own technical terms",
    text: "The \"fragrance\" that comes from ground coffee and the \"aroma\" that rises from the brewed liquid are technically distinguished as different smells.",
  },
  "「シティロースト」はニューヨーク発祥": {
    title: "\"City roast\" comes from New York",
    text: "The roast level name \"City roast\" comes from the fact that this roast level was the most popular in New York City.",
  },
  "昔はヨーロッパの国ごとに好みの焙煎度が違った": {
    title: "In the past, preferred roast levels differed by European country",
    text: "In the early 20th century, coffee roasting cultures clearly differed by country: Britain preferred lighter roasts, while France and Italy preferred darker roasts.",
  },
  "「ヘアルーム」は品種名ではない": {
    title: "\"Heirloom\" is not a variety name",
    text: "\"Heirloom,\" often seen in descriptions of Ethiopian coffee, is not the name of a specific variety but a collective name for Ethiopian native varieties, said to number in the thousands.",
  },
  "コーヒーの木の寿命は20〜30年": {
    title: "A coffee tree lives 20-30 years",
    text: "Once a variety is planted it is grown for a long time, so choosing a variety is a weighty decision for producers that affects the next 20-30 years.",
  },
  "ジャマイカは2025年のハリケーンで収穫の4割を失った": {
    title: "Jamaica lost 40% of its harvest to a hurricane in 2025",
    text: "Hurricane Melissa in October 2025 is reported to have destroyed about 40% of Jamaica's mature crop.",
  },
  "グアテマラには300を超える微気候がある": {
    title: "Guatemala has more than 300 microclimates",
    text: "Thanks to active and dormant volcanoes and rich biodiversity, Guatemala is said to have more than 300 microclimates.",
  },
  "コロンビアは地域で収穫期が真逆になる": {
    title: "In Colombia, harvest seasons are reversed by region",
    text: "In Colombia, near the equator, the timing of the main and secondary harvests is swapped between Huila in the north and Nariño and others in the south, so there is effectively a harvest all year across the country.",
  },
  "ケニアのSL28はカシス風味の立役者": {
    title: "Kenya's SL28 is the star behind the blackcurrant flavor",
    text: "The variety SL28, selected in the 1930s and 40s, has deep, drought-resistant roots, and its malic-acid-dominant structure produces the blackcurrant-like flavor characteristic of Kenyan coffee.",
  },
  "ブラジルの生産地はある年の大霜害で移動した": {
    title: "Brazil's growing areas shifted after one year's great frost",
    text: "After the great frost of 1975, producers in the hard-hit south moved to Minas Gerais, where frost is less common, creating today's pattern of major growing areas.",
  },
  "コロンビア・ケニア・タンザニアは「同じ仲間」": {
    title: "Colombia, Kenya and Tanzania are \"in the same group\"",
    text: "In the world coffee price indicator (I-CIP), these three geographically distant countries alone form a price group called \"Colombian Milds.\" What they share is not geography but the quality of their processing: fully washed, high-grown coffee.",
  },
  "エチオピアは価格上「ブラジルの仲間」": {
    title: "On price, Ethiopia is \"in Brazil's group\"",
    text: "In the price indicators of the International Coffee Organization (ICO), Ethiopia is classified in the same \"Brazilian Naturals\" group as Brazil. The character of the origins is the opposite, but they are grouped on the processing axis of \"natural processing.\"",
  },
  "コーヒー価格の重み付けは生きている": {
    title: "The weighting of coffee prices is a living thing",
    text: "The weights of the four groups that make up the world coffee price indicator (I-CIP) are reviewed periodically as the structure of world production changes - for example, from \"13/24/29/34%\" in 2005 to \"14/20/31/35%\" in 2007.",
  },
  "「80点基準」はSCA自身が2021年に卒業していた": {
    title: "The SCA itself moved on from the \"80-point standard\" in 2021",
    text: "The standard \"specialty coffee = a cupping score of 80 or above\" was actually replaced by the SCA itself in 2021 with the qualitative definition \"coffee that has high market value because of its characteristics.\" However, the old standard is still widely used as industry common knowledge.",
  },
  "コーヒー鑑定士資格「Qグレーダー」の運営元が変わった": {
    title: "The operator of the Q Grader coffee-assessor qualification has changed",
    text: "The \"Q Grader\" qualification for assessing coffee quality by international standards was run by the CQI (Coffee Quality Institute) from 2003, but from October 2025 it was fully transferred to the SCA. The new system is based on the CVA (the four-axis evaluation system).",
  },
  "ロブスタの鑑定士はウガンダが認定する": {
    title: "Robusta assessors are certified by Uganda",
    text: "Separately from the Arabica Q Grader qualification, the Robusta version of the Q Grader is internationally certified by a single country's government agency, the Uganda Coffee Development Authority (UCDA).",
  },
  "「コーヒーのオリンピック」はブラジルのオークションから始まった": {
    title: "The \"Olympics of coffee\" began as a Brazilian auction",
    text: "The international competition Cup of Excellence originated in an online auction project called \"Best Brazil\" held in Brazil in 1999. The ICO (International Coffee Organization) was also involved in the funding at its founding.",
  },
  "「緑のカエル」は合併で生まれたロゴ": {
    title: "The \"green frog\" is a logo born of a merger",
    text: "Rainforest Alliance, the \"green frog\" familiar from sustainability certification, is a combined brand formed in 2018 by merging with UTZ (founded by a Guatemalan producer and a Dutch roaster).",
  },
  "SCAJ誕生のきっかけは「コーヒークライシス」だった": {
    title: "SCAJ was born out of the \"coffee crisis\"",
    text: "Behind the birth of the Specialty Coffee Association of Japan (SCAJ, established in 2003) was a sense of alarm over the \"coffee crisis,\" when international prices hit record lows in 2001-02 and exhausted both producing and consuming countries.",
  },
  "サパティスタ運動が今のメキシココーヒーの姿を作った": {
    title: "The Zapatista movement shaped Mexican coffee as it is today",
    text: "The 1994 uprising of the Zapatista Army of National Liberation (EZLN) arose from opposition over the land system. Land redistribution after the uprising meant that Chiapas did not move toward large plantations, shaping the smallholder-centered production structure that continues today.",
  },
  "内戦が皮肉にも伝統品種を守った": {
    title: "The civil war ironically protected traditional varieties",
    text: "During El Salvador's civil war of 1979-1992, in the 1980s when many Central American countries were replanting with high-yield varieties, the country's farms were left abandoned, and as a result a high proportion of the traditional varieties Typica, Bourbon and Pacamara was preserved.",
  },
  "ルワンダのコーヒー復興を導いたのは女性たちだった": {
    title: "Women led the revival of Rwandan coffee",
    text: "After the 1994 genocide, women have led the revival of the coffee industry as the main operators of cooperatives - for example, the Maraba cooperative was launched to support the independence of women who had lost their husbands.",
  },
  "パナマゲイシャは1kgあたり3万ドルを超えた": {
    title: "Panamanian Gesha passed 30,000 dollars per kg",
    text: "In 2004, a Gesha lot from Hacienda La Esmeralda sold at a record price for the time and was said to have \"changed the industry.\" Records have been broken repeatedly since, and in 2025 a world record of 30,204 dollars per kg was set.",
  },
  "タンザニアには「自国だけの」等級規格がない": {
    title: "Tanzania has no grading standard of its own",
    text: "Tanzania has no coffee grading standard of its own and uses \"EAS 130:1999,\" the standard common to the East African Community (EAC). The secretariat is actually based in Arusha, Tanzania, but Uganda has also stated in its submission to the ICO that it complies with the same standard, making it a real example of several East African countries sharing a standard.",
  },
};

// 淹れ方(src/data/brewGuide.js の BREW_METHODS)。キーは method
export const BREW_METHODS_EN = {
  "ペーパードリップ": {
    method: "Paper drip (pour over)",
    tagline: "The most common brewing method. Brings out the character of the beans clearly",
    ratio: "15 g coffee : 250 ml water (1:16-17; the SCA Golden Cup standard is 55 g/L, about 1:18)",
    temp: "92-96°C (the SCA standard is 90-96°C)",
    time: "About 2 min 30 sec to 3 min",
    grindSize: "Medium-fine (about 400-600 microns)",
    steps: [
      "Put the medium-fine grounds in a paper filter",
      "Pour water over all the grounds and let it bloom for about 30 seconds (this releases gas and evens out the extraction)",
      "Pour in 2-3 stages, moving in a spiral from the center outward",
      "Pour the next before the water has drained completely, so a little water always remains",
      "When you reach the target amount, remove the dripper even if water remains (to avoid extracting off-flavors)",
    ],
    pairing: "Suits light to medium roasts (Light to City), bringing out their showy acidity",
    calibration: "If the brew takes less than 2 minutes, grind finer; if it takes more than 3.5 minutes, grind coarser",
  },
  "フレンチプレス": {
    method: "French press",
    tagline: "A metal filter extracts the oils too, for a full-bodied cup",
    ratio: "18 g coffee : 250 ml water (1:12-14)",
    temp: "93-96°C",
    time: "4 minutes of immersion",
    grindSize: "Coarse (about 800-1,000 microns)",
    steps: [
      "Put the coarse grounds in the press",
      "Pour in water and stir lightly to combine the grounds and water",
      "Put on the lid and let it steep for 4 minutes",
      "Slowly press down the plunger (a metal filter)",
      "After brewing, move the coffee to another container right away, because leaving the grounds in the water leads to over-extraction",
    ],
    pairing: "Suits medium-dark to dark roasts (Full City to French), letting you feel the body clearly",
    calibration: "Coarse is the rule. If too fine, fine particles remain on the tongue and cause off-flavors and over-extraction",
  },
  "エアロプレス": {
    method: "AeroPress",
    tagline: "Extraction pushed through by air pressure. A clean taste in a short time",
    ratio: "16 g coffee : 220 ml water (around 1:14; recipes vary widely)",
    temp: "80-85°C (somewhat low)",
    time: "1-2 minutes",
    grindSize: "Medium-fine (coarser than espresso, somewhat finer than paper drip)",
    steps: [
      "Set the filter in the cap and rinse it with hot water (to prevent the paper taste from transferring)",
      "Put the grounds in the chamber, pour in water and stir lightly",
      "Wait about 1 minute, then attach the cap and slowly press the plunger",
      "The hiss of escaping air signals that the brew is finished",
    ],
    pairing: "The lower water temperature works well with light roasts with delicate acidity",
    calibration: "Because it is a sealed system (the temperature drops less), variations in temperature show up directly in the result",
  },
  "水出し(コールドブリュー)": {
    method: "Cold brew",
    tagline: "A slow extraction with just water and time. Mellow with gentle acidity",
    ratio: "50 g coffee : 500 ml water (1:10, concentrate style)",
    temp: "Room temperature to cold water",
    time: "8-12 hours (slowly in the refrigerator)",
    grindSize: "Coarse (about the same as French press to slightly coarser)",
    steps: [
      "Put the coarse grounds in a dedicated pot or a filter bag",
      "Pour in water and mix lightly to wet all the grounds",
      "Let it stand in the refrigerator for about 8-12 hours",
      "Strain out the grounds with a filter, and serve diluted with ice or water to taste",
    ],
    pairing: "Bitterness and acidity become gentler, so you can enjoy the strength of dark roasts in a mellow form",
    calibration: "At low temperatures, the dissolution of melanoidins (brown compounds) and the like is gentle, and extraction of acidic and browning-type components is lower than with hot water",
  },
};

// 抽出理論(EXTRACTION_VARIABLES)。キーは key
export const EXTRACTION_VARIABLES_EN = {
  grind: {
    title: "Grind size",
    summary: "The finer it is, the more surface area, and the faster and more it extracts",
    detail:
      "Grinding increases the surface area exponentially (even 10 g of coffee ground to 400 microns is said to exceed 1 square meter of surface area). The larger the surface area, the more surface is in contact with water and the faster extraction goes. One experiment reported that an extra-fine grind (average 282 microns) dissolved 93% of its components in 5 minutes, while an extra-coarse grind (average 1,057 microns) reached only 61% in the same 5 minutes.",
  },
  roast: {
    title: "Roast level",
    summary: "The darker the roast, the more porous the bean, and the more readily it dissolves at the same grind",
    detail:
      "Light-roasted beans keep a dense, compact structure, but in dark-roasted beans heating breaks down the internal structure and makes them porous and brittle. As a result, even brewed with the same grind and the same recipe, dark roasts tend to have a higher extraction rate. In practice, adjustments are made such as grinding dark roasts coarser (or using less coffee) and grinding light roasts finer to make up for surface area. Note that because light-roasted beans are denser, they actually contain more caffeine than dark roasts per equal volume (such as a spoonful).",
  },
  temperature: {
    title: "Water temperature",
    summary: "The higher it is, the faster and stronger the extraction, but too high brings bitterness and astringency",
    detail:
      "The higher the water temperature, the faster acids, sugars, oils and bitter components all dissolve. At too low a temperature (below about 90°C as a guide), the extraction of sugars and oils cannot keep up and only the acidity stands out, tending toward a thin, sour \"under-extracted\" result. Conversely, at too high a temperature extraction proceeds too fast and even astringent components (tannins, etc.) dissolve in excess, tending toward a bitter, harsh \"over-extracted\" result. The SCA standard gives 90-96°C (195-205°F) as a guide.",
  },
  time: {
    title: "Brew time",
    summary: "Determined together with grind size and temperature. Even at the same grind, longer contact moves toward over-extraction",
    detail:
      "Coffee's components dissolve in a fixed order. First the acidic and aromatic components in the first tens of seconds, then the sweet, well-balanced flavor components in the middle, and the bitter and astringent components dissolve more toward the end. If the brew time is too short you get an \"under-extracted\" cup of only acidic components, and if it is too long (or the grind is so fine that it takes too long) even the bitter and astringent components of the final stage dissolve in excess, giving \"over-extraction.\" In other words, grind size, water temperature and time are not independent variables: the three together always determine how far the extraction has gone (the extraction yield).",
  },
};

// 未抽出・適正・過抽出(EXTRACTION_DIAGNOSIS)。キーは label
export const EXTRACTION_DIAGNOSIS_EN = {
  "未抽出(Under-extraction)": {
    label: "Under-extraction",
    cause: "Any one (or several) of: water temperature too low / grind too coarse / brew time too short",
    taste: "Thin, sour, a salty note, a short flavor finish",
  },
  "適正抽出": {
    label: "Proper extraction",
    cause: "The SCA standard gives an extraction yield of 18-22% and a strength (TDS) of 1.15-1.35% as a guide",
    taste: "A balance of sweetness, acidity and bitterness, with a long-lasting flavor finish",
  },
  "過抽出(Over-extraction)": {
    label: "Over-extraction",
    cause: "Any one (or several) of: water temperature too high / grind too fine / brew time too long",
    taste: "Bitter, astringent, harsh, a heavy aftertaste",
  },
};

// 用語解説(src/data/glossary.js の GLOSSARY_TERMS)。キーは term(精選方法の見出しは「日本語(English)」の形)
export const GLOSSARY_EN = {
  "ブレンド(Blend)": {
    term: "Blend",
    summary: "Coffee made by combining beans from several origins.",
    detail:
      "Refers to a product made by combining green coffee from several origins. It is not merely for uniformity; it has two main purposes. One is \"creating a new taste\" - designing, by blending several lots, an intended balance of flavors that a single origin cannot provide. The other is \"achieving consistency that reduces year-to-year variation in taste\" - beans from a single farm or single lot vary from year to year with weather and harvest conditions, but by combining several lots the same taste can be offered all year round. Under the rules of the All Japan Coffee Fair Trade Council, a blend product name that carries a specific origin or brand name must contain at least 30% green coffee of that origin or brand (see \"Designated brands\" for details). Note that it is a misconception that \"blend means lower quality\": the quality standards of specialty coffee are a separate axis of evaluation unrelated to whether the origin is single or multiple, and high-quality \"specialty blends\" combining several origins also exist (see \"Specialty coffee\" for details). For the classification along the single / multiple origin axis, see also \"Straight\" and \"Single origin.\"",
  },
  "ストレート": {
    term: "Straight",
    summary: "Beans from a single country only. Blending several farms within the same country is allowed.",
    detail:
      "An industry term derived from Japanese coffeehouse culture for coffee beans whose origin is limited to a single country. It does not require a single farm: even if several farms and lots in the same country are blended, it can be called straight as long as the country of origin is one (this is how it differs from a \"blend\"). Interestingly, there is no English technical term that corresponds exactly to \"straight.\" In the English-speaking world coffee is basically described in two categories, \"single origin\" and \"blend,\" and the Japanese \"straight\" is a Japanese-only term (with no corresponding English term) expressing an intermediate category of its own - looser than a single farm and stricter than a blend. See also the explanation of \"Single origin.\"",
  },
  "シングルオリジン(Single Origin)": {
    term: "Single origin",
    summary: "Coffee made from a single origin (country, region, farm, etc.). How strictly this is meant varies with context.",
    detail:
      "One of the basic categories used in the English-speaking world to describe the origin makeup of coffee, and a concept paired with \"blend.\" Although they share the idea of \"a single origin,\" in practice the term has a range of strictness depending on context: it can refer to a single country, or be used in the strict sense of a single farm or single lot. The Japanese \"straight\" (beans from a single country, regardless of farm) roughly corresponds to the looser usage of single origin. Because the distinctive term \"straight\" is well established in Japan, the notation \"single origin\" itself is only seen on imported bean packages and in explanations at specialty shops, and there is no widely established Japanese translation. See also the explanations of \"Blend\" and \"Straight.\"",
  },
  "精選(せいせん)": {
    term: "Seisen (processing)",
    summary: "The processing steps up to extracting green beans from the coffee cherry.",
    detail:
      "\"Seisen\" refers to the process of turning harvested coffee cherries into green beans. A similar word is \"seisei\" (精製), but this properly refers to a different concept, \"the process of turning a mixture into a pure substance,\" and in the coffee industry it is an easily confused misuse or conventional spelling. In product descriptions, notations such as \"seisei processing: ...\" are actually used.",
  },
  "ウォッシュド(Washed)": {
    term: "Washed",
    summary: "A method in which the pulp and mucilage are washed off with water before drying.",
    detail:
      "The steps are: remove the pulp, ferment in a tank and remove the mucilage, wash with water, and dry. Characterized by clean, clear acidity with few off-flavors. Traditional in regions such as Guatemala and Kenya where plenty of water is available.",
  },
  "ナチュラル(Natural)": {
    term: "Natural",
    summary: "A method in which the cherries are dried whole and hulled all together.",
    detail:
      "Because no water is used, it is possible even in mountainous areas. Fruity, with strong sweetness and a distinctive character. Seen on small farms in Brazil and Ethiopia, among others.",
  },
  "ハニー(Honey)": {
    term: "Honey",
    summary: "A method in which only the pulp is removed and the mucilage is left on during drying.",
    detail:
      "Intermediate in character between washed and natural. Depending on the color during drying it is subdivided into white, yellow, red and black honey, and the closer to black, the more natural-leaning the flavor. Often seen in Central America.",
  },
  "ウェットハルド(Wet Hulled)": {
    term: "Wet-hulled",
    summary: "A two-stage drying method specific to Indonesia, also called the Sumatran method. The green bean is hulled at high moisture.",
    detail:
      "The sequence is: a first drying at the farm to about 40% moisture (called Gabah / Asalan), hulling while still at a high 30-35% moisture, and then a second drying. A method developed in a hot, rainy climate where long drying is difficult. Characterized by a heavy body and earthy flavor, and the green beans turn dark green.",
  },
  "アナエロビック(Anaerobic)": {
    term: "Anaerobic",
    summary: "A processing method that ferments in a sealed tank with oxygen cut off.",
    detail:
      "A process in which harvested cherries or parchment are fermented while immersed in a sealed, low-oxygen tank. Because oxygen concentration, temperature and time can be controlled more finely than in the open fermentation tanks of traditional washed and natural processing, distinct fruitiness and wine-like flavors tend to arise. There are many variations, such as methods that adopt \"carbonic maceration\" from winemaking and \"anaerobic natural,\" which is combined with natural and honey processing, and it has drawn worldwide attention since the mid-2010s, prompted by barista competitions.",
  },
  "焙煎度(ロースト)": {
    term: "Roast level",
    summary: "How far the green beans are roasted. In Japan it is expressed in eight levels (Light to Italian).",
    detail:
      "From light to dark: Light → Cinnamon → Medium → High → City → Full City → French → Italian. The sounds of the beans cracking, called first crack and second crack, serve as a guide to roast level. There is also the objective measure of the \"Agtron value,\" which measures bean color with infrared; the higher the number, the lighter the roast. At some shops, it is not a fixed attribute of the product but an option you choose when ordering.",
  },
  "グレード(等級)": {
    term: "Grade",
    summary: "A classification showing the quality of green coffee. The criteria differ by producing country.",
    detail:
      "Criteria differ by country: altitude (Guatemala's SHB, etc.), screen size = bean size (Kenya's AA, etc.), defect count (Brazil's No. 2-8, Ethiopia's G1-5, etc.), cup quality and so on. Even the same \"G1\" label has different strictness in Ethiopia and Indonesia, so it needs to be understood together with the country.",
  },
  "特定銘柄": {
    term: "Designated brands",
    summary: "The brand-labeling rules in Japan, with 14 types, set by the All Japan Coffee Fair Trade Council.",
    detail:
      "A voluntary industry regulation in Japan under which 14 brands such as Blue Mountain and Kilimanjaro cannot be used in a product name unless the origin conditions are met. When used in a blend, at least 30% of the green coffee by weight must be used. Note that these are not brands officially certified by the producing country; they are only Japanese labeling rules.",
  },
  "スペシャルティコーヒー": {
    term: "Specialty coffee",
    summary: "Redefined as the qualitative definition: \"coffee that has high market value because of its distinctive characteristics.\"",
    detail:
      "It was once defined as coffee that scored 80 or above on the COE-style cupping form (eight items scored 0-8 with a base of 36 points added), but in 2021 the SCA (Specialty Coffee Association, international headquarters) replaced this overly technical definition with the qualitative definition: \"coffee that is recognized by its distinctive characteristics and has higher value in the market because of them.\" In 2024 it put in place a concrete evaluation system, the \"CVA (Coffee Value Assessment),\" to operate this idea. However, the old \"80-point standard\" is still widely used as industry common knowledge.",
  },
  "Coffee Value Assessment(CVA)": {
    term: "Coffee Value Assessment (CVA)",
    summary: "A new framework, put in place by the SCA in 2024, that evaluates coffee on four axes.",
    detail:
      "It combines four axes: physical evaluation (color, defective beans, moisture, etc.), descriptive evaluation (recording aroma, flavor, texture and aftertaste objectively in standardized language; equivalent to a tasting note), affective evaluation (impressions based on the preferences of evaluators and markets), and extrinsic evaluation (certifications, origin traceability, processing method information, etc.). The design philosophy emphasizes not condensing value into a single score.",
  },
  "ダイヤルイン(Dial-in)": {
    term: "Dial-in",
    summary: "The work of fine-tuning brewing conditions little by little to approach the ideal cup.",
    detail:
      "Originally an English expression meaning to turn a dial on an instrument to set a number precisely (to dial in a setting). Even with the same beans and the same recipe, the best brewing conditions change with the days since roasting, humidity and the condition of the beans, so the adjustment work of changing the dose, water amount, grind size, water temperature, brew time and so on little by little to approach the intended balance of sweetness, acidity and body came to be called \"dialing in\" in espresso settings, and it has become an established technical term across the specialty coffee industry, including hand drip. It is not something you get right in one try; it refers to the process itself of repeating brew, taste and adjust.",
  },
};

// 用語解説の分類
export const GLOSSARY_CATEGORIES_EN = {
  "分類": "Classification",
  "加工": "Processing",
  "精選方法": "Processing method",
  "焙煎": "Roasting",
  "格付け": "Grading",
  "抽出": "Brewing",
};
