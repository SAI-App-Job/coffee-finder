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
    text: "Under Hawaii's administrative rules, Hawaii-grown green coffee that does not meet the quality standards of Hawaii No. 3 may not be sold with a Hawaiian place name. It must instead be labeled \"offgrade\" or simply \"coffee,\" with no geographic reference.",
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
    text: "The variety SL28, selected in the 1930s, has deep, drought-resistant roots, and its malic-acid-dominant structure produces the blackcurrant-like flavor characteristic of Kenyan coffee.",
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
  "「モカ」は港の名前でもある": {
    title: "\"Mocha\" is also the name of a port",
    text: "The coffee name \"Mocha\" is also the name of a port in Yemen. A 2023 report by FAO and IFC describes the port of Al Mokha as historically a major hub for coffee exports out of Yemen and says that mocha coffee is associated with this port. The ICO's history of coffee likewise says that Moca, the great port of its time, has a name that is today synonymous with a kind of coffee.",
  },
  "コスタリカは独立の年に、貧しい人々へコーヒーの苗を配った": {
    title: "Costa Rica handed out coffee plants to the poor in the year of independence",
    text: "According to the geographical-indication specification (Pliego de Condiciones) of ICAFE, the Costa Rican coffee institute, the first seeds arrived at the end of the 18th century, but it is only after 1808 that there is certainty, backed by historical evidence, that an important coffee-growing activity began in Costa Rica. In 1821, the year of independence, the municipal body of San José (the \"corporación josefina\") distributed coffee plants free of charge to the destitute.",
  },
  "「AA」はふるいの番号で決まる等級(ケニア・タンザニア)": {
    title: "\"AA\" is a grade defined by screen size (Kenya and Tanzania)",
    text: "Under Kenya's coffee regulations (2019), AA is a flat bean that passes through screen 21 and is retained on 18 (7.2 mm). Under Tanzania's Coffee Industry Regulations (2013), AA means at least 90% retained on screen 18 (with at most 8-10% on screen 17). In both, AA is a size grade set by screen number, though it is written differently. The East African Standard (EAS 130:1999) states that grading by size and shape is only a fair estimate of coffee quality.",
  },
  "グアテマラの「SHB」は、標高1,370m超のコーヒー": {
    title: "Guatemalan \"SHB\" means coffee grown above 1,370 m",
    text: "In a chart by Anacafé, the Guatemalan coffee association, coffee types are divided by altitude. SHB is above 4,500 ft (1,370 m), Semi-Hard / Hard is 3,500-4,500 ft (1,066-1,370 m), and Extra Prime / EPW is 2,500-3,500 ft (764-1,066 m).",
  },
  "ルワンダは、アフリカで最初にCOEを開いた国": {
    title: "Rwanda was the first African country to host a Cup of Excellence",
    text: "A blog post (August 2018) by the ACE (Alliance for Coffee Excellence), which runs the Cup of Excellence, says that Rwanda was the first African country to host a Cup of Excellence (CoE) competition, with the first CoE there dating back to 2008.",
  },
  "コーヒーに「生産の割当」があった時代": {
    title: "When coffee had production quotas",
    text: "According to the FAQ of the ICO (International Coffee Organization), the ICO operated a quota system, under which coffee supplies in excess of consumer requirements were withheld from the market, on and off from 1962 to 1989. In 1989 the system was suspended because members failed to agree on quota distribution. The ICO does not currently operate a quota system.",
  },
  "エチオピアは2019年に、一部の小農の直接輸出を認めた": {
    title: "Ethiopia opened direct exports to some smallholders in 2019",
    text: "According to USDA FAS reports, smallholder farmers account for 90 percent of Ethiopia's coffee production (2026 edition). The Ethiopia Commodity Exchange (ECX) was established in 2008 (2019 edition). A policy reform in 2019 allowed smallholder farmers who own at least two hectares of land to obtain export licenses and sell their coffee directly to international markets (2025 edition).",
  },
  "ペルーのCOEは、2022〜2026年の1位がすべてカハマルカ産": {
    title: "Peru's Cup of Excellence: Cajamarca took first place every year from 2022 to 2026",
    text: "According to the results pages of the ACE, which runs the Cup of Excellence, first place at Peru's Cup of Excellence (CoE) went to a farm in the Cajamarca region for five years in a row, from 2022 to 2026 (for 2026 these are the jury results; the auction is planned for December). First place in 2017 and 2019 also went to Cajamarca. In 2018 and 2021, first place went to a farm in Cusco.",
  },
};

