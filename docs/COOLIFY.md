# Installation via Coolify

Denna profil kompletterar den fristående installationen. Använd `compose.coolify.yaml` med Git-baserad Docker Compose-applikation. Ange en HTTPS-domän enbart för tjänsten `web`, intern port 80. Publicera inga portar för databas, API, scanner, worker eller migrering.

Coolify sköter TLS och vidarebefordrar trafiken till Caddy. Caddy litar på proxyn på det privata containernätet och läser klientkedjan från höger; API ska bara vara nåbart via Caddy. Testa att HTTP omdirigeras, att HTTPS inte får en omdirigeringsloop och att manipulerade klientheaders inte kringgår begränsningar före produktionsstart. [Coolify Compose](https://coolify.io/docs/applications/builds/docker-compose) och [Caddys proxyinställningar](https://caddyserver.com/docs/caddyfile/options).

Alla hemligheter i `.env.example` ska anges som privata driftvariabler i Coolify. Inga verkliga hemligheter eller verksamhetsdata ska läggas i Git. DEMO_MODE och DEBUG är avstängda; MFA är obligatorisk. Separata privata S3-konton behövs för bilagor respektive backup. SMTP behövs för återkoppling och rapportmeddelanden.

Migrering körs som separat engångstjänst före API och worker. De beständiga databas- och signaturvolymerna ska behållas vid uppgraderingar. Namn på projekt och volymer får inte ändras utan flyttplan.

Innan användare släpps in måste pgBackRest-stanza, arkivering och första krypterade backup verifieras enligt BACKUP.md. Återställningsövning ska inkludera bilagor. Monitoring/timers i den fristående guiden använder dess Compose-fil och behöver anpassas till Coolifys arbetskatalog och genererade projektnamn; de är inte automatiskt aktiverade av denna profil. Första administratören skapas först efter lagrings- och backupkontroller.

