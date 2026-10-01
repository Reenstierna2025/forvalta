# Rapportanalys och budgetjämförelse · version 0.5

## Grupperade rapporter

Öppna **Rapporter → Rapportbyggare**. Välj rapportfamilj, organisation och befintliga datumfilter, därefter **Gruppera efter** och **Mått**. Enskilda poster finns kvar som standardval.

Grupperingarna är fördefinierade per rapportfamilj, exempelvis organisation, objekt, status, utförare, år och kontering. Alla rapportfamiljer stöder antal rapportposter. Budget/underhåll stöder även budget, möjlig finansiering och beviljad finansiering. Fakturaunderlag stöder belopp. Ingen fri formelskrivning erbjuds. Förbrukning, area och NKI-medelvärden summeras inte genom denna funktion eftersom enheter, överlappande objekt och beräkningsdefinitioner kräver separata regler.

Gruppering sker på rapportens visade fältvärden. Två objekt eller enheter med identiska namn hamnar därför i samma namngrupp; underlagsraderna bevarar sina post-ID. Det är inte en ny summeringsnivå i organisationshierarkin.

- Staplar och tabell visar samma serverberäknade grupper. Klick på en stapel/grupp öppnar exakt de rapportposter som ingår; arbetsorder kan öppnas vidare.
- Antal betyder rapportposter, inte alltid unika registerobjekt. Återkommande underhåll kan förekomma en gång per år/tillfälle.
- Belopp summeras med Decimal från rapportens redan avrundade rader. Möjlig och beviljad finansiering är separata mått.
- Saknade värden räknas separat. En grupp med enbart saknade belopp får null, inte noll. Ett null-gruppvärde skiljs från en faktisk text som heter ”Saknas”.
- Gruppval och mått följer med sparade mallar, arkiverade rapporter och API-baserad schemalagd rapportgenerering. Befintlig behörighetskontroll återanvänds.
- PDF/CSV/Excel exporterar grupperingen och valda gruppkolumner. Detaljunderlaget visas i vyn; välj **Enskilda poster** för att exportera detaljraderna. Excel får numeriska mått och jämförelsebelopp som tal.

Rapportens beräkningsversion är 1.1. Tidigare arkiverade rapporter behåller sina sparade underlag och versioner. Rapporterna materialiseras fortfarande i minnet; stora urval behöver en senare lösning med bakgrundsgenerering och strömmad export. Kopplingen till DeDus 85 rapportval är fortfarande inte verifierad.

## Budgetversioner

Öppna **Underhåll & budget → Jämför versioner**. Välj före och efter. Versionerna måste avse samma organisationsomfång, startår och antal år. Båda versionernas sparade organisationsomfång måste ligga inom användarens aktuella ekonomibehörighet.

Jämförelsen visar totalsumma före/efter, skillnad i SEK, fördelning per år samt tillagda, borttagna, ändrade och oförändrade åtgärder. Expandera en ändrad rad för att se före/efter för varje ändrat fält, inklusive mängd, pris, kostnadsfaktor, index, prisår, finansiering och kontering. Oförändrade rader kan döljas i vyn men ingår alltid i totalsummor och exporter.

**Kopiera före-version till nytt utkast** skapar en ny, fristående budgetversion med de sparade raderna från källan. Det fungerar även för en fastställd källa; originalet ändras inte. Ändra därefter utkastets åtgärdsår i den befintliga scenariovyn och jämför igen. Ändring av övriga antaganden direkt i ett scenario ingår ännu inte; sådana skillnader kan jämföras mellan separata sparade versioner skapade från ändrat planunderlag.

Nya versioner och kopior får stabila radnycklar som bevaras när en åtgärd flyttas. För äldre versioner utan radnycklar används åtgärds-ID och sparat år. En redan flyttad äldre rad kan därför visas som borttagen/tillagd. Om identiteten inte är entydig avbryts jämförelsen; systemet gissar inte. Ingen historisk fastställd version skrivs om i efterhand.

CSV, Excel och PDF innehåller samtliga jämförelserader med före/efter-fält och versionsmetadata. Årsfördelningen visas i webbgränssnittet och JSON-svaret; den är inte en separat flik i exportfilen. Exportlänkarna från vyn inkluderar de lästa versionsnumren och ger konflikt om någon version därefter har ändrats. Läs då in jämförelsen igen.

## Testning och avgränsning

Sju nya tester kontrollerar grupperingssummor, klickunderlag, organisationsgränser, godkända mått, saknade värden, kopiering av fastställd version, stabila identiteter vid flytt, belopps-/finansieringsskillnader, tillägg/borttagning, periodkrav, exportkonflikter och numeriska Excel-celler. Befintlig regression har också körts. Totalt finns nu 75 backendtester och tre frontendtester.

I webbläsaren har gruppering efter status, klick till underliggande arbetsorder samt budgetjämförelsen verifierats. Den lokala demonstrationen innehåller två tydligt märkta syntetiska budgetversioner: **Demo – grundplan 2026–2035** och **Demo – senarelagd åtgärd**. De ingår inte som verksamhetsdata i källkodspaketet eller en tom installation.

Kvarstår: fler mått och diagramtyper, ID-baserad gruppering av objekt med samma namn, korsvisa grupperingar, attestprocess, fler redigerbara scenarioantaganden, belastningsprov och verifiering mot de faktiska DeDu-rapporterna. Produktionsgodkännande är fortsatt separat.