// 淹れ方(src/data/brewGuide.js の BREW_METHODS)。キーは method
export const BREW_METHODS_EN = {
  "ペーパードリップ": {
    method: "Paper drip (pour over)",
    tagline: "A method that extracts through a paper filter. The result tastes clear, and the character of the beans comes through directly (HARIO)",
    ratio: "12 g coffee : 160 ml water (AJCA example; the SCA standard is 55 g/L, about 1:18)",
    temp: "About 95°C (AJCA). The SCA standard is 92-96°C",
    time: "30-second bloom; all the water through within 3 minutes (HARIO)",
    grindSize: "Medium-fine (AJCA example)",
    steps: [
      "HARIO's basic V60 recipe: fold the sealed edge of the paper filter and fit it snugly inside the dripper",
      "Pour hot water over the filter until it is wet all over (this rinses off the paper smell and warms the equipment). Discard the water that dripped into the server",
      "Put in the coffee and shake it gently to level it",
      "Slowly pour twice the weight of the coffee in water from the center until the whole bed is wet, then let it bloom for 30 seconds after finishing the pour",
      "Pour the water in three stages (each pour = 4 times the weight of the coffee). Pour in a spiral from the center, without letting water hit the paper directly, and keep the whole brew within 3 minutes until the water has dripped through",
      "When the water has dripped through into the server, it is done",
    ],
    pairing: "",
    calibration: "HARIO: pouring quickly gives a crisper taste, pouring slowly a deeper, richer one (V60). AJCA: a short brew time makes the coffee \"sour and thin\", and a long one \"bitter and harsh\"",
  },
  "フレンチプレス": {
    method: "French press",
    tagline: "Put the coffee straight into the pot, pour in hot water and press the filter down, and you get a coffee with a deep flavor (HARIO press)",
    ratio: "Standard amount of coffee for one cup: 12-13 g (medium grind) or about 15 g (coarse grind) (AJCA)",
    temp: "About 95°C (AJCA basic principles)",
    time: "About 1 minute to bloom; once the swirling of the coffee has calmed down (about 2 minutes), press (HARIO)",
    grindSize: "Medium to coarse (AJCA table)",
    steps: [
      "Pour in enough hot water to wet all the grounds and wait about 1 minute (bloom)",
      "Pour in the water and, once the swirling of the coffee has calmed down (about 2 minutes), push the filter down",
    ],
    pairing: "The AJCA explains that the components of the coffee are extracted thoroughly, so you can enjoy the taste of the beans directly",
    calibration: "",
  },
  "エアロプレス": {
    method: "AeroPress",
    tagline: "The manufacturer's official instructions (Signature Brew). Described as having a smooth, rich, full-bodied flavor",
    ratio: "16-18 g of coffee (1 heaping scoop); water up to the \"4\" mark on the chamber",
    temp: "85°C (if you have no temperature-control kettle, use boiling water)",
    time: "Stir for about 3 seconds, wait 60 seconds, then press (30 seconds for a medium-fine grind)",
    grindSize: "Medium, or medium-fine (two official recipes)",
    steps: [
      "Heat water to 85°C (if you have no temperature-control kettle, use boiling water)",
      "Pull the plunger out of the chamber completely",
      "Put a paper filter in the filter cap and twist the cap onto the chamber",
      "Stand the chamber on a sturdy mug and add the coffee (16-18 g, or 1 heaping scoop)",
      "Shake gently to level the coffee and pour water up to the \"4\" mark on the chamber (some coffee dripping through is normal)",
      "Stir gently for about 3 seconds. Quickly insert the plunger about 1/2 inch into the chamber, then pull it up slightly to create a vacuum that stops the dripping, and wait 60 seconds (30 seconds for medium-fine grounds)",
      "Press the plunger with gentle, constant pressure (do not push too hard). When you hear the hissing sound begin and end, the coffee is done",
    ],
    pairing: "",
    calibration: "",
  },
  "水出し(コールドブリュー)": {
    method: "Cold brew",
    tagline: "A method that steeps the coffee in water. Known for a clean sweetness (HARIO immersion cold brew)",
    ratio: "Fill with water up to the product's marked line (HARIO)",
    temp: "Put it in the refrigerator and wait (HARIO)",
    time: "About 8 hours (HARIO immersion type). The drip type takes 6-8 hours (for 10 cups) (AJCA)",
    grindSize: "A medium-fine grind of a dark roast is recommended (HARIO)",
    steps: [
      "Put the coffee (a medium-fine grind of a dark roast is recommended) in the strainer",
      "Pour in water up to the product's marked line so that the coffee is wet through",
      "Put it in the refrigerator and wait. It is ready in about 8 hours. If you make it overnight, you can enjoy it in the morning",
    ],
    pairing: "",
    calibration: "A 2018 paper in Scientific Reports, \"Acidity and Antioxidant Activity of Cold Brew Coffee\", found that hot-brewed coffee had a higher concentration of total titratable acids than cold-brewed coffee.",
  },
};

