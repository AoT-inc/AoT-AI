The dashboard combines visualization and control into a single, customizable interface. 

## Data Visualization Tools

1.  **Live Measurements**: Displays the most recent data from all active controllers.
2.  **Asynchronous Graphs**: Engineered for long-term data analysis, focusing on performance by loading only required data points for each zoom level.
3.  **Dashboard Widgets**: Intersect information with interactivity. Use widgets to:
    -   Monitor sensor trends (Charts, Gauges).
    -   Quickly control hardware (Sliders, Switches).
    -   View environmental data (Weather, GIS Maps).
    -   Receive AI-driven insights (AI Reasoning Widget).

---

## Custom Widget Development

AoT supports custom widget imports. Modules are located in `aot/widgets/`.

Creating a custom widget requires specific placement of Javascript. The following structure illustrates how multiple widgets are combined on the dashboard:

```html
<html>
<head>
  <title>Title</title>
  <script>
    {{ widget_1_head }}
    {{ widget_2_head }}
  </script>
</head>
<body>

<div id="widget_1">
  <div id="widget_1_titlebar">{{ widget_title_bar }}</div>
  {{ widget_1_body }}
</div>

<div id="widget_2">
  <div id="widget_2_titlebar">{{ widget_title_bar }}</div>
  {{ widget_2_body }}
</div>

<script>
  {{ widget_1_js }}
  {{ widget_2_js }}

  $(document).ready(function() {
    {{ widget_1_js_ready }}
    {{ widget_2_js_ready }}
  });
</script>

</body>
</html>
```

---

> [!NOTE]
> For AI agents, structured widget categories and visualization details are available in `ai_docs/data_viewing.json`.
