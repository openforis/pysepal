# Solara + pysepal gotchas

Things the stack does silently: no error, no log, just a blank widget, a frozen
kernel or a wrong colour. Each entry is symptom, cause, fix. Check here before
debugging from scratch.

## 1. The map is a 400 px strip across the top

**Cause:** `MapApp` overlays its drawers on a viewport-sized container but never
sizes the map inside it, so the map keeps ipyleaflet's default height.

**Fix:** build the map with `SepalMap(..., fullscreen=True)`. See
`solara-app-builder.md` §5.

## 2. Toasts never appear, or `use_notifications()` raises

**Cause:** `NotificationProvider` creates the bus during its own render. A
component rendered before it finds no bus: `use_notifications()` raises
`NotificationProviderError`, and with `required=False` it gets a `NoopNotifier`
that drops every toast.

**Fix:** mount the provider first, above everything that notifies.

```python
@solara.component
def Page():
    NotificationProvider()   # first, always
    MapApp.element(...)
```

## 3. `solara.display()` mounts nothing

**Cause:** Solara only captures a `display()` call into the component tree while
a render is in progress. Called from `use_effect` it does nothing.

**Fix:** call it from the render body. Repeated calls across renders are fine;
they reconcile into one output, not a stack of duplicates.

## 4. The kernel freezes on one specific edit

**Cause:** reacton compares old and new props with `==` on every render.
`ee.ComputedObject.__eq__` compares the whole expression graph, and shared
subtrees get re-walked once per path. Two _structurally equal_ `ee` objects can
take many seconds to compare, while different ones short-circuit in
microseconds, which is why only one edit hangs.

**Fix:** never let reacton compare `ee` objects. Disable equality on anything
that holds them, so comparison falls back to identity.

```python
@dataclass(frozen=True, slots=True, eq=False)
class IndicatorMaps:
    soc: ee.Image
```

## 5. An ECharts chart is tiny, or ignores a theme change

**Cause:** `EChartsRawWidget` measures its canvas once, at construction. Built
inside a collapsed panel or an inactive tab, it bakes in the 100×500 fallback
and never recovers. It also reads `option` once, so restyling an existing widget
changes nothing.

**Fix:** memoise construction on the container being open and on the theme, so
the widget is rebuilt rather than updated.

```python
def _build_chart():
    if option.value is None or not is_open:
        return None
    return EChartsRawWidget(option=option.value)

chart = solara.use_memo(_build_chart, [option.value, is_open, dark])
```

## 6. A render test sees "nothing happened"

**Cause:** reacton skips a component's render body when its props compare
equal, and `force_update()` does not always force it either. A test that watches
a side effect of rendering (a patched `display`, a construction counter) sees
nothing and concludes the widget is gone.

**Fix:** change a prop that actually differs, such as an `is_open` toggle, to
make the body run again.

## 7. Preselecting an export source does nothing

**Cause:** `use_export_dialog().open_dialog()` resets the whole form: source,
name, asset id, bands.

**Fix:** open first, then preselect. Both are synchronous, so the order is all
that matters.

```python
controller.open_dialog()
controller.selected_source_id.value = source_id
```

The dialog also mounts a `use_task` at first render, which needs a running event
loop. In a bare `solara.render()` test that raises `RuntimeError: no running event loop`, so stub the dialog host there.

## 8. A classified raster paints the whole globe

**Cause:** Earth Engine clamps everything at or below `min` to the first palette
colour. With a `0` background and a vis window starting at `1`, the background
is painted too. `.clip()` alone leaves in-AOI zeros painted, `.selfMask()` alone
leaves the rest of the world drawn.

**Fix:** both.

```python
image.select(band).clip(region).selfMask()
```

## 9. A colour stays light in dark mode

**Cause:** ipyvuetify ships Vuetify 2 without `customProperties`, so `--v-*`
CSS variables are undefined and `var(--v-divider-base, <fallback>)` always
resolves to the fallback. The element renders, so a browser check passes.

**Fix:** pick the colour in Python from `use_theme_dark()` and pass it in, or
use a Vuetify 2 theme class.

## 10. An icon renders as an empty box

**Cause:** Solara pins the MDI webfont at 4.9.95. Vuetify does not warn on an
unknown icon name; anything added in MDI 5+ renders as nothing.

**Fix:** check names against the font actually installed. Worth a test in any
app with more than a couple of icons.

```python
import re
from pathlib import Path
from jupyter_core.paths import jupyter_path

names = set()
for root in jupyter_path("labextensions"):
    static = Path(root) / "jupyter-vuetify" / "static"
    for bundle in static.glob("*.js") if static.is_dir() else ():
        names |= set(re.findall(r"\.mdi-([a-z0-9-]+)::before", bundle.read_text(errors="ignore")))
assert "export-variant" in names
```

## 11. Dark mode does not follow the app's toggle

**Cause:** `solara.lab.use_dark_effective()` follows Solara's own theme setting,
not pysepal's per-kernel `ThemeState`.

**Fix:** read `pysepal.solara.use_theme_dark()` for anything that must follow
the user's toggle.

## 12. Probe limits

`scripts/browser_probe.mjs` (see `browser-testing.md`):

- Every invocation starts a fresh browser and a fresh kernel. Chain interactions
  inside one invocation with repeated `--click` and `--wait-js`; nothing carries
  over between invocations.
- Vuetify's `v-select` only opens on a trusted click. Use `--click`, not
  `el.click()` from `--eval`.
- The default viewport is 780×493. Always `--resize` to a desktop width, or you
  will debug a layout nobody has.
- To photograph a fully populated app, point the probe at a throwaway page module
  that seeds the app's state before handing back its `Page`.
