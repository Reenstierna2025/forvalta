# Drift och återställning

## Driftsättning

Använd en dedikerad Linux-server inom EU/EES med Docker Engine och Compose. Domän/DNS, driftansvarig, privata lagringskonton, SMTP och separata backuphemligheter måste fastställas. Den lokala demonstrationen är ingen driftmiljö. Sätt aldrig `DEBUG=1` eller `DEMO_MODE=1` på en publik server.

`deploy/configure.py` skapar `.env` med rättighet 0600 och slumpade hemligheter. Skriptet skriver inte över en befintlig fil. Spara nycklarna i separat säker förvaring. Byte av `SECRET_KEY` bryter befintliga publika länkar; byte av MFA-krypteringsnyckel utan konvertering gör registrerade autentiseringsappar oanvändbara.

Lagringskrav: privat S3-behållare, blockering av offentlig åtkomst, versionering, SSE-S3/AES256 och EU/EES-region. Applikationskontot behöver endast sin dokumentbehållare. Backupkontot ska tillhöra separat säkerhetsdomän och får inte finnas i API- eller webbcontainern. Testmiljön får inte dela behållare med produktion. `compose.yaml` skiljer ut backupvariabler till databastjänsten och exponerar endast proxyportarna 80/443.

Installeraren bygger och startar databasen och antivirus, konfigurerar backupstanza, kör migrationer och Djangos driftskontroll, tar en första databasbackup och startar applikationen. Den avbryter vid fel. Första databasrollen för programmet är inte superuser. Administratörslösenordet för PostgreSQL skiljer sig från programmets lösenord. Ändra båda genom en planerad rutin, inte genom att bara skriva nya värden i `.env` efter initiering.

ClamAV kan behöva tid för första signaturhämtningen. Uppladdningar nekas tills kontrollen fungerar. En ofullständig filuppladdning skapar inte en färdig dokumentpost. Ett avbrutet databasanrop efter objektlagring kan lämna ett oanvänt lagringsobjekt; ta bort sådana först efter jämförelse med register, backup och retention.

Kontrollera att HTTPS-certifikat, källkodslänk, MFA, sessionsutloggning, SMTP och dokumentladdning fungerar. Proxyhuvudet X-Real-IP skrivs över av Caddy; API-porten får inte exponeras direkt. Om en ytterligare proxy läggs till måste IP-kedja och missbruksskydd granskas igen.

## Säkerhetskopiering

pgBackRest konfigureras med separat S3-behållare och AES-256-kryptering. PostgreSQL arkiverar WAL med fem minuters maximal segmentväntan. Detta är en konfiguration, **ingen garanti om fem minuters faktisk replikeringsfördröjning**. Fördröjning och misslyckad arkivering måste larmas.

```sh
./deploy/backup.sh full
./deploy/backup.sh diff
docker compose exec --user postgres db pgbackrest --stanza=forvalta info
```

Schemalägg full backup varje vecka och differentialbackup dagligen på driftservern. Kontrollera returvärde och senaste lyckade backup, inte bara att processen startade. Larma på mer än 26 timmar sedan daglig backup, arkiveringsfel, ofullständiga WAL-kedjor och mindre än 20 procent ledigt diskutrymme. Kontakta driftansvarig via organisationens övervakning.

Dokumentversioner och konfiguration kopieras krypterat till separat backupförvaring och kopplas till en verifierad WAL-återställningspunkt. [Backupmanualen](BACKUP.md) beskriver installation av timers, övervakning och isolerad återställningsövning. Dessa måste konfigureras och verifieras på driftservern. S3-versionering i primärkontot ersätter inte en oberoende backup.

Säkerhetskopiera även krypterad konfiguration, MFA-nyckel, publik länksignering, SMTP-inställningar, migrationsversion och exakt källkods-/containerrevision. Placera dekrypteringsnycklar separat från kopiorna. Använd inte appens full-export som enda backup: exporten utelämnar autentiseringshemligheter och köstatus.

