# Verifiering 2026-10-01

Körda i lokal utvecklingsmiljö. Inga verkliga DeDu-data användes.

| Kontroll | Resultat |
|---|---|
| Django-testsvit, PostgreSQL 18.6 | 81 tester godkända i hela sviten efter sista backendändringen, inklusive samtidig kodåterställning, åtkomstskydd krypterad bilagebackup och AI-behörigheter/anropsgränser samlad fastighetsvy samt rapportgruppering/budgetjämförelser |
| Frontendens sparlogik | 3 tester godkända: nätverksavbrott, osäkert 502-svar, versionskonflikt |
| TypeScript och produktionsbygge | Godkänt; byggverktyget varnar för en större JavaScript-fil |
| npm beroendegranskning vid installation | 0 rapporterade sårbarheter; punktkontroll, ingen långsiktig garanti |
| OpenAPI-generering | 0 fel och 0 varningar |
| Djangos driftskontroll | Godkänd med produktionsinställningar |
| Compose-konfiguration | Godkänd syntaxkontroll; inga containrar körda |
| Lokal återläsning | 8 objekt, 9 arbetsorder och 1 bilaga återlästa; SHA-256/relationskontroll godkänd |
| Lokal tidpunktsåterställning | Krypterad basbackup/WAL; två bilagor verifierade; post efter återställningspunkt utesluten. Se [protokoll](pitr-test.json). |
| Manuellt webbläsarprov | Demoinloggning, översikt, ärendeskapande och serverkvittens, budgetvy på dator och 390 px mobilbredd, återkallad session återgår till inloggning nya säkerhetsvyer, AI-startvy och låst inställningsförhandsvisning, fastighetsöversikt, försenat urval och historik, grupperade rapporter med klickunderlag och jämförelse av syntetiska budgetversioner; besiktningsplanering, kontrollsvar, fastställande och åtgärdsorder vid 390/320 px |

Backendtesterna verifierar bland annat direktlänkar/sökning/export över organisationsgränser, entreprenörens tilldelningar, skydd av ekonomiska/interna uppgifter, idempotens, samtidig versionskonflikt, månadsslut/skottår/sommartidsdatum, decimalavrundning, låst budget, append-only-historik, publik tokenåtkomst, nyckellån, mätarbyte, återkallad rapportåtkomst, CSV-formelskydd, PDF/Excel, dokumentkontroll, CSRF och TOTP-återspelning.

Det nya PITR-provet verifierar även en bilaga skapad efter basbackupen. Säkerhetstesterna täcker kodernas engångsanvändning, två administratörer, återkallade sessioner och behörighetsbegränsning.

Den tidigare logiska återläsningen tog cirka 2,23 sekunder för den lilla syntetiska datamängden. Tiden är inte representativ för verksamhetens volym och får inte användas som bevis för RTO.

AI-transporten har endast provats med simulerad leverantör. Inga verkliga nycklar eller externa AI-anrop användes. Se [AI-dokumentationen](AI.md).

## Inte verifierat

- Containerbygge eller drift på en extern server; lokal Docker-motor saknas.
- HTTPS och mejlleverans på organisationens domän, ClamAV-tjänsten och faktisk S3-lagring.
- Krypterad fjärrbackup och tidpunktsåterställning via produktionskedjan Docker/pgBackRest/S3, inklusive faktiska RPO/RTO och larmleverans.
- Belastningsmålet 100 samtidiga användare / 10 000 objekt / 1 miljon historikposter.
- WCAG 2.2 AA, skärmläsare, komplett mobiltest och användarmätningen 30 procent snabbare.
- Alla 85 rapportvarianter och alla verksamhetsspecifika beräkningsregler.

Kör testerna på målmiljön före godkännande. Tester är regressionsevidens, inte ett intyg om att alla möjliga dataförluster eller intrång har uteslutits.

## Besiktningar 0.6

Sex nya tester täcker hela kedjan anmärkning–order–ombesiktning–verifiering, PDF, databaslås, rättelser, dubblettskydd, ofullständiga svar, versionskonflikter, organisationsgränser, bilagereferenser, återöppnade brister och krav på senaste ombesiktning.

Mobilprovet omfattade syntetisk SBA med fyra punkter, obligatorisk anmärkningskommentar, sparstatus, fastställande och tilldelning av åtgärdsorder. Vid 320 px var sidans uppmätta bredd 320 px utan horisontell sidrullning. Slutprovet av det rättade ombesiktningsformuläret är nu godkänt: planering, sparning, fastställande, kvittering av kopplad arbetsorder och explicit verifiering. Översikten visade därefter noll öppna anmärkningar. Ingen fysisk iOS-/Android-enhet, kamerauppladdning eller fullständig WCAG-granskning har testats.
