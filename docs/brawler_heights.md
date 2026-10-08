# Brawler roster: official heights and sprite scale

Research 2026-10-08. Purpose: calibrate the roster's sprite sizes (game.json `scale`) against each other from the characters' published heights.

## Sources, best first

1. **SNK official, KOF anniversary site** (kofaniv.snk-corp.co.jp, English, 2017, current KOF profile values). The live pages no longer answer, so these were read from the Wayback Machine:
   `http://web.archive.org/web/2017/http://kofaniv.snk-corp.co.jp/english/character/index.php?num=<id>`
   with ids `terry ryo ralf robert yamazaki billy kyo iori mai yashiro geese big krauser kdush rugal goenitz`. All 16 KOF-side fighters were read there.
2. **SNK official, Samurai Shodown anniversary site** (samuraianiv.snk-corp.co.jp, still live): `https://samuraianiv.snk-corp.co.jp/english/character/<haohmaru|genjuro|hanzo>/index.php`. It gives the Edo units too (shaku/sun, kanme).
3. **SNK Wiki (snk.fandom.com)**, read through its MediaWiki API (the HTML pages sit behind Cloudflare). It gives older per-game values and cites game sites (KOF 2000, KOF XII, KOF XIII, KOF MI-A, Garou 15th). It is the only source found for Kim Sue-il, Rosa and World Heroes Hanzo.
4. **Double Dragon Wiki (doubledragon.fandom.com)**: the Neo Geo game's personal data for Billy Lee and Cheng-Fu, given in feet and pounds, so it probably comes from the US manual or promo material. The wiki does not name its source.

I found no Neo Geo Freak or Gamest mook scan online that gives heights. The Japanese Wikipedia character articles give no 身長/体重. The KOF XV official pages no longer list height or weight.

## Table

Anchor: Terry = 182 cm = 100 px, so target px = height_cm / 1.82.
"Today px" is our in-game standing height (shadow included), where it has been measured.

| Fighter (game.json) | Official height | Weight | Source | Target px | Today px | Scale vs today | Conflicts / notes |
|---|---|---|---|---|---|---|---|
| Terry Bogard (`terry`) | 182 cm | 83 kg | kofaniv `num=terry` | **100** (anchor) | 100 | 1.00 | Weight has changed over the years (SNK Wiki): 77 kg in FF2–RB and KOF94–98, 82 kg in RBS–KOF2002, 81 kg in MotW, 83 kg from KOF2003 on. Height has always been 182. |
| Ryo Sakazaki (`ryo`) | 179 cm | 75 kg | kofaniv `num=ryo` | 98.4 | 106 | **0.93** | 68 kg in the AOF games and KOF94–98, 75 kg from KOF99 on (SNK Wiki). Today he stands 6 % taller than Terry even though he is 3 cm shorter. |
| Ralf Jones (`ralf`) | 188 cm | 110 kg | kofaniv `num=ralf` | 103.3 | – | – | Same in KOF XII and MI-A (SNK Wiki). |
| Robert Garcia (`robert`) | 180 cm | 85 kg | kofaniv `num=robert` | 98.9 | – | – | |
| Ryuji Yamazaki (`yamazaki`) | 192 cm | 96 kg | kofaniv `num=yamazaki` | 105.5 | – | – | 110 kg in Fatal Fury and KOF2002/UM, 96 kg in KOF2003 (SNK Wiki). |
| Billy Kane (`billy`) | 179 cm | 78 kg | kofaniv `num=billy` | 98.4 | – | – | The SNK Wiki cites the same values from the KOF XIII and MI-A official sites. |
| Kyo Kusanagi (`kyo`) | 181 cm | 75 kg | kofaniv `num=kyo` | 99.5 | – | – | 180 cm in KOF94–98, 181 cm from KOF99 on (SNK Wiki). For a KOF98 sprite, 180 cm gives 98.9 px. |
| Iori Yagami (`iori`) | 182 cm | 76 kg | kofaniv `num=iori` | 100 | – | – | 79 kg in KOF95–98, 76 kg from KOF99 on (SNK Wiki, citing the KOF2000 site). |
| Mai Shiranui (`mai`) | 165 cm | 48 kg | kofaniv `num=mai` | 90.7 | – | – | The weight is stable. Only her BWH figures changed (KOF2003 and NGBC sites). |
| Yashiro Nanakase (`yashiro`) | 190 cm | 99 kg | kofaniv `num=yashiro` | 104.4 | – | – | |
| Geese Howard (`geese`) | 183 cm | 82 kg | kofaniv `num=geese` | 100.5 | – | – | |
| Mr. Big (`mr_big`) | 187 cm | 81 kg | kofaniv `num=big` | 102.7 | – | – | |
| Wolfgang Krauser (`krauser`) | 200 cm | 145 kg | kofaniv `num=krauser` | 109.9 | 121 | **0.91** | |
| K' (`k_dash`) | 183 cm | 65 kg | kofaniv `num=kdush` | 100.5 | – | – | |
| Rugal Bernstein (`rugal`) | 197 cm | 103 kg | kofaniv `num=rugal` | 108.2 | – | – | **Weight conflict:** 103 kg (KOF94, and the anniversary site) against 145 kg (KOF95–2002, SNK Wiki). The height is the same in both. |
| Goenitz (`goenitz`) | 193 cm | 88 kg | kofaniv `num=goenitz` | 106.0 | – | – | |
| Haohmaru (`haohmaru`) | 173 cm (5 shaku 7 sun) | 64 kg (17 kanme) | samuraianiv `haohmaru` | 95.1 | – | – | 69 kg in Warriors Rage (SNK Wiki). |
| Genjuro Kibagami (`genjuro`) | 182 cm (6 shaku) | 82.5 kg (22 kanme) | samuraianiv `genjuro` | 100 | – | – | |
| Hattori Hanzo, SS (`hanzo_ss2`) | 179 cm (5 shaku 9 sun, "estimate") | 60 kg (16 kanme) | samuraianiv `hanzo` | 98.4 | – | – | SNK itself labels the figure an estimate, because he is a ninja whose details are unknown. |
| Hanzo, World Heroes (`hanzo`) | 175 cm | 69 kg | SNK Wiki "Hanzo Hattori (World Heroes)" | 96.2 | – | – | Fan wiki only. This is an ADK game and I found no official ADK page. |
| Kim Sue-il (`kim`) | 180 cm | 73 kg | SNK Wiki "Kim Sue-il" | 98.9 | 115 (≈105.8 after the planned ×0.92) | **0.86** (or 0.935 on top of the 0.92) | Fan wiki only. **Name confirmed:** Kim Sue-il (김수일 / 金秀一, キム・スイル), Taekwondo + bōjutsu, a Kizuna Encounter protagonist and Rosa's partner. He was also a striker for Kim Kaphwan in KOF2000. He is not "Kim Young Mok". |
| Rosa (`rosa`) | 165 cm | 48 kg | SNK Wiki "Rosa" | 90.7 | – | – | Fan wiki only. Same figures as Mai. |
| Billy Lee, DD Neo Geo (`billy_lee`) | 5′9″ ≈ 175 cm | 154 lb ≈ 70 kg | Double Dragon Wiki "Billy Lee" (Neo Geo section) | 96.2 | 95 (after ×0.8) | **1.01** | **Conflict:** Double Dragon V gives 6′2″/210 lb and DD Advance gives 175 cm/72 kg. Use the Neo Geo game's 5′9″. Some search summaries wrongly attach the DD V numbers to the Neo Geo game. |
| Cheng-Fu (`cheng_fu`) | 5′9″ ≈ 175 cm | 167 lb ≈ 76 kg | Double Dragon Wiki "Cheng-Fu" | 96.2 | 94 | **1.02** | Fan wiki only, unnamed source (the imperial units point to the US manual or promo material). |