// 抽出理論(EXTRACTION_VARIABLES)。キーは key
export const EXTRACTION_VARIABLES_EN = {
  principles: {
    title: "Six basic principles for brewing delicious coffee",
    summary: "The basic principles listed by the All Japan Coffee Association (AJCA)",
    detail:
      "The AJCA lists six basic principles for brewing delicious coffee: use fresh roasted beans, grind to suit the equipment, use an amount of coffee suited to the equipment, use suitable water, use clean equipment, and keep to a suitable brewing temperature and time. The SCA protocols list the measurable elements of brewing as water, the ratio of coffee to water, the particle size distribution, the contact time between coffee and water, temperature, turbulence (the mixing action of water flowing through and around the coffee particles to achieve a uniform extraction of soluble material), and filter media.",
  },
  strength: {
    title: "Strength and extraction yield",
    summary: "TDS (strength), extraction yield and the coffee-to-water ratio are linked",
    detail:
      "An SCA magazine article says that Lockhart (in a 1957 paper) proposed that how good a coffee is can be described by measuring how much of the grounds dissolved into the liquid (TDS), and pointed out that TDS and the extraction yield (PE) are linked by how much water is used per mass of coffee (the brew ratio). The classic \"Coffee Brewing Control Chart\" puts TDS on the vertical axis, PE on the horizontal axis and the brew ratio as diagonal lines. The article names three limitations of that chart: it conflates sensory description with consumer preference, its zones are too fine (most experts cannot tell 17.9% from 18.1% extraction), and it leaves out the variety of flavors. It adds that the UC Davis Coffee Center is working on updating and expanding the chart. The AJCA says the best Brix (strength) for drip coffee is said to be around 1.4%.",
  },
  grind: {
    title: "Grind size",
    summary: "Match the grind to the equipment and to the contact time between coffee and water (AJCA, SCA)",
    detail:
      "The All Japan Coffee Association (AJCA) lists \"grinding to suit the equipment\" as one of the basic principles of brewing good coffee. Its table gives the standard amount of coffee for one cup as 6-8 g for extra-fine, 8-10 g for fine, about 10 g for medium-fine, 12-13 g for medium and about 15 g for coarse. The SCA protocols say the particle size distribution should match the time of coffee-to-water contact, with a guide of 1-4 minutes for fine, 4-6 minutes for drip and 6-8 minutes for coarse. In a brew-temperature study (Batali 2020), the grind size and overall brew time were adjusted to reach the target TDS and extraction yield.",
  },
  roast: {
    title: "Roast level",
    summary: "The darker the roast, the more porous the bean, and the more readily it dissolves at the same grind",
    detail:
      "Light-roasted beans keep a dense, compact structure, but in dark-roasted beans heating breaks down the internal structure and makes them porous and brittle. As a result, even brewed with the same grind and the same recipe, dark roasts tend to have a higher extraction rate. In practice, adjustments are made such as grinding dark roasts coarser (or using less coffee) and grinding light roasts finer to make up for surface area. Note that because light-roasted beans are denser, they actually contain more caffeine than dark roasts per equal volume (such as a spoonful).",
  },
  temperature: {
    title: "Water temperature",
    summary: "About 95°C is ideal (AJCA). The SCA says 92-96°C. A study reports little effect when TDS and extraction yield are matched",
    detail:
      "The All Japan Coffee Association (AJCA) says the ideal water temperature is what you get after the water has boiled and the pot is taken off the heat until the rolling surface has calmed down (around 95°C). The SCA Golden Cup standard gives the water temperature at the point of contact with the coffee as 200°F ± 5° (195-205°F), or 94.0°C ± 2° (92-96°C). On the other hand, Batali et al. (Scientific Reports 2020) drip-brewed at 87°C, 90°C and 93°C, adjusting the grind size and brew time to match TDS and extraction yield, and reported that the brew temperature had no appreciable impact on the sensory profile. They conclude that the profile is governed by differences in TDS and extraction yield rather than temperature, at least over the range of temperatures tested.",
  },
  time: {
    title: "Brew time",
    summary: "Determined together with grind size and temperature. Even at the same grind, longer contact moves toward over-extraction",
    detail:
      "Coffee's components dissolve in a fixed order. First the acidic and aromatic components in the first tens of seconds, then the sweet, well-balanced flavor components in the middle, and the bitter and astringent components dissolve more toward the end. If the brew time is too short you get an \"under-extracted\" cup of only acidic components, and if it is too long (or the grind is so fine that it takes too long) even the bitter and astringent components of the final stage dissolve in excess, giving \"over-extraction.\" In other words, grind size, water temperature and time are not independent variables: the three together always determine how far the extraction has gone (the extraction yield).",
  },
  water: {
    title: "Water",
    summary: "Alkalinity matters more than pH for the acidity of the cup (SCA magazine)",
    detail:
      "An SCA magazine article (25 Issue 9) says that when choosing water for coffee extraction, it is far more important to keep alkalinity within a certain range than pH. The perceived acidity of a coffee corresponds to the amount of acids extracted from the coffee minus the amount of alkalinity from the water. It adds that experimental measurements suggest the impact of total hardness on extraction efficiency is insignificant between 20 and 250 ppm CaCO3. The AJCA says that tap water contains impurities and chlorine, so it is best to use water that has passed through a water filter, and that soft water suits enjoying the taste of the coffee directly.",
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
      "A voluntary industry regulation in Japan under which 14 brands such as Blue Mountain and Kilimanjaro (defined in an appendix to the code) cannot be used in a product name unless the origin conditions are met. To call a product a \"(brand) blend,\" at least 30% of the green coffee used must be that brand. Note that these are not brands officially certified by the producing country; they are only Japanese labeling rules.",
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
