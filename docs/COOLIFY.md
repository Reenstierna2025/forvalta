# Installation via Coolify

Denna profil kompletterar den fristående installationen. Använd `compose.coolify.yaml` med Git-baserad Docker Compose-applikation. Ange en HTTPS-domän enbart för tjänsten `web`, intern port 80. Publicera inga portar för databas, API, scanner, worker eller migrering.

Coolify sköter TLS och vidarebefordrar trafiken till Caddy. Caddy litar på proxyn på det privata containernätet och läser klientkedjan från höger; API ska bara vara nåbart via Caddy. Testa att HTTP omdirigeras, att HTTPS inte får en omdirigeringsloop och att manipulerade klientheaders inte kringgår begränsningar före produktionsstart. [Coolify Compose](https://coolify.io/docs/applications/builds/docker-compose) och [Caddys proxyinställningar](https://caddyserver.com/docs/caddyfile/options).

Alla hemligheter i `.env.example` ska anges som privata driftvariabler i Coolify. Inga verkliga hemligheter eller verksamhetsdata ska läggas i Git. DEMO_MODE och DEBUG är avstängda; MFA är obligatorisk. Separata privata S3-konton behövs för bilagor respektive backup. SMTP behövs för återkoppling och rapportmeddelanden.

Migrering körs som separat engångstjänst före API och worker. De beständiga databas- och signaturvolymerna ska behållas vid uppgraderingar. Namn på projekt och volymer får inte ändras utan flyttplan.

Innan användare släpps in måste pgBackRest-stanza, arkivering och första krypterade backup verifieras enligt BACKUP.md. Återställningsövning ska inkludera bilagor. Monitoring/timers i den fristående guiden använder dess Compose-fil och behöver anpassas till Coolifys arbetskatalog och genererade projektnamn; de är inte automatiskt aktiverade av denna profil. Första administratören skapas först efter lagrings- och backupkontroller.

## Liten testinstallation på befintlig server

Använd i stället `compose.pilot.yaml` för en installation med enbart syntetiska testdata. Planerad adress är `https://forvalta.byreenstierna.se`, tjänst `web`, port 80. Profilen kräver ingen S3-tjänst och startar ingen extern backup eller WAL-arkivering. Register sparas i volymen `database`, bilagor i den privata volymen `documents`. Dessa volymer ska behållas vid uppdateringar. De skyddar mot containerbyten, inte mot förlust av servern.

`PILOT_MODE=1` och `LOCAL_DOCUMENT_STORAGE=1` aktiverar uttryckligen lokal dokumentlagring. DEBUG och demoinloggning förblir avstängda. HTTPS, MFA, kontrollsummor, filkontroll, databastransaktioner och behörigheter gäller även här. Gränssnittet visar en testmarkering. API använder en process för att minska minnesåtgången. ClamAV behöver fortfarande utrymme för signaturdatabasen; kontrollera serverns minne efter start.

Ange fyra privata värden i Coolify före start: `SECRET_KEY` (minst 50 slumpmässiga tecken), `MFA_ENCRYPTION_KEY` (Fernet-nyckel), `DB_ADMIN_PASSWORD` och `POSTGRES_PASSWORD` (olika slumpmässiga lösenord). Domänvärdena har förval för testadressen, men Coolify kan behålla tomma värden från en tidigare Compose-profil. Ange därför uttryckligen `ALLOWED_HOSTS=forvalta.byreenstierna.se`, `CSRF_TRUSTED_ORIGINS=https://forvalta.byreenstierna.se` och `PUBLIC_ORIGIN=https://forvalta.byreenstierna.se`. Säkerställ också att gammal `S3_BUCKET` är tom vid byte från produktionsprofilen. Ingen e-postserver är konfigurerad; e-postjobb får inte betraktas som levererade och kommer att visas som misslyckade efter omförsök. Återkoppling via ärendelänken fungerar separat.

Verifiera filuppladdning och återläsning, behörigheter samt att register och bilagor finns kvar efter omstart. Första administratören skapas med `python manage.py createsuperuser` i API-containern och registrerar därefter MFA vid inloggning. Ladda inte produktionsdata innan separat backup och återställning har verifierats. Produktionsprofilen ovan är fortfarande tillgänglig när piloten ska övergå till skarp drift.