## Återställningsövning

1. Skapa en isolerad testmiljö med avstängd extern e-post, publik trafik och jobbprocess. Använd inga befintliga produktionsvolymer som återställningsmål.
2. Välj och dokumentera UTC-tidpunkt T samt tillgänglig krypterad basbackup/WAL-kedja. Hämta rätt konfiguration och programversion.
3. Återställ pgBackRest till en ny tom PostgreSQL-volym. För tidpunktsåterställning används `--type=time --target='<UTC-tid>'` enligt pgBackRests aktuella dokumentation. Stoppa databasprocessen före filåterställning. Kör aldrig ett generiskt återställningskommando mot en befintlig produktionsvolym.
4. Återställ dokumentbehållarens samtliga objekt som refereras vid T, med originalversioner och sökvägar. Behåll extra objekt tills register och retention kontrollerats.
5. Starta bara databasen och API:t i testmiljön. Kör `python manage.py verify_integrity`. Kommandot läser alla bilagor, jämför SHA-256 och storlek och kontrollerar organisationsrelationer för arbetsorder.
6. Jämför antal/radnycklar, budgetsumma och rapportarkiv mot en i förväg registrerad testjournal. Prova MFA, roller, återkopplingslänk, dokumentnedladdning och en ny versionskontrollerad skrivning.
7. Mät senaste återfunna testhändelse och total tid till godkänd tjänst. RPO ska vara ≤15 minuter och RTO ≤4 timmar, för både register och bilagor. Spara protokoll, fynd och ansvarig.
8. Genomför automatisk isolerad återläsning minst varje månad och full övning varje kvartal. Dessa körningar måste installeras på driftservern; de har inte schemalagts eller utförts mot någon produktionsserver i denna leverans.

Det medföljande lokala provet i `restore-test.json` är en logisk dump/återläsning av syntetiska data och en bilagekopia. Det kompletteras av ett godkänt lokalt PITR-prov med krypterad basbackup/WAL och två bilagor i `pitr-test.json`. Inget av proven bevisar tidsmålen i produktion. PostgreSQL beskriver varför logiska dumpar inte ersätter kontinuerlig WAL-arkivering: https://www.postgresql.org/docs/18/continuous-archiving.html. pgBackRest: https://pgbackrest.org/user-guide.html.

## Jobb, uppgraderingar och incidenter

Jobb lagras i databasen och har pending/running/done/failed, försök och nästa körtid. Arbetaren återtar jobb som fastnat i 15 minuter och försöker högst fem gånger. Larma på `failed` och gamla pending/running. SMTP kan ge dubbla meddelanden om servern tog emot e-post precis före avbrott; verksamhetsändringen ska ändå bara ske en gång. Schemalagda rapporter kontrollerar mottagarens aktuella behörighet och skickar en skyddad länk.

Före uppgradering: ta och kontrollera backup, testa den nya koden och migrationerna i separat miljö, dokumentera versionen och stoppa skrivningar under en migration som kräver det. Att byta tillbaka container återställer inte automatiskt databasschemat. Planera antingen en verifierad bakåtkompatibel migration eller återställning av hela den samordnade kopian.

Ändringslogg, dokumentposter, kostnadsposter, avläsningar, kommentarer och rapportarkiv skyddas mot UPDATE/DELETE av databasregler. Databasadministratören kan ändra reglerna; separat revisionslogg/övervakning krävs om även driftadministratörer ska omfattas av manipulationsskydd. Ordinarie UI/API saknar radering av dessa poster.

Förlorad MFA-enhet hanteras med engångskod efter lösenordsinloggning eller genom tvåpersonsgodkänd administrativ återställning. Återkallning avslutar gamla sessioner. Följ [säkerhetsrutinerna](SECURITY.md) för identitetskontroll och säker kodöverlämning.
