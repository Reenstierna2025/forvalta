# Inbyggd AI · version 0.3

## Anslut din leverantör

1. Logga in med ett systemadministratörskonto och öppna **Administration → AI-inställningar**. Demokontot visar endast en låst förhandsvisning.
2. Ange HTTPS-basadress, modellnamn och API-nyckel. För OpenAI är basadressen `https://api.openai.com/v1`. Modellnamnet ska vara ett som ditt API-konto har tillgång till; inget modellval är förinställt.
3. Välj varje tillåten organisationsenhet uttryckligen. Underordnade enheter inkluderas inte automatiskt.
4. Ange dagsgräns för antal anrop över hela installationen och välj om prioriteringsförslag ska vara tillåtna.
5. Aktivera och spara med ditt lösenord och, i drift, en ny MFA-kod. Granska leverantörens villkor, lagringsregion och hantering av verksamhetsdata före aktivering.
6. Öppna **AI-assistent**, välj enhet, granska underlaget och skicka en fråga. Detta provar den riktiga anslutningen och kan debiteras av leverantören.

Anslutningen använder Chat Completions med Bearer-autentisering, JSON-svar, `max_completion_tokens: 2000` och `store: false`. Leverantören och modellen måste stödja dessa fält. Alla tjänster som marknadsförs som OpenAI-kompatibla gör inte det. Se [officiell API-referens](https://developers.openai.com/api/reference/resources/chat). Anthropic Messages, Azure-specifik autentisering, verktygsanrop, filer, ljud och strömmande svar ingår inte i denna adapter.

Egen AI kan anslutas genom en kompatibel HTTPS-gateway med betrott certifikat på port 443. Privata adresser kräver att driftansvarig anger exakt ursprung i `AI_PRIVATE_ORIGINS`, exempelvis `https://ai.example.org`, och startar om tjänsten. HTTP och självsignerade certifikat tillåts inte. Publika adresser kontrolleras mot privata/reserverade IP-intervall; anslutningen använder den kontrollerade IP-adressen med ursprungligt TLS-värdnamn. Omdirigeringar följs inte och miljöns HTTP-proxy används inte.

## Vad som fungerar

- Fristående frågor om arbetsorder inom en uttryckligen vald och tillåten enhet.
- Högst 100 oarkiverade arbetsorder per fråga, med nummer, rubrik, status, prioritet, förfallodatum samt tekniska post-ID och versionsnummer.
- Serverberäknade statusantal för hela enhetens oarkiverade arbetsorder. Poster och antal hämtas i samma SQL-fråga så att de använder samma databasögonblick.
- Källförteckning, modell och genereringstid visas med svaret. Modellens hänvisningar och slutsatser kan fortfarande vara fel och måste granskas.
- Högst fem prioriteringsförslag. Bara servervaliderade post-ID och tillåtna prioriteter får bli godkännbara förslag.
- Varje ändring godkänns separat. Förslaget är signerat, bundet till användare, konfigurationsversion och postversion samt giltigt i en timme. Ändringen sparas transaktionellt med behörighetskontroll, idempotens och ändringslogg.

Assistenten kan inte skapa arbetsorder, ändra datum, status eller ansvarig, behandla dokument, analysera budget eller ändra scenarier i denna version. Dessa kräver egna avgränsade verktyg, granskningsvyer och acceptanstester innan de läggs till. Den har ingen fri databasåtkomst och utför inte modellstyrda nätverksanrop eller SQL.

## Data, nycklar och begränsningar

- AI är avstängd i en tom installation. Endast interna roller kan lämna underlag; entreprenörsrollen ger ingen AI-åtkomst.
- Användarens aktuella enhetsbehörighet skärs mot administratörens AI-tillåtelselista både före anrop och före svar. Utgångna sessioner och återkallade behörigheter kontrolleras igen. Information som redan skickats till leverantören kan inte tas tillbaka.
- Beskrivningar, kommentarer, kontaktfält, bilagor och ekonomiska uppgifter skickas inte av underlagsfunktionen. Rubriker, organisationsnamn och frågetext kan ändå innehålla känsliga uppgifter; användaren ser och godkänner underlaget.
- Underlaget behandlas som opålitlig data i instruktionen till modellen. Detta är inte ett bevis mot alla promptinjektioner; det avgörande skyddet är avsaknaden av fria verktyg och serverkontrollerade, mänskligt godkända skrivningar.
- Nyckeln krypteras med installationens `MFA_ENCRYPTION_KEY` och lagras i databasen. Samma förvarings-/återställningsrutiner gäller som för MFA-hemligheter. Nyckeln visas aldrig i lässvar, verksamhetsexport eller ändringslogg. Byte av serveradress kräver en ny nyckel. HTTPS skyddar överföringen från administratörens webbläsare.
- Frågetext sparas inte i en chattlogg. Anropskvittot innehåller användare, tid, hash och status samt krypterat svar inklusive källunderlag. Dessa ligger kvar i databasen; någon automatisk gallringsrutin är ännu inte implementerad. Organisationen behöver besluta om retention före skarp användning.
- Varje nytt anrop reserverar en plats i den gemensamma dagsgränsen innan nätverksanropet. Även misslyckade eller avbrutna anrop räknas eftersom leverantören kan ha debiterat dem. Detta är en anropsgräns, inte en garanterad kostnadsgräns i kronor; sätt även budgettak hos leverantören.
- Samma anropsnyckel skickar aldrig frågan två gånger. Ett sparat svar kan hämtas igen om underlag, konfiguration och behörighet fortfarande gäller. Pågående eller misslyckade anrop återförs inte automatiskt till leverantören. Ändrad fråga eller omläsning skapar en ny nyckel och kan ge ett nytt debiterat anrop.
- JSON-svar renderas som vanlig text, inte HTML. Okända ändringsfält och förslag om poster utanför underlaget blir aldrig verkställbara.

## Verifiering

Den lokala testsviten kontrollerar bland annat organisationsgränser, återkallning under pågående anrop, kryptering och maskering av nycklar, återanvändning av anropsnycklar, samtidiga dagsgränser, manipulerade förslag och konflikter vid sparning. Leverantörstransporten har testats med simulerade svar, inklusive nekade omdirigeringar och maskerade fel.

Ingen verklig API-nyckel har lagts in, inget externt AI-anrop har gjorts och ingen verksamhetsdata har skickats till en AI-leverantör i dessa utvecklingstester. Verklig modellkompatibilitet, leverantörskostnad, svarskvalitet, promptinjektioner och driftmiljön behöver verifieras med godkänt underlag före produktionsbruk.
