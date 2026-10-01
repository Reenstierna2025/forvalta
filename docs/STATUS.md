# Leveransstatus 0.6.1

Detta är en implementerad utvecklingspilot med databas och fungerande kärnflöden. Den uppfyller delar av etapp 1 och 2, samt grundregister från etapp 3. Etapperna är inte slutgodkända.

| Område | Implementerat | Återstår före full täckning |
|---|---|---|
| Organisation och åtkomst | Fyra nivåer, explicit grenbehörighet, roller, ekonomiflagga, ändringshistorik, återkallning, kontostängning och MFA-återställning | Tidsatta omorganisationer, delegering och verksamhetens identitets-/incidentrutiner |
| Fastigheter | Hierarki, mark/byggnad/lokal/rum/objekt, area, ägare/förvaltare, bilagor, samlad vy över hela objektträdet och sidindelad händelsehistorik | Hyresobjekt, strukturerade kontakter och historisk jämförelse av fältvärden |
| Arbetsorder | Prioritet, utförare, datum, status, checklistor, kommentarers synlighet, tid/material/kostnad | Personbokning med klockslag, kredit/rättelse av kostnader, rikare entreprenörsportal |
| Publik felanmälan | Godkända platser, idempotens, privat länk, begränsad återkoppling, e-postjobb | Publika fotobilagor, CAPTCHA vid behov och anpassad kvittensdesign |
| Ronder och besiktning | Intervall, kalender, checklistor, avvikelser, åtgärdsorder, SBA/skyddsrond/byggnadsmallar, bilagor per kontrollpunkt, låsta protokoll, rättelser, ombesiktning, explicit verifiering och PDF | Verksamhetsspecifika kravmallar, återkommande skapande av den nya protokolltypen och samlad kalenderkoppling |
| Underhåll | Mängd/pris/faktor/index, intervall, konto och två finansieringsfält | Fler konteringsdimensioner, delad finansiering och beslutsprocess |
| Budget | 1/5/10/30 år, decimalberäkning, utfall, fristående scenarier, låsning av fastställd version, kopiering till utkast och jämförelse rad för rad | Fler redigerbara scenarioantaganden och beslutsattester |
| Vård/SBA/träd/inventarier | Typade grundregister med ansvarig, referens och datum | Domänspecifika fält, vårdplansstruktur, trädinventering, fördjupade skyddsrondsmallar och inventariehändelser |
| Energi | Mätare, kronologiska avläsningar, mätarbyten, förbrukning med enheter | Normalårskorrigering, tariff/CO₂, mätarhierarkier och fördjupade analyser |
| Nycklar | Fysiska nycklar, unika aktiva lån, återlämning | Låsscheman, signering och kvittensdokument |
| Entreprenader/garantier | Grundregister, ansvarig och datum | Avtalsrader, bevakning, garantikoppling till arbete och attest |
| Rapporter | Tolv rapportfamiljer, kolumner, mallar, PDF/XLSX/CSV, arkiv, schemalagda skyddade länkar, godkända grupperingar/mått och klickbara staplar | Fler mått/diagram, ID-baserad gruppering, korsgruppering och alla verifierade DeDu-varianter |
| Dokument | Privata objekt, versionskedja, SHA-256, 20 MB, filvalidering, antiviruskoppling | Verifierad produktions-S3 och fjärrbackup, retention och återställning på målmiljön |
| AI-assistent | Krypterad leverantörsnyckel, arbetsorderunderlag, anropsgräns, källförteckning, godkända prioriteringsförslag | Verkligt leverantörsprov, fler adapterformat, budget/dokument/andra ändringar, retention och kvalitetsutvärdering |
| Drift | Compose, HTTPS, pgBackRest/WAL, krypterad dokument-/konfigurationsbackup, övervakningsskript, timers och isolerad återställningsövning | Faktisk S3 och tjänstest på målservern, aktiverade timers, extern larmmottagare och full katastrofövning |

## Rapporttäckning

Planen anger 85 identifierade rapportval i 11 kategorier, men innehåller inte den namngivna listan och beräkningsreglerna. De 85 får därför **inte** betecknas som implementerade eller verifierade. Denna leverans har tolv självständiga rapportfamiljer. [Rapportmatrisen](report-coverage.csv) anger vilket underlag som finns och vilka definitioner som ska verifieras.

Nästa täckningsarbete är att föra in varje verkligt rapportnamn med DeDu-kategori, urval, kolumner, formel, måttenhet, representativt testunderlag och motsvarande Förvalta-mall. En rapport räknas som täckt först när både innehåll och beräkning har godkänts. Namn eller platshållare får inte användas som bevis för funktionstäckning.

## Produktionsspärrar

1. Kör hela containerinstallationen i separat EU/EES-testmiljö. Verifiera HTTPS, MFA, SMTP, antivirus, privata S3-behörigheter och källkodspaketet.
2. Verifiera de implementerade säkerhetsflödena på målmiljön. Utse två systemadministratörer och fastställ rutiner för identitetskontroll, kodöverlämning och incidenter.
3. Konfigurera separata backupkonton, installera timers och anslut en larmmottagare. Kör den medföljande PITR-övningen med bilagor på målmiljön och bevisa RPO ≤15 minuter och RTO ≤4 timmar. Det lokala syntetiska PITR-provet är godkänt men bevisar inte produktionsmålen.
4. Gör tillgänglighets- och användartest med verkliga roller. Ingen mätning av 30 procent snabbare flöden har gjorts.
5. Genomför belastningsprov med 100 samtidiga användare, 10 000 objekt och 1 miljon historikposter. Rapportbyggaren materialiserar i dag sitt urval; stora exporter behöver strömning/bakgrundskörning. Vissa objektväljare använder de första 1 000 objekten och behöver sökning på servern före större register.
6. Verifiera funktions-/rapportmatrisen innan tjänsten kallas fullständig ersättare.

Piloten kan granskas lokalt nu. Det är inte ett godkännande att använda verkliga verksamhetsdata i skarp drift.

## Besiktningsleverans 0.6

Se [besiktningsflödet](INSPECTIONS.md). Protokollen och anmärkningarna ingår i fullständig dataexport. Åtkomsten till Coolify, OVH och Strato har verifierats. Ett separat installationsutkast är förberett i Coolify. Ingen extern tjänst är startad; domän, S3, SMTP, backup och återställningsprov återstår. Containerbyggen och produktionsstart med begränsat databaskonto har klarat CI.
