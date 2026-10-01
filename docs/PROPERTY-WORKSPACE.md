# Samlad fastighetsvy · version 0.4

Öppna **Fastigheter** och välj en fastighet. Vyn gäller det valda objektet och samtliga underobjekt inom samma organisationsenhet. Den är avsedd för interna användare; entreprenörer arbetar vidare med sina tilldelade arbetsorder under Arbete.

## Levererat

- Översikt med öppna/försenade arbeten, arbeten som väntar på verifiering och registrerade återkommande kontroller. Klick på arbetsantalen öppnar motsvarande filtrerade lista.
- Byggnader och objekt hämtas från servern med sökning och sidindelning om 50 poster. Vyn är inte begränsad till uppstartsunderlagets första 1 000 objekt. Navigation till underobjekt och tillbaka via objekthierarkin.
- Arbetsorder på alla underobjekt, med statusfilter och öppning av det befintliga arbetsorderflödet för tilldelning, åtgärd, kommentarer, kostnader, kvittering och verifiering.
- Återkommande kontroller med nästa datum och genvägar till att skapa eller redigera scheman.
- Underhållsåtgärder med belopp för planerat år samt koppling till befintlig eller ny arbetsorder. Dessa är grundåtgärder, inte en komplett flerårsbudget.
- Årets registrerade kostnader, summerade med samma decimalavrundning per rad som kostnadsregistret. Klick till kostnadsrader och arbetsorder. Summan inkluderar även avslutade/arkiverade arbetsorder och är inte fullständig bokföring.
- Dokument på alla underobjekt med bevarade versioner, behörighetskontrollerad hämtning, uppladdning på valt objekt och uppladdning av en ny version på originalets objekt.
- Sidindelad händelsehistorik för objekt, arbeten, kommentarer, kontroller, dokument och relaterade register. Visar vem, vad och när samt registrerad rubrik där sådan finns; historiska före/efter-payloads exponeras inte.

## Dataskydd och beräkningar

Servern kontrollerar objektets organisationsenhet innan trädet läses. Även en felaktig databasrelation till ett objekt i en annan enhet utesluts. Varje relaterad lista filtreras både på enhet och objektträd.

Underhåll, kostnader och deras historikhändelser kräver separat ekonomibehörighet. Historik kräver förvaltar- eller administratörsroll. Uppgifter som användaren saknar behörighet till visas inte som noll; ekonomifälten blir null och ekonomiflikarna döljs.

Översiktens area avser bara det valda objektets registrerade area. Area på fastighet, byggnad och rum summeras inte ihop. Registrerad nollarea skiljs från saknad area. Summering av kostnader sker efter öresavrundning av varje rad; inga JavaScript-beräkningar används för totalsumman.

Varje fristående PostgreSQL-anrop till vyn använder en lästransaktion med ett stabilt databasögonblick. Olika sidvisningar kan visa förändringar som sparats mellan anrop. Vanliga versions- och idempotenskontroller gäller fortsatt vid skrivning genom befintliga API:er.

## Verifiering och återstående arbete

Fem nya tester täcker nästlade objekt, kostnadsavrundning, organisationsgränser, entreprenörsbegränsning, ekonomibehörighet, historik, dokumentversioner, arkiverade arbetsorder och sidindelning. Den fullständiga backendtestsviten omfattar nu 68 tester. Fastighetsöversikt, klick till försenade arbeten och historik har också provats i webbläsaren med syntetiska data.

Detta slutför den första utbyggnaden av den samlade vyn. Personbokning med klockslag, strukturerade kontakter, hyresobjekt, publika fotobilagor, kostnadsrättelser, full historisk jämförelse och en rikare entreprenörsportal återstår. Formulärens generella objektväljare har fortfarande den tidigare begränsningen vid stora register. Rapportbyggare, jämförelse av budgetversioner, fastställda besiktningsprotokoll och utökad AI är nästa separata leveranser. Produktions- och belastningsprov återstår.
