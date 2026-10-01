# Åtkomst och MFA – version 0.2

## Vad som är implementerat

- Tilldelningar kan återkallas och ligger kvar som inaktiva poster med versionsnummer. Administratören måste ha rätt att administrera hela tilldelningens omfattning. Återkallning av en tilldelning avslutar användarens samtliga sessioner; övriga tilldelningar består och kan användas vid ny inloggning.
- Kontostängning och återkallning av en annan användares samtliga sessioner kräver systemadministratör. Eget konto får inte stängas genom administrationsvyn. Det finns även skydd för sista aktiva systemadministratören. Konton och historik raderas inte.
- Säkerhetsåtgärder kräver nuvarande lösenord och en ny TOTP-kod i produktionsläge. Kontrollförsök begränsas även när transaktionen återställs efter ett fel. Kontot/tilldelningen versionskontrolleras innan ändring.
- Varje användare har en sessionsgeneration. Den höjs vid återkallning, kontostängning och MFA-återställning. Skyddade anrop från gamla sessioner nekas och webbklienten återgår till inloggning. Även påbörjad lösenordsinloggning före MFA kan återkallas. Redan mottagen information kan inte tas tillbaka från en klient.
- Skrivningar och återkallning samordnas med användarlås. Två samtidiga användningar av samma återställningskod får bara en vinnare.
- En administratör får inte skapa en tilldelning med större organisations- eller ekonomiomfattning än sin egen, även om administratören har åtkomst till en överordnad enhet.

## Egen återställning

Vid första registrering av autentiseringsapp visas tio slumpade engångskoder. Bara hashvärden sparas. Koderna visas inte igen i API eller historik. Förvara dem utanför autentiseringsappen, exempelvis i organisationens godkända lösenordshanterare.

Användaren loggar först in med sitt lösenord och väljer återställning. En oanvänd kod ger en kortvarig behörighet att registrera en ny autentiseringsapp, inte tillgång till verksamhetsdata. Gamla sessioner avslutas. Vid lyckad registrering ersätts alla tidigare återställningskoder med tio nya.

Om anslutningen bryts efter att en kod förbrukats men innan den nya appen registrerats kan användaren börja om med lösenord och en annan kvarvarande kod. Koderna som återstår spärras inte förrän ny app registrerats. Administrativt godkänd återställning spärrar däremot gamla återställningskoder eftersom de kan vara komprometterade.

I **Min säkerhet** kan användaren ersätta återställningskoder eller avsluta övriga sessioner efter ny verifiering. Den nuvarande sessionen hålls kvar vid eget avslut av övriga sessioner.

## När koderna saknas

1. En systemadministratör kontrollerar identiteten enligt organisationens rutin utanför tjänsten och registrerar en motivering. Begäran gäller i 30 minuter.
2. En annan systemadministratör, som inte heller är målpersonen, gör en oberoende kontroll och godkänner med eget lösenord och TOTP.
3. Befintliga sessioner och gamla återställningskoder spärras. En slumpad tillfällig kod visas bara för godkännaren och gäller i en timme. Den lagras inte i klartext i logg eller sparningskvitto.
4. Godkännaren överlämnar koden via en separat, godkänd säker kanal. Tjänsten skickar den inte med vanlig e-post.
5. Målpersonen använder sitt befintliga lösenord och engångskoden för att registrera ny app.

Förloras svaret med engångskoden behöver en ny begäran godkännas. En förbrukad eller utgången begäran kan inte återanvändas. Kontots säkerhetsversion kontrolleras också, så att en äldre begäran inte kan tillämpas efter en senare säkerhetsändring.

Detta kräver minst två aktiva systemadministratörer med registrerad MFA. Den första systemadministratören och en reserv skapas interaktivt av behörig driftansvarig. Ingen publik endpoint kan göra någon till systemadministratör. Offlineåterställning vid förlust av samtliga administratörer måste följa en dokumenterad och separat behörighetskontrollerad driftprocess; ingen sådan bakdörr är inbyggd.

## Loggning och begränsningar

Åtgärder loggar aktör, tid, mål, orsak och version. Hemliga MFA-nycklar, engångskoder och deras hashvärden tas inte med i ändringsloggen. Känsliga API-svar får `Cache-Control: private, no-store`.

Demokontot har inget lösenord och kan därför inte genomföra de nya säkerhetsåtgärderna. Använd separata testkonton för pilotprov. Det finns ingen återaktiveringsknapp som oavsiktligt kan återställa gamla behörigheter. Återanställning/återaktivering kräver tills vidare en granskad administrativ process.

TOTP, tvåpersonsgodkännande, samtidighet och återkallning är testade lokalt. Organisationsrutiner för identitetskontroll, säker kodöverlämning, reservadministratörer och incidenthantering behöver beslutas före skarp drift.
