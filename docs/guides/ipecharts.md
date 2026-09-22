# ipecharts - Complete Guide to Creating Interactive Charts

## Table of Contents

1. [Introduction](#introduction)
2. [Why not `solara.FigureEcharts`?](#why-not-solarafigureecharts)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Two Approaches to Creating Charts](#two-approaches-to-creating-charts)
6. [Core Components](#core-components)
7. [Chart Examples](#chart-examples)
8. [Advanced Features](#advanced-features)
9. [Best Practices](#best-practices)

---

## Introduction

`ipecharts` is a Jupyter Widget library that brings interactive charts powered by [Apache ECharts](https://echarts.apache.org/en/index.html) to Jupyter notebooks. It provides two main ways to create charts:

- **`EChartsRawWidget`**: Direct approach using option dictionaries (similar to JavaScript)
- **`EChartsWidget`**: Object-oriented approach with reactive, typed Python classes

### Key Features

- ✅ Full compatibility with Jupyter Widget protocol
- ✅ Reactive updates via traitlets
- ✅ Support for 30+ chart types (2D and 3D)
- ✅ Event handling and chart actions
- ✅ Custom themes and styling
- ✅ JavaScript function support

---

## Why not `solara.FigureEcharts`?

Solara ships its own ECharts component, `solara.FigureEcharts`. pysepal does not
use it, and a new release touching it (1.62 guarded its option watcher, #1201) is
not a reason to revisit that. The comparison, so nobody has to redo it:

|                  | `solara.FigureEcharts`                                                                                              | `ipecharts`                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| Python API       | none — a raw `option` dict; the docstring says "we do not support a Python API to create the figure data"           | typed `Option` / `XAxis` / series classes      |
| ECharts delivery | fetched from a CDN at mount (`solara.settings.assets.cdn`), or served by `solara-assets` when `assets.proxy` is set | bundled with the widget                        |
| Updates          | `setOption(option, true)` — `notMerge`, so every change rebuilds the chart and drops zoom and brush state           | mutate a series, partial update                |
| Theme            | none                                                                                                                | `theme=`, plus the `theme_state` binding below |

The CDN path is the one that would hurt on SEPAL: a chart that fetches its own
JavaScript at render time fails wherever the sandbox network does, and the
offline escape hatch — `solara-assets` — is capped at 1.58.2 on PyPI because the
project hit its storage limit.

The two fixes Solara made upstream have no analogue here. Its 1.62 guard exists
because it imports ECharts asynchronously and the option watcher could fire
first; `ipecharts` imports ECharts statically and initializes on `after-attach`,
and every write already goes through `this._myChart?.setOption(...)`. Its
`on_mouseover_enabled` flag exists because its handlers are always wired;
`ipecharts` registers handlers on demand, so an event with no handler costs no
kernel traffic.

---

## Installation

### Using pip

```bash
pip install ipecharts
```

### Using conda

```bash
conda install -c conda-forge ipecharts
```

---

## Quick Start

### Your First Chart

```python
from ipecharts import EChartsWidget
from ipecharts.option import Option, XAxis, YAxis
from ipecharts.option.series import Line

# Create a simple line chart
line = Line(data=[820, 932, 901, 934, 1290, 1330, 1320], areaStyle={})
option = Option(
    xAxis=XAxis(
        type="category",
        boundaryGap=False,
        data=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    ),
    yAxis=YAxis(type="value"),
    series=[line]
)

# Display the chart
chart = EChartsWidget(option=option)
chart
```

---

## Two Approaches to Creating Charts

### 1. EChartsRawWidget - Dictionary-Based Approach

**Best for:** Quick prototypes, converting JavaScript examples

```python
from ipecharts import EChartsRawWidget

option = {
    'xAxis': {
        'type': 'category',
        'data': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    },
    'yAxis': {
        'type': 'value'
    },
    'series': [{
        'data': [820, 932, 901, 934, 1290, 1330, 1320],
        'type': 'line',
        'areaStyle': {}
    }]
}

EChartsRawWidget(option=option)
```

**Pros:** Simple, direct translation from JavaScript examples  
**Cons:** No reactivity, no type hints

### 2. EChartsWidget - Object-Oriented Approach

**Best for:** Interactive applications, reactive updates, maintainable code

```python
from ipecharts import EChartsWidget
from ipecharts.option import Option, XAxis, YAxis
from ipecharts.option.series import Line

# Create reactive components
line = Line(data=[820, 932, 901, 934, 1290, 1330, 1320], areaStyle={})
option = Option(
    xAxis=XAxis(type="category", data=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
    yAxis=YAxis(type="value"),
    series=[line]
)

chart = EChartsWidget(option=option)

# Update data reactively - chart updates automatically!
line.data = [100, 200, 300, 400, 500, 600, 700]
```

**Pros:** Reactive updates, type hints, IDE autocomplete  
**Cons:** More verbose syntax

---

## Core Components

### The Option Object

The `Option` class is the root configuration object that contains all chart settings:

```python
from ipecharts.option import Option

option = Option(
    # Chart title
    title=Title(text="My Chart", subtext="Subtitle"),

    # Axes
    xAxis=XAxis(type="category", data=categories),
    yAxis=YAxis(type="value"),

    # Series (actual data visualizations)
    series=[line1, bar1, scatter1],

    # Interactive components
    legend=Legend(),
    tooltip=Tooltip(trigger="axis"),
    toolbox=Toolbox(),

    # Styling
    backgroundColor="#1e1e1e",
    color=["#5470c6", "#91cc75", "#fac858"]
)
```

### Common Components

| Component        | Purpose           | Example                                   |
| ---------------- | ----------------- | ----------------------------------------- |
| `XAxis`, `YAxis` | Coordinate axes   | `XAxis(type="category", data=["A", "B"])` |
| `Legend`         | Chart legend      | `Legend(data=["Series1", "Series2"])`     |
| `Tooltip`        | Hover tooltips    | `Tooltip(trigger="axis")`                 |
| `Grid`           | Chart positioning | `Grid(left="10%", right="10%")`           |
| `Toolbox`        | Interactive tools | `Toolbox(show=True)`                      |
| `Dataset`        | Data management   | `Dataset(source=data)`                    |

### Series Types

Available in `ipecharts.option.series`:

**2D Charts:**

- `Line`, `Bar`, `Pie`, `Scatter`, `EffectScatter`
- `Heatmap`, `Boxplot`, `Candlestick`
- `Graph`, `Sankey`, `Funnel`, `Gauge`
- `Tree`, `Treemap`, `Sunburst`
- `Lines`, `Map`, `ThemeRiver`

**3D Charts:**

- `Bar3D`, `Line3D`, `Scatter3D`, `Lines3D`
- `Map3D`, `Surface`, `Polygons3D`

---

## Chart Examples

### Example 1: Interactive Line Chart with Button Control

```python
from ipecharts import EChartsWidget
from ipecharts.option import Option, XAxis, YAxis, Legend, Tooltip
from ipecharts.option.series import Line
from ipywidgets.widgets import Button
import numpy as np

# Create a smooth line chart
line = Line(smooth=True, areaStyle={}, data=np.random.rand(10).tolist())
option = Option(
    xAxis=XAxis(type="category"),
    yAxis=YAxis(type="value"),
    series=[line],
    tooltip=Tooltip(),
    legend=Legend()
)

chart = EChartsWidget(option=option)

# Add interactive button
button = Button(description="Generate Random Data")

def on_button_clicked(b):
    line.data = np.random.rand(10).tolist()

button.on_click(on_button_clicked)

display(button, chart)
```

### Using ipecharts inside Solara

You can mount an ipecharts widget directly inside a Solara component using
the widget factory API. This is useful when building small Solara apps or
examples where you don't want to manage widget references manually.

```python
import solara
from ipecharts import EChartsWidget
from ipecharts.option import Option, XAxis, YAxis
from ipecharts.option.series import Line


@solara.component
def Page():
    line = Line(data=[820, 932, 901, 934, 1290, 1330, 1320], areaStyle={})
    option = Option(
        xAxis=XAxis(
            type="category",
            boundaryGap=False,
            data=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        ),
        yAxis=YAxis(type="value"),
        series=[line],
    )

    # Mount the widget in the Solara component tree
    EChartsWidget.element(option=option)


```

### Example 2: Horizontal Stacked Bar Chart

```python
from ipecharts import EChartsWidget
from ipecharts.option import Option, XAxis, YAxis, Legend, Tooltip
from ipecharts.option.series import Bar

# Create multiple bar series with stacking
bars = []
categories = ["Region A", "Region B", "Region C"]
series_data = {
    "Suitable": [120, 200, 150],
    "Moderately Suitable": [80, 100, 90],
    "Marginally Suitable": [50, 60, 40]
}
colors = ["#2ecc71", "#f39c12", "#e74c3c"]

for i, (name, values) in enumerate(series_data.items()):
    bars.append(Bar(
        name=name,
        data=[round(v, 2) for v in values],
        stack="Total",  # Stack all bars
        itemStyle={"color": colors[i]}
    ))

option = Option(
    backgroundColor="#1e1e1e00",  # Transparent background
    xAxis=XAxis(type="value"),
    yAxis=YAxis(type="category", data=categories),
    series=bars,
    tooltip=Tooltip(trigger="axis", axisPointer={"type": "shadow"}),
    legend=Legend()
)

chart = EChartsWidget(option=option, style={"height": "300px"})
chart
```

### Example 3: Graph/Network Visualization

```python
from ipecharts import EChartsWidget
from ipecharts.option import Option, Title, Legend, Tooltip
from ipecharts.option.series import Graph
import json

# Load graph data (nodes and edges)
with open('les-miserables.json', 'r') as f:
    graph_data = json.load(f)

# Create graph series
g = Graph(
    name="Les Miserables",
    layout="circular",
    circular={"rotateLabel": True},
    roam=True,
    label={"position": "right", "formatter": "{b}"},
    lineStyle={"color": "source", "curveness": 0.3}
)

g.data = graph_data['nodes']
g.links = graph_data['links']
g.categories = graph_data['categories']

option = Option(
    series=[g],
    title=Title(text="Les Miserables", subtext="Circular layout"),
    tooltip=Tooltip(),
    legend=Legend(),
    animationDurationUpdate=1500,
    animationEasingUpdate="quinticInOut"
)

EChartsWidget(option=option)
```

### Example 4: 3D Bar Chart

```python
from ipecharts import EChartsWidget
from ipecharts.option import Option, Grid3D, Tooltip, XAxis3D, YAxis3D, ZAxis3D, Dataset
from ipecharts.option.series import Bar3D

# Prepare dataset
dataset = Dataset(
    dimensions=["Income", "Life Expectancy", "Population", "Country", {"name": "Year", "type": "ordinal"}],
    source=data  # Your data array
)

# Create 3D bar series
bar3D = Bar3D(
    shading="lambert",
    encode={
        "x": "Year",
        "y": "Country",
        "z": "Life Expectancy",
        "tooltip": [0, 1, 2, 3, 4]
    }
)

option = Option(
    grid3D=Grid3D(),
    tooltip=Tooltip(),
    xAxis3D=XAxis3D(type="category"),
    yAxis3D=YAxis3D(type="category"),
    zAxis3D=ZAxis3D(),
    dataset=dataset,
    series=[bar3D]
)

EChartsWidget(option=option)
```

### Example 5: Custom Item Colors (from seplanexample.py)

```python
from ipecharts import EChartsWidget
from ipecharts.option import Option, XAxis, YAxis, Tooltip, Legend
from ipecharts.option.series import Bar

def get_bars_series(values, series_names, series_colors=[], custom_item_color=False, custom_item_colors=None):
    """Create bar series with optional custom colors per item."""

    if not series_colors:
        series_colors = [None] * len(series_names)

    if not custom_item_colors:
        custom_item_colors = [[None] * len(value) for value in values]

    bars = []
    for i, series_name in enumerate(series_names):
        bars.append(Bar(
            data=[
                {
                    "value": round(value, 2),
                    "itemStyle": {"color": color if custom_item_color else None}
                }
                for value, color in zip(values[i], custom_item_colors[i])
            ],
            itemStyle={"color": series_colors[i]},
            name=series_name,
            type="bar"
        ))

    return bars

# Example usage
categories = ["Region A", "Region B", "Region C"]
values = [[120, 200, 150]]
series_names = ["Suitability"]
custom_colors = [["#2ecc71", "#f39c12", "#e74c3c"]]

bars = get_bars_series(
    values,
    series_names=series_names,
    custom_item_color=True,
    custom_item_colors=custom_colors
)

option = Option(
    yAxis=YAxis(type="category", data=categories),
    xAxis=XAxis(type="value"),
    series=bars,
    tooltip=Tooltip(trigger="axis")
)

chart = EChartsWidget(option=option, style={"height": "300px"})
chart
```

---

## Advanced Features

### 1. Widget Initialization Parameters

Customize ECharts initialization (applies to both `EChartsWidget` and `EChartsRawWidget`):

```python
chart = EChartsWidget(
    option=option,

    # Rendering
    renderer="svg",              # 'canvas' or 'svg'
    use_dirty_rect=True,         # Performance optimization

    # Sizing
    width="600px",               # Or "auto"
    height="400px",              # Or "auto"

    # Styling
    style={
        'border': '2px solid #ccc',
        'backgroundColor': '#f0f0f0',
        'borderRadius': '8px'
    },

    # Theme
    theme="dark",                # Or None for default

    # Advanced
    device_pixel_ratio=2.0,
    use_coarse_pointer=False,
    locale="EN"                  # 'EN' or 'ZH'
)
```

### 2. Dynamic Style Updates

```python
# Create chart
chart = EChartsWidget(option=option, style={'height': '300px'})

# Update style later
chart.style = {
    'width': '800px',
    'height': '600px',
    'border': '2px solid #000'
}
```

### 3. Event Handling

Listen to user interactions:

```python
chart = EChartsWidget(option=option)

def on_click(params):
    print(f"Clicked: {params}")

def on_hover(params):
    print(f"Hovering: {params['name']}")

# Register event handlers
chart.on('click', None, on_click)              # All click events
chart.on('click', 'series.line', on_click)     # Only line series
chart.on('mouseover', {'seriesIndex': 1}, on_hover)  # Specific series

# Remove handlers
chart.off('click')              # Remove all click handlers
chart.off('mouseover', on_hover)  # Remove specific handler
```

### 4. Chart Actions

Programmatically trigger chart behaviors:

```python
chart = EChartsWidget(option=option)

# Highlight a data point
chart.dispatchAction({
    'type': 'highlight',
    'seriesIndex': 0,
    'dataIndex': 2
})

# Show tooltip
chart.dispatchAction({
    'type': 'showTip',
    'seriesIndex': 0,
    'dataIndex': 1
})

# Data zoom
chart.dispatchAction({
    'type': 'dataZoom',
    'start': 20,
    'end': 80
})
```

### 5. Using JavaScript Functions

For advanced formatting and callbacks:

```python
from ipecharts.tools import encode_js_fn
from ipecharts.option import Tooltip

# Create a JS function for custom tooltip formatting
formatter = encode_js_fn(
    ['params'],
    "return params.value[3] + ': ' + params.value[0];"
)

tooltip = Tooltip(trigger='item', formatter=formatter)
option = Option(tooltip=tooltip, series=[...])
```

### 6. Custom Theme Integration

```python
from pysepal.solara import get_current_theme_state

class EChartsWidget(EChartsWidget):
    """Extended widget bound to the scope-keyed ThemeState."""

    def __init__(self, theme_state=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.renderer = "svg"
        self.theme_state = theme_state or get_current_theme_state()
        self.theme = "dark" if self.theme_state.dark else "light"
        self.theme_state.observe(self._on_theme_change, "dark")

    def _on_theme_change(self, change):
        self.theme = "dark" if change["new"] else "light"
```

> Observing `theme_state.dark` (the resolved boolean) picks up both explicit
> user toggles and live `prefers-color-scheme` changes in auto mode.

---

## Best Practices

### 1. Choose the Right Approach

- **Use `EChartsRawWidget`** when:

  - Converting JavaScript examples quickly
  - Creating static charts without interactivity
  - Prototyping

- **Use `EChartsWidget`** when:
  - Building interactive dashboards
  - Need reactive data updates
  - Working with other Jupyter widgets
  - Want type hints and IDE support

### 2. Performance Optimization

```python
# For large datasets, use canvas renderer (default)
chart = EChartsWidget(option=option, renderer="canvas", use_dirty_rect=True)

# For better quality/scalability, use SVG
chart = EChartsWidget(option=option, renderer="svg")

# Set explicit dimensions for better performance
chart = EChartsWidget(option=option, width="800px", height="600px")
```

### 3. Data Management

```python
# Good: Use Dataset for complex data
dataset = Dataset(
    dimensions=["Product", "Sales", "Price"],
    source=[
        ["Product A", 43.3, 85.8],
        ["Product B", 83.1, 73.4],
        ["Product C", 86.4, 65.2]
    ]
)

# Reference data in series
bar = Bar(encode={"x": "Product", "y": "Sales"})
option = Option(dataset=dataset, series=[bar])
```

### 4. Styling Consistency

```python
# Define color palette
colors = ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de"]

option = Option(
    color=colors,  # Apply to all series
    backgroundColor="#1e1e1e00",  # Transparent
    # ... rest of config
)
```

### 5. Responsive Charts

```python
# Use relative sizing
chart = EChartsWidget(
    option=option,
    style={
        'width': '100%',   # Responsive width
        'height': '400px'  # Fixed height
    }
)

# Or calculate height dynamically
num_categories = len(categories)
height = max(200, 50 + 75 * num_categories)
chart = EChartsWidget(option=option, height=f"{height}px")
```

`width: 100%` stretches the container, but ECharts lays its canvas out once and
only redraws when something calls `resize()`. `ipecharts` calls it on a window
`resize` (debounced 100ms), on Lumino `resize` messages, on `after-attach`, and
whenever `style` or the CSS classes change — see `baseWidgetView.ts`. It does
**not** watch the container with a `ResizeObserver`.

`demo_apps/solara_chart_app` mounts the same chart in seven places and measures
each one. Two of the seven come out wrong:

| Context                                                     | Result                                          |
| ----------------------------------------------------------- | ----------------------------------------------- |
| A container that changes width, no window resize            | **wrong**: 510px canvas in a 1020px box         |
| A chart built inside a rendered but hidden menu             | **wrong**: 100px canvas in a 128px box          |
| A collapsed expansion panel, an unopened tab, a dialog step | fine: the content mounts when it is shown       |
| MapApp's right panel opening and closing                    | fine: the panel slides, its width never changes |
| A plain page column                                         | fine: a window resize is a path it listens on   |

The same table holds under Voila. Lumino sends its resize messages when its own
layout changes, not when CSS moves something inside a single output, so running
the component from `ui.ipynb` gets both cases wrong in the same way — measured,
not assumed.

So the rule is narrower than "charts break in panels": a chart is wrong when its
box changes without a window resize, or when it is built inside a container that
is in the DOM but not visible. Vuetify's own lazy containers save you from most
of the second case.

**Telling it takes a delay.** The widget has no resize API, and both levers that
reach `resize()` from Python — swapping a CSS class, writing `style` — are
applied the moment the trait lands, which can be before the browser has applied
the layout change that prompted it. Measured: the class arrived on the element
and the canvas still redrew at the old width. Wait for the layout first:

```python
@solara.component
def PanelChart(option, resize_token: int):
    """``resize_token`` is anything that changes when the chart's box changes."""
    chart = EChartsWidget.element(option=option, style={"height": "300px"})
    widget_ref = solara.use_ref(None)

    def capture():
        # get_widget needs a render context, which a task body does not have.
        widget_ref.current = solara.get_widget(chart)

    solara.use_effect(capture, [])

    async def follow():
        if widget_ref.current is None:
            return
        await asyncio.sleep(0.25)
        # Any class change reaches update_classes, which calls chart.resize().
        widget_ref.current.remove_class(f"chart-resize-{(resize_token + 1) % 2}")
        widget_ref.current.add_class(f"chart-resize-{resize_token % 2}")

    solara.lab.use_task(follow, dependencies=[resize_token], prefer_threaded=False)
```

Under `MapApp` the token comes from the shell itself: `right_panel_open`,
`right_panel_width` and `step_open` are synced traits, so `solara.get_widget` on
the `MapApp.element` and an `observe` on those three is all an app needs.

**A window `resize` event fixes every chart on the page at once**, debounced and
acted on by `ipecharts`. `MapApp.vue` already dispatches one inside a
`$nextTick` when the bottom panel toggles, because leaflet has the same blind
spot — that covers MapApp's own layout modes, and there is nothing further to
extend there: `right_panel_width` is a static prop with no drag handle, and
opening or closing the panel slides it without changing its width.

Which leaves the two broken cases to the app, through the deferred nudge above.
What would retire that workaround is a `ResizeObserver` on the chart element in
`ipecharts`' `setupResizeListener`, catching both a container that changes width
and an element that becomes visible. That is upstream work in
[`ipecharts`](https://github.com/trungleduc/ipecharts), deliberately not taken on
here: until it exists, tell the chart yourself and leave it a beat to settle.

### 6. Reusable Components

```python
def create_bar_chart(categories, values, title="", height="300px"):
    """Reusable bar chart factory."""
    bar = Bar(data=values)
    option = Option(
        title=Title(text=title),
        xAxis=XAxis(type="category", data=categories),
        yAxis=YAxis(type="value"),
        series=[bar],
        tooltip=Tooltip(trigger="axis")
    )
    return EChartsWidget(option=option, style={"height": height})

# Usage
chart = create_bar_chart(
    ["A", "B", "C"],
    [120, 200, 150],
    title="Sales by Region"
)
```

### 7. Error Handling

```python
# Always validate data before creating charts
def validate_data(values, series_names, custom_colors=None):
    if len(values) != len(series_names):
        raise ValueError(
            f"Mismatch: {len(values)} value series vs {len(series_names)} names"
        )

    if custom_colors and len(custom_colors) != len(values):
        raise ValueError(
            f"Mismatch: {len(custom_colors)} color series vs {len(values)} value series"
        )

    return True

# Use before creating charts
validate_data(values, series_names, custom_colors)
bars = get_bars_series(values, series_names, custom_item_colors=custom_colors)
```

---

## Summary

`ipecharts` provides a powerful, flexible way to create interactive charts in Jupyter notebooks:

1. **Two approaches**: Dictionary-based (`EChartsRawWidget`) or object-oriented (`EChartsWidget`)
2. **Reactive updates**: Change data properties and charts update automatically
3. **Rich components**: 30+ chart types, axes, legends, tooltips, etc.
4. **Event handling**: Respond to user interactions
5. **Customizable**: Themes, styling, JavaScript functions
6. **Integration**: Works with ipywidgets and other Jupyter tools

For more information:

- 📚 [Documentation](https://ipecharts.readthedocs.io/)
- 🌐 [Try it online](https://trungleduc.github.io/ipecharts/)
- 💻 [GitHub Repository](https://github.com/trungleduc/ipecharts)
- 📊 [ECharts Documentation](https://echarts.apache.org/en/index.html)

---

## Additional Resources

### Converting JavaScript Examples

When you find an ECharts example in JavaScript:

1. Copy the `option` object
2. Convert JavaScript syntax to Python:
   - `camelCase` → `snake_case` for parameters (optional)
   - `true/false` → `True/False`
   - Single quotes → Double quotes (optional)
3. Use `EChartsRawWidget` for quick testing
4. Convert to `EChartsWidget` for production use

### Common Gotchas

1. **Series must be in a list**: `series=[line]` not `series=line`
2. **Data updates**: Use `line.data = new_data` not `line['data'] = new_data`
3. **Height defaults**: Charts default to 500px, set explicitly for control
4. **Theme updates**: Changing theme requires widget recreation or custom handler

### Performance Tips

- Use `renderer="canvas"` for large datasets
- Enable `use_dirty_rect=True` for animations
- Set explicit `width` and `height` when possible
- Debounce rapid data updates in interactive applications
