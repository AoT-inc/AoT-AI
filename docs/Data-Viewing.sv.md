## Live mätningar

Page\: `Data -> Live Measurements`

Sidan `Live Measurements` är den första sidan som en användare ser efter att ha loggat in på AoT-AI. Den visar de aktuella mätningar som erhålls från styrenheter för ingång och funktion. Om det inte visas något på sidan `Live` ska du se till att en ingångs- eller funktionsregulator är både korrekt konfigurerad och aktiverad. Data kommer automatiskt att uppdateras på sidan från mätningsdatabasen.

## Asynchronous Graphs

Sidan\: `Data -> Asynchronous Graphs`

En grafisk datavisning som är användbar för att visa datamängder som sträcker sig över relativt långa tidsperioder (veckor/månader/år), vilket kan vara mycket data- och processorkrävande att visa som en synkron graf. Välj en tidsram och data kommer att laddas från den tidsperioden, om den finns. Den första visningen kommer att vara av hela den valda datamängden. För varje vy/zoom kommer 700 datapunkter att laddas. Om det finns fler än 700 datapunkter registrerade för det valda tidsspannet kommer 700 punkter att skapas genom en genomsnittlig beräkning av punkterna i det tidsspannet. På så sätt kan mycket mindre data användas för att navigera i en stor datamängd. Exempelvis kan 4 månaders data vara 10 megabyte om alla data laddas ner. När man tittar på en 4-månadersperiod är det dock inte möjligt att se varje datapunkt i de 10 megabyte, och aggregering av punkter är oundviklig. Med asynkron laddning av data hämtar du bara det du ser. Så i stället för att ladda ner 10 megabyte varje gång grafen laddas, laddas endast ~50 kb ner tills en ny zoomnivå väljs, varvid endast ytterligare ~50 kb laddas ner.

!!! note
    Grafer kräver mätningar, därför måste minst en ingång/utgång/funktion/etc. läggas till och aktiveras för att data ska kunna visas.

## instrumentbräda

Sidan\: `Data -> instrumentbräda`

Instrumentpanelen kan användas både för att visa data och för att manipulera systemet, tack vare de många widgetar som finns tillgängliga. Flera instrumentpaneler kan skapas och låsas för att förhindra att arrangemanget ändras.

## Widgets

Widgets är element på instrumentpanelen som kan användas på olika sätt, t.ex. för att visa data (diagram, indikatorer, mätare osv.) eller för att interagera med systemet (manipulera utgångar, ändra PWM-tjänstgöringscykel, fråga eller ändra en databas osv.). Widgetar kan enkelt omorganiseras och ändras i storlek genom att dra och släppa dem. För en fullständig lista över widgets som stöds, se [Supported Widgets](Supported-Widgets.md).

### Anpassade widgetar

Det finns ett importsystem för anpassade widgetar i AoT-AI som gör det möjligt att använda användarskapade widgetar i AoT-AI-systemet. Anpassade widgetar kan laddas upp på sidan `[Gear Icon] -> Configure -> Custom Widgets`. Efter import kommer de att vara tillgängliga för användning på sidan `Setup -> Widget`.

Om du utvecklar en fungerande modul kan du överväga att [skapa ett nytt GitHub-ärende](https://github.com/kizniche/AoT-AI/issues/new?assignees=&labels=&template=feature-request.md&title=New%20Module) eller en pull request, så att den kan inkluderas i den inbyggda uppsättningen.

Öppna någon av de inbyggda widgetmoduler som finns i katalogen [AoT-AI/aot-ai/widgets](https://github.com/kizniche/AoT-AI/tree/master/aot-ai/widgets/) för att få exempel på korrekt formatering. Det finns också exempel på anpassade widgets i katalogen [AoT-AI/aot-ai/widgets/examples](https://github.com/kizniche/AoT-AI/tree/master/aot-ai/widgets/examples).

För att skapa en anpassad widgetmodul krävs ofta en specifik placering och utförande av Javascript. Flera variabler skapades i varje modul för att lösa detta och följer följande korta struktur för den instrumentbrädsida som skulle genereras när flera widgetar visas.

```angular2html
<html>
<head>
  <title>Title</title>
  <script>
    {{ widget_1_dashboard_head }}
    {{ widget_2_dashboard_head }}
  </script>
</head>
<body>

<div id="widget_1">
  <div id="widget_1_titlebar">{{ widget_dashboard_title_bar }}</div>
  {{ widget_1_dashboard_body }}
  <script>
    $(document).ready(function() {
      {{ widget_1_dashboard_js_ready_end }}
    });
  </script>
</div>

<div id="widget_2">
  <div id="widget_2_titlebar">{{ widget_dashboard_title_bar }}</div>
  {{ widget_2_dashboard_body }}
  <script>
    $(document).ready(function() {
      {{ widget_2_dashboard_js_ready_end }}
    });
  </script>
</div>

<script>
  {{ widget_1_dashboard_js }}
  {{ widget_2_dashboard_js }}

  $(document).ready(function() {
    {{ widget_1_dashboard_js_ready }}
    {{ widget_2_dashboard_js_ready }}
  });
</script>

</body>
</html>
```
