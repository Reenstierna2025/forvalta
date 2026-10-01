# API 1.0

Bas: `/api/v1/`. Inloggade anrop använder sessionscookie. Hämta CSRF-token från `GET auth/` och skicka `X-CSRFToken` vid skrivning. POST till `auth/` med `username` och `password` följs vid behov av `auth/mfa/`. Använd HTTPS i drift.

Alla verksamhetsändringar kräver `Idempotency-Key: <UUID>`. En ändring av befintlig post kräver även `version` i JSON-kroppen. Skrivsvar är normalt `{ "id": "…", "version": 2 }`; hämta posten på nytt efter skrivning. Återanvänd nyckeln och oförändrad kropp vid nätverksomförsök. Nyckeln får inte återanvändas för en annan ändring. `409` betyder versionskonflikt eller krock. `400` betyder valideringsfel. `403` betyder nekad åtkomst. `404` används för poster utanför läsurvalet.

`GET receipts/<uuid>/` kontrollerar serverbekräftelsen för den inloggade användarens begäran. Vid osäkert svar ska klienten kontrollera kvittot innan den skapar en ny begäran. Nuvarande webbklient behåller retry-nycklar medan sidan är öppen; stäng inte ett osparat formulär vid osäker anslutning.

Register: `organizations/`, `assets/`, `work/`, `schedules/`, `maintenance/`, `costs/`, `registry/`, `meters/`, `readings/`, `keys/`, `loans/`, `documents/`, `scenarios/`, `templates/`, `snapshots/`, `subscriptions/`. Listor är sidindelade med 100 poster och returnerar `count`, `next`, `previous`, `results`. Följ `next` för hela urvalet.

Vanliga urval: `org`, `asset`, `q`, `kind`; arbetsorder även `status`. `org` avser den valda grenen, skuren mot användarens faktiska behörigheter. Objekt-ID ger aldrig åtkomst i sig. Relationer valideras på servern.

Arbetsorderstatus ändras endast via `POST work/<id>/transition/` med `version` och `status`. Kommentarer ligger på `work/<id>/comments/`. Checklistesvar ändras genom versionskontrollerad PATCH. Kostnadsposter är beständiga och kan inte ändras genom PATCH.

Dokument laddas upp med multipart till `documents/` med `file`, `asset`, `title` och frivilligt `work`, `revision_of`, `shared_contractor`. Godkända format är PDF, PNG, JPEG, högst 20 MB. I produktion måste antiviruskontrollen lyckas. `documents/<id>/download/` kontrollerar behörighet och SHA-256 innan nedladdning.

`reports/?type=budget&start_year=2026&years=10` ger JSON med rader, urval, definitioner och beräkningsversion. `format_file=csv|xlsx|pdf` ger export. Datum avser förfallodatum för arbetsorder/register/nyckellån och avläsnings-/kostnadsdatum för energi/fakturaunderlag. Budget använder `start_year` och `years`. `columns` är kommaseparerade rubriker. Saknade värden förblir null i JSON.

Publika anrop: `GET public/assets/`, `POST public/issues/` med `asset`, `title`, `description`, frivillig `email` och idempotensnyckel. Svaret innehåller ett ärendenummer och en hemlig token. `POST public/track/` med token returnerar bara det ärendets avsedda återkoppling. Token läggs i webblänken efter `#`, aldrig i serverns URL-fråga.

`full-export/` kräver systemadministratör. ZIP innehåller JSON, bilagor och SHA-256-manifest. Lösenord, MFA-hemligheter, sessioner, publika tokens och jobbkö ingår inte. Exporten är avsedd för portabilitet; använd PostgreSQL-backup för exakt återställning.

OpenAPI-filen beskriver registerfälten. Specialflöden har generiska objekt i schemat och preciseras ovan; använd inte schemat som ett färdigverifierat SDK-kontrakt för alla specialåtgärder.

## Säkerhetsflöden i version 0.2

