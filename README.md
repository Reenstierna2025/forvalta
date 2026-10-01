# Förvalta

Öppen fastighetsförvaltning för Svenska kyrkans organisationsstruktur. React/TypeScript, Django och PostgreSQL med privata dokument. Licens: **AGPL-3.0-only**.

**Version 0.6.1 – fungerande utvecklingspilot. Inte en färdig DeDu-ersättare eller produktionsgodkänd leverans.** Kärnflöden går att prova med syntetiska data. Den fullständiga fyrastegsplanen är inte färdig; faktisk täckning och kvarvarande arbete finns i [leveransstatus](docs/STATUS.md).

## Prova

I den aktuella arbetsmiljön finns en lokal förhandsvisning på <http://127.0.0.1:5173>. Klicka **Öppna demonstrationen**. Den använder en separat lokal PostgreSQL-databas. Inga uppgifter har migrerats från DeDu.

Prova exempelvis att skapa ett ärende, öppna en arbetsorder, kvittera en checklista, registrera en underhållsåtgärd och jämföra 1-, 5-, 10- och 30-årsbudget. Publik felanmälan ligger på `/#/public`.

Förhandsvisningen behöver de lokala utvecklingsprocesserna för att fungera. Källkodspaketet innehåller inte databasen, lösenord, uppladdningar eller installerade beroenden.

## Ingår

- Organisationshierarki och uttryckliga behörigheter per gren, roll och ekonomiåtkomst.
- Fastighets- och objektregister, arbetsorder, tilldelning, statusövergångar, checklistor, kommentarer och kostnader.
- Publik felanmälan med privat återkopplingslänk och entreprenörsbegränsad läsning.
- Återkommande ronder/besiktningar, kalender, underhållsbudget och fristående fastställbara scenarier.
- Tolv rapportfamiljer, kolumnurval, rapportmallar, arkiv, CSV/Excel/PDF och schemalagda skyddade rapportlänkar.
- Grundregister för vårdplaner, träd, inventarier, SBA, entreprenader och garantier; energiavläsningar/mätarbyten samt nyckelutlåning.
- Transaktioner, versionskonflikter, idempotensnycklar, beständig jobbkö, ändringshistorik och dokumentkontrollsummor.
- TOTP-inloggning, engångskoder för återställning, tvåpersonsgodkänd administrativ MFA-återställning och återkallad åtkomst. Se [säkerhetsrutiner](docs/SECURITY.md).
- Krypterade bilage- och konfigurationskopior kopplade till databasens återställningspunkt, övervakning och isolerad återställningsövning. Se [backupmanual](docs/BACKUP.md).

- Inbyggd AI-assistent med egen API-nyckel, avgränsad arbetsorderanalys och godkända prioriteringsändringar. [Anslutning och begränsningar](docs/AI.md).

- Samlad fastighetsvy med underobjekt, arbetsorder, kontroller, underhåll, kostnader, dokument och historik. [Innehåll och avgränsning](docs/PROPERTY-WORKSPACE.md).

- Rapportgruppering med godkända mått och klickbart underlag, samt kopiering och jämförelse av budgetversioner rad för rad. [Rapportverktyg](docs/REPORT-TOOLS.md).

## Lokal utveckling från tom installation

Python 3.13+, Node 24+ och PostgreSQL 18. SQLite får endast användas för enklare utveckling; tester av samtidiga skrivningar kräver PostgreSQL.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
export DEBUG=1
export MFA_REQUIRED=0
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py createsuperuser
.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

I en andra terminal:

```sh
cd frontend
npm ci
npm run dev
```

PostgreSQL väljs med `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` och `POSTGRES_PASSWORD`. Skapa en separat utvecklingsdatabas. För syntetiska data, sätt `DEBUG=1 DEMO_MODE=1 MFA_REQUIRED=0` och kör `seed_demo` **enbart på en tom demodatabas**. Kommandot avbryter om registerdata redan finns. Produktionsinstallationen börjar alltid tom.

## Egen server och domän

Paketet innehåller Docker Compose, HTTPS-proxy, applikation, jobbprocess, PostgreSQL med pgBackRest samt ClamAV. Dokument och backup använder två separata privata S3-konton inom EU/EES. Registrera ingen verklig verksamhetsdata innan driftkraven i [driftmanualen](docs/DRIFT.md) är godkända.

```sh
python3 deploy/configure.py
# Fyll i .env: domän, privata lagringskonton och e-post.
./deploy/install.sh
# Skapa första administratören interaktivt:
docker compose exec api python manage.py createsuperuser
```

Installera därefter schemalagd backup och övervakning enligt [backupmanualen](docs/BACKUP.md). Installationen kräver en lyckad återställningsövning innan timers aktiveras.

Logga in, registrera autentiseringsappen och skapa organisationsenheterna i Administration. Skapa därefter fastigheter och verksamhetsdata. Domänens DNS måste peka på servern och portar 80/443 vara tillgängliga. Separat testserver ska ha egen databas, egna lagringsbehållare och hemligheter.

**Compose-konfigurationen är validerad, men containerbygge och driftsättning har inte körts här eftersom Docker-motorn inte är igång.** Det finns ingen publicerad tjänst på er domän ännu.

## Tester och API

```sh
DEBUG=1 MFA_REQUIRED=0 .venv/bin/python backend/manage.py test core
cd frontend
npm test
npm run build
```

[Testresultat och begränsningar](docs/TESTER.md). API börjar på `/api/v1/`. [API-avtal](docs/API.md), [OpenAPI](docs/openapi.yaml). Systemadministratören kan hämta verksamhetsdata och bilagor via `/api/v1/full-export/`; denna portabilitetsexport ersätter inte driftbackup och innehåller inte inloggningshemligheter.

## Källkod och licens

Se [LICENSE](LICENSE). Produktionsbygget skapar automatiskt `/source/forvalta-source.tar.gz` av den aktuella källkoden och visar länken i tjänstens sidfot. Installationsanvisningarna ingår. Källkodsarkivet får inte innehålla privata data eller `.env`. Granska tillägg och beroenden innan publicering. AGPL avser programvaran; den öppnar inte verksamhetens data.

Installation med befintlig Coolify-proxy beskrivs i [Coolify-guiden](docs/COOLIFY.md).