24 of 24 fighters have a published height. 19 come from SNK's own sites: 16 from the KOF anniversary site and 3 from the Samurai Shodown anniversary site. The other 5 (Kim, Rosa, WH Hanzo, Billy Lee, Cheng-Fu) are fan-wiki only.

### Caveats for using target px

- An official height is an upright height. Our "today" heights are fighting-stance heights with the shadow included, and stances differ: Terry leans forward, while Krauser and Kim stand tall. A pure height ratio will therefore make the upright fighters look slightly too tall. Before trusting a scale factor, compare the same pose type (an idle stance) and either remove the shadow or count it for everyone.
- SNK's own sprites do not follow these numbers either. In KOF98, Ryo (179 cm) is drawn taller than Terry (182 cm), and our 106 vs 100 px shows it. The profiles are character-sheet facts and were never a pixel spec.

### Biggest mismatches today

| Fighter | Today | Target | Factor |
|---|---|---|---|
| Kim Sue-il | 115 | 98.9 | 0.86. The planned ×0.92 (to ≈106) is still about 7 px too tall. |
| Krauser | 121 | 109.9 | 0.91 |
| Ryo | 106 | 98.4 | 0.93 |
| Billy Lee | 95 | 96.2 | 1.01 (fine) |
| Cheng-Fu | 94 | 96.2 | 1.02 (fine) |

## What I found on sprite-scale consistency between series

- **KOF94 redrew everyone.** In the KOF94 developer interview (from the mook *All About KOF'94*, translated by shmuplations), the team says: "At first we would just use assets directly from the source games for characters from Fatal Fury and Art of Fighting, but in the end we redrew every character, which took up an enormous amount of time." So KOF94 is a single-scale re-draw and not a merge of FF and AOF sprites. The interview also notes that "Of the many characters in KOF'94 with slim builds, Robert got the biggest slimming down", that Heavy D! ended up much bigger than the others before anyone noticed, and that Joe received the biggest graphical update of the FF cast. Sources: https://shmuplations.com/kof94/ , https://itsfantastic.moe/all-about-the-king-of-fighters-94-developer-interview/ , https://www.culturaneogeo.com/imagenes/entrevistas/kof94eng
- **Scaling-camera games draw large.** Art of Fighting, Savage Reign and Kizuna Encounter draw large sprites and shrink them with the LSPC zoom as the fighters separate. Contemporary reviews describe this ("huge sprites and a camera that zooms in-and-out", "large scaling sprites, similar to Art of Fighting": fightersgeneration.com Savage Reign / Kizuna pages, destructoid). This explains why Kim measures 115 px at zoom $CC (≈80 %), and why the Kizuna and DD Neo Geo fighters needed the ×0.8 pre-shrink. A source drawn for a zoom camera is not drawn at KOF's fixed scale.
- **Pixel heights of KOF characters.** I found no developer statement on how many pixels tall KOF characters are drawn. Forum posts on this were only hobbyist (e.g. chronocrash "How big should sprites be?") and none were authoritative. The only usable reference is our own measurement: KOF98 Terry is 100 px standing, shadow included.
- **Samurai Shodown.** SS also uses a zoom camera and draws its fighters large, but I found no published statement about its sprite scale relative to KOF. The SS anniversary site gives heights in Edo units (shaku/sun), which shows that SNK keeps one canonical height per character across series.
- **SNK has one canonical height per character.** It reuses the same height across FF, AOF, KOF, MI and XII–XV. Only the weights drift between eras, so the heights are a stable cross-series yardstick even though no SNK game ever rendered them literally.