`POST auth/recover/` kräver påbörjad lösenordsinloggning och `recovery_code`. Följ med `GET/POST auth/mfa/` för ny autentiseringsapp. Nya återställningskoder visas bara vid utfärdandet.

`GET/POST security/` hanterar egen säkerhet, med åtgärderna `revoke_sessions` och `recovery_codes`. `GET access/users/` visar administrerbara konton; `POST access/reduce/` återkallar tilldelning/sessioner eller stänger konto. `GET/POST access/resets/` hanterar återställningsbegäran; `POST access/resets/<uuid>/approve/` kräver en annan systemadministratör. Känsliga ändringar kräver aktuell lösenords-/MFA-verifiering, och versionsstyrda åtgärder kräver rätt `version`. Se [säkerhetsrutiner](SECURITY.md).

Återkallade sessioner ger `401` med `code: session_revoked`. Klienten ska tömma inläst verksamhetsdata och återgå till inloggning. Engångshemligheter lagras inte i ändringslogg eller idempotenskvittot. Om svaret med en administrativ återställningskod går förlorat måste en ny begäran godkännas av två personer.

## AI i version 0.3

- `GET/POST ai/settings/`: systemadministratör, versionskontroll, lösenord och MFA vid skrivning. Nyckel är skrivbar men aldrig läsbar. Skrivningen använder versionskontroll, inte verksamhetskvittot, och returnerar inget hemligt värde. Vid osäkert svar, läs aktuell konfiguration på nytt.
- `GET ai/context/?org=<uuid>`: tillåtna enheter, exakt underlag och dess hash (`digest`).
- `POST ai/chat/`: `question`, `org`, `context_digest`, med `Idempotency-Key`. Eget beständigt AI-kvitto undviker upprepade externa anrop. Gamla kvitton går inte via `receipts/`; anropa samma AI-endpoint med oförändrad begäran och nyckel. `409` kan betyda ändrat underlag eller redan pågående/misslyckat anrop.
- `POST ai/apply/`: serverns signerade `token`, med `Idempotency-Key`. Kräver aktuell skrivbehörighet och oförändrad postversion. Använder ordinarie verksamhetskvitto. Endast ändrad prioritet stöds.

Se [AI-avgränsning och datahantering](AI.md).

## Samlad fastighetsvy i version 0.4

`GET assets/<uuid>/workspace/` ger översikt och behörigheter. `section=objects|work|schedules|maintenance|costs|documents|history` ger sidindelade listor om 50 poster med `count`, `next`, `previous`, `results`. `page` och `q` stöds; historik har inget textsök i denna version. Arbetslistan tar `status=open|overdue|new|planned|in_progress|completed|verified|cancelled`.

Vyn kräver intern läsrätt; ekonomidelarna kräver ekonomibehörighet och historik kräver förvaltar-/administratörsroll. Alla underobjekt avgränsas till rotobjektets enhet. Omfång, beräkningsdefinitioner och begränsningar finns i [fastighetsvyns dokumentation](PROPERTY-WORKSPACE.md).

## Rapportverktyg i version 0.5

`reports/` tar `group_by` och `measure`. Tillåtna kombinationer finns i rapportbyggaren och [rapportdokumentationen](REPORT-TOOLS.md). Grupperat JSON-svar innehåller `rows` (grupper), `analysis` (mått, enhet, medlemsindex) och `detail_rows` (ursprungligt behörighetsfiltrerat underlag). Samma filter fungerar i mallar, arkivering och rapportgenerering. Export använder grupperna.

`POST scenarios/<uuid>/clone/` tar `name`, källans `version` och `Idempotency-Key`. Skapar ett separat utkast, även från en fastställd källa.

`GET scenarios/<uuid>/compare/?other=<uuid>` jämför två åtkomliga budgetversioner med samma period och organisationsomfång. Svaret innehåller jämförelserader, fältförändringar, årsbelopp och versionsmetadata. `format_file=csv|xlsx|pdf` ger export. `before_version` och `after_version` kan låsa exporten till de lästa versionsnumren; avvikelse ger 409. Ingen version ändras av jämförelsen.
