# Besiktningsprotokoll · 0.6

Öppna **Besiktningsprotokoll**. Planera en kontroll mot ett objekt och välj SBA, skyddsrond eller okulär byggnadskontroll. Egna kontrollpunkter kan ersätta grundmallen. Mallarna är arbetsstöd och kräver verksamhetens anpassning.

1. Besvara varje punkt: utan anmärkning, anmärkning eller ej tillämpligt. De två senare kräver kommentar.
2. Lägg vid behov till PDF/PNG/JPEG per punkt. Befintlig privat dokumentlagring, filkontroll och 20 MB-gräns gäller. En uppladdad fil lagras först i dokumentregistret; kopplingen till punkten sparas med kontrollsvaren.
3. Spara svaren. Kvittens visas först när servern bekräftat sparningen. Osparade ändringar varnas vid navigation. Versionskonflikter skriver inte över en annan persons ändring.
4. Chef eller administratör fastställer protokollet. Det låses även mot databasuppdatering/radering. PDF använder fryst objekt-/organisationsnamn, utförare, svar och bilagemetadata. Bilagor hämtas separat; fotografier bäddas inte in i PDF.
5. Anmärkningar skapas en gång per kontrollpunkt och serie. Skapa en arbetsorder med ansvarig, sista datum och prioritet. Upprepade försök skapar inte flera order.
6. Planera ombesiktning med skäl och datum. En senare fastställd ombesiktning ska godkänna punkten, eventuell arbetsorder ska vara kvitterad/verifierad, och en behörig person måste uttryckligen verifiera anmärkningen.
7. Rättelser skapar en ny länkad revision. Originalet ändras aldrig. En ny underkänd kontroll återöppnar tidigare verifierad brist och tillåter en ny åtgärdsorder; den tidigare kopplingen bevaras i ändringsloggen.

Översikten räknar planerade och försenade utkast samt öppna anmärkningar inom användarens organisationsurval. De 20 äldsta öppna anmärkningarna visas direkt. Alla finns kvar i respektive kontrollserie. Rättelser räknas som egna protokollutkast.

Entreprenörer får tillgång till tilldelad arbetsorder enligt befintliga regler, inte till interna protokoll. Intern personal får fylla i kontroller; chef/administratör fastställer och verifierar. API, PDF och fullständig administrativ export följer samma åtkomstmodell som övriga tjänsten.

Återstår: verksamhetsvaliderade kontrollmallar, återkommande generering av denna nya protokolltyp, kalender-/fastighetsvyintegration, fysisk mobil- och kameratestning samt återställningsövning med protokoll och bilagor på målservern. De befintliga återkommande checklistorna fortsätter som ett separat flöde.
