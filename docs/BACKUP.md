# Samordnad backup och återställning – version 0.2

Paketet har nu automatisering för krypterade dokument- och konfigurationskopior tillsammans med en namngiven PostgreSQL-återställningspunkt. Kod och lokal PITR-övning är verifierade. Docker/pgBackRest, faktisk S3-leverantör, servervolym och extern larmleverans är ännu inte verifierade i en driftmiljö.

## Hur en komplett kopia skapas

`python3 deploy/recovery.py checkpoint` körs på driftvärden. API- och webbcontainrar får inte backupbehållarens åtkomstuppgifter eller krypteringsnyckel.

1. Kontrollera att pgBackRest har en lyckad databasbackup som är högst 26 timmar gammal.
2. Skapa en unik namngiven återställningspunkt i PostgreSQL och spara dess LSN, WAL-segment, tid och klusteridentitet.
3. Läs dokumentregistret **efter** återställningspunkten. Eftersom dokumentposter och objekt är beständiga kommer alla dokument som hör till punkten med; även senare dokument kan följa med som ofarliga extra objekt.
4. Kontrollera varje originalfils storlek och SHA-256. Kryptera och kopiera dokument och konfiguration till det separata backupkontot. Återläs och verifiera krypterade objekt. Inga befintliga backupobjekt skrivs över.
5. Tvinga WAL-växling, kör pgBackRests arkiveringskontroll och hämta faktiskt tillbaka segmentet som innehåller återställningspunkten.
6. Publicera först därefter det krypterade manifestet som **komplett**. Avbrott eller kontrollfel lämnar högst ett förberett paket; det får inte räknas som en lyckad backup.

Dokument/config använder Fernet (autentiserad kryptering). pgBackRest använder sin separata AES-256-krypterade lagring. Backupobjekt namnges med kontrollsumma eller slumpad identitet. Det finns ingen automatiserad borttagning av dokumentbackuper i version 0.2; utrymme och retention måste förvaltas. Behåll dokument/config minst lika länge som tillhörande basbackuper och WAL-kedjor. Ett gammalt manifest kan inte återställa en databasbackup som gallrats bort av pgBackRest.

Läs [PostgreSQLs beskrivning av namngivna återställningspunkter](https://www.postgresql.org/docs/18/functions-admin.html) och [pgBackRests restore-alternativ](https://pgbackrest.org/command.html#command-restore).

## Konfiguration

Nya fält i `.env.example`: `BACKUP_ENCRYPTION_KEY`, `BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`, `BACKUP_S3_REGION`, `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY`. Ny installation får en slumpad krypteringsnyckel via `deploy/configure.py`. Befintlig `.env` får inte skrivas över; komplettera den kontrollerat med en ny Fernet-nyckel och separata backupuppgifter.

Välj privat, versionsbevarande lagring inom EU/EES i en separat säkerhetsdomän. Behållaren måste stödja HTTPS, villkorad skapning (`If-None-Match: *`) och SSE-S3/AES256. Kontrollera offentliga bucketpolicyer hos leverantören. Backupkontot behöver lista, läsa och skapa objekt; ingen raderingsrätt behövs för det ordinarie jobbet.

Lägg backupens krypteringsnyckel och återställningsåtkomst i separat säker förvaring. Den krypterade konfigurationskopian innehåller serverhemligheter, men kan inte hjälpa om dekrypteringsnyckeln också gått förlorad. Byt inte krypteringsnyckel utan en verifierad nyckelrotations-/återställningsplan.

Operationscontainern `recovery` är separat, har inga publicerade portar och får läsa `.env` för krypterad konfigurationsbackup. Den kör som root för att kunna läsa den 0600-skyddade konfigurationen. Ingen container får Docker-socket; samordnaren kör Docker CLI på driftvärden. Docker/driftåtkomst är en privilegierad administratörsroll.

## Schemaläggning och larm

Efter installation i `/opt/forvalta`, kör som driftansvarig:

```sh
./deploy/install-monitoring.sh
```

Skriptet kräver först en lyckad samordnad backup och en isolerad återställningsövning. Därefter installeras systemd-timers för:

- Samordnad återställningspunkt var femte minut.
- Full databasbackup varje söndag och differentialbackup övriga dagar.
- Hälsokontroll varje minut: komplett återställningspunkt högst 15 minuter gammal, aktuell databasbackup, WAL-fel, ledigt utrymme, arbetarpuls och fel/fördröjning i jobbkö.
- Isolerad återställningsövning varje månad. Fullständig verksamhetsövning med ansvariga ska dessutom genomföras varje kvartal.

Ett misslyckande skrivs som kritiskt fel i systemjournalen. Koppla extern larmmottagare genom root-skyddad `/etc/forvalta-alert.env` (0600) med `FORVALTA_ALERT_WEBHOOK=https://...` och vid behov `FORVALTA_ALERT_TOKEN`. Endast tjänst, allvarlighetsgrad och namnet på den felande systemd-enheten skickas. Ingen larmadress är konfigurerad och inget externt larm har skickats i den lokala leveransen. Prova hela larmkedjan och mottagarens beredskap före skarp drift. Ett fel i larmsändningen måste fångas av värdens övervakning.

## Automatisk återställningsövning

`python3 deploy/restore-drill.py` använder **separat Compose-fil och ett slumpat projektnamn**. Den skapar egna volymer, återställer vald basbackup till manifestets namngivna punkt, väntar på att PostgreSQL nått punkten, återläser och verifierar bilagorna samt kör register-/integritetskontroll. Inga webbportar, mejljobb eller ordinarie applikationsarbetare startas. Produktionsvolymerna monteras inte i övningen.

Resultat och tidsmätning sparas i `backups/drill-*.json`. Projektets övningsvolymer tas bort efter provet. Vid misslyckad städning anges exakt vilket tillfälligt projekt som behöver hanteras. Inget generellt raderingskommando riktas mot produktionsprojektet.

Övningen underkänns om återställningen tar mer än fyra timmar eller om dess senaste kompletta punkt redan var äldre än 15 minuter vid start. Ett grönt prov gäller den testade miljön och volymen; det är ingen permanent garanti. För stora datamängder behöver kapacitet, tidsgränser och dokumentgenomläsning mätas.

## Återställning av dokument vid incident

Använd en separat tom destinationsmapp eller en ny tom privat S3-behållare. `recovery_bundle restore --id <paket-id> --target <tom-mapp>` återläser dokument. `--include-config` återläser även konfiguration med rättighet 0600. Befintliga destinationsfiler skrivs aldrig över. `verify` kontrollerar dokument/config; samordnaren och återställningsövningen kontrollerar databasen.

För S3 finns `recovery_bundle restore-s3 --id <paket-id>` med separata `RESTORE_S3_ENDPOINT`, `RESTORE_S3_BUCKET`, `RESTORE_S3_REGION`, `RESTORE_ACCESS_KEY_ID`, `RESTORE_SECRET_ACCESS_KEY` i operationsprocessens miljö. Kommandot nekar primär- och backupbehållaren som mål, kräver tom behållare och återläser varje uppladdat objekt för hashkontroll. Vid ett fel lämnas destinationen som misslyckad; använd en ny tom destination efter felsökning.

Återställ databasen till exakt manifestets punkt, inte till en senare tid som saknar säkrade bilagor. Kontrollera klusteridentitet, programversion, migrationer och konfiguration innan den återställda miljön blir publik. Aktivera aldrig schemalagda utskick innan återställningen är godkänd.

## Lokal verifiering

[Det lokala PITR-provet](pitr-test.json) använder två separata PostgreSQL 18-kluster, en krypterad grundbackup, krypterade WAL-segment och den riktiga kodens dokumentpaket. Det verifierade att en bilaga skapad efter grundbackupen återfanns och att en registerpost skapad efter återställningspunkten inte återfanns. Detta ersätter inte prov mot driftserverns Docker-, pgBackRest- och S3-konfiguration.

Provet kan upprepas med projektets Python-miljö:

```sh
python deploy/local-pitr-drill.py --pg-bin /sökväg/till/postgresql/bin --work-dir /privat/testkatalog --result /privat/testresultat.json
```

Testklustren stoppas när provet är klart. Katalogerna innehåller enbart syntetiska data men även testhemligheter; de ska förvaras privat och gallras enligt lokal rutin.
