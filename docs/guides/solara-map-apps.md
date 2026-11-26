# Best practices for map apps in Solara

These rules are for apps that show a `SepalMap` under Solara (`solara run`, a
SEPAL container) or Voila. Each rule gives its reason, with the Solara doc or
source it rests on. Source paths such as `solara/tasks.py` are in the installed
Solara and reacton packages.

Other guides cover the rest, and this one does not repeat them:

- every `MapApp` argument: [MapApp](./solara-mapapp-component.md);
- the entry point, the sessions and the app's folders:
  [Building Solara apps](./solara-app-builder.md);
- Earth Engine tasks and the async button:
  [Solara GEE patterns](./solara-gee-patterns.md);
- the pysepal 5 map API and what it replaced:
  [Migrating to pysepal 5](./migrating-to-pysepal-5.md);
- serving local raster and vector tiles:
  [Local tile servers](./local-tile-servers.md).

The snippets leave out the entry point (`setup_solara_server()`,
`@with_sepal_sessions`) and use plain strings where an app calls `msg()`.
`tests/test_docs/test_solara_map_apps_snippets.py` renders every snippet marked
`<!-- run -->` in this file.

## The rules in short

1. Build each map with `use_sepal_map` in the component that owns it, one that
   stays mounted, and pass it down.
2. Keep per-user objects per kernel, never at module level.
3. Keep map callbacks short, and register them in an effect.
4. Run slow work in `use_task(prefer_threaded=False)`, with the `*_async`
   methods.
5. Use `MapApp` for an app and `MapView` for an embedded map.
6. Link maps with `link_group`; a group is per kernel.
7. Hold the drawing tools with one `DrawSession`, ended in an effect cleanup.
8. Give a layer its legend; `MapView` shows it.
9. Test with `solara.render` on a live loop, and close the render context.
10. Deploy with `setup_solara_server()` and `--production`.

## 1. Create, hold, share and close a map

- **Build a map with `use_sepal_map(factory, dependencies)`, in the component
  that owns it.** Solara closes only the widgets it built from elements
  (`reacton/core.py`, `_RenderContext.close`), so a map built in
  `solara.use_memo` alone lives until the kernel closes. The hook closes it on
  unmount, on a dependency change and on a hot reload.
- **Never build a map in the render body.** Each render would build a new map,
  with no layers, and none of them would close.
- **Never build a map at module level.** Solara runs the app module once, in a
  kernel it closes before the first user connects (`solara/server/app.py`,
  `AppScript.init`), and every user would share that object.
- **Never hold a map in `use_state`.** A hot reload pickles the page's state to
  restore it, and one value that fails to pickle loses all of it
  (`solara/server/app.py`, `reload`).
- **Pass objects as dependencies, not `id(obj)`.** Reacton compares dependencies
  with `is`, then `==` (`reacton/utils.py`, `equals`), so `id()` adds nothing,
  and it can match a new object that took the address of a collected one.
- **Pass the map down; only its owner closes it.** `MapView`, `LayerPanel`,
  `AoiView` and `MapApp` show the map they are given and never close it. One map
  can show in several views.
- **Build the map in a component that stays mounted.** The owner's unmount
  closes the map, so a map built under a condition, or in a lazy tab
  (`solara.lab.Tabs(lazy=True)`), loses its layers when the user leaves it.
  Build it above them, or hold the `LayerStore` in a longer-lived owner and pass
  it as `layer_store=`.
- **Add the first layers in the factory.** They are added once, with the map.

<!-- run -->

```python
import solara

from pysepal.layers import LayerSpec
from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map
from pysepal.solara.components.layer_panel import LayerPanel
from pysepal.solara.components.map_view import MapView

CITIES = [(-74.07, 4.71), (-75.56, 6.25), (-76.53, 3.45)]  # (lng, lat)


def build_map() -> SepalMap:
    m = SepalMap(gee=False, center=(-75.0, 5.0), zoom=5)
    m.layer_store.add(LayerSpec.from_points(CITIES, name="Cities", id="cities"))
    return m


@solara.component
def Page():
    m = use_sepal_map(build_map, [])  # built once, closed on unmount
    with solara.Columns([3, 1]):
        MapView(m)
        LayerPanel(m.layer_store, map_=m)
```

## 2. Per-user state

- **Keep per-user objects per kernel.** Each browser page gets a virtual kernel,
  with its own thread and asyncio loop
  ([Solara server](https://solara.dev/documentation/advanced/understanding/solara-server));
  under Voila each page is a kernel of its own.
- **A module-level `solara.reactive` holds one value per kernel; any other
  module-level object is shared by every user.** A reactive's default is one
  object for every kernel, so give it an immutable default, never a store or a
  list you change in place
  ([reactive](https://solara.dev/documentation/api/utilities/reactive)).
- **Build a per-page object in the component that uses it**, with
  `use_sepal_map` or `solara.use_memo`, and pass it down. An object for the
  whole kernel goes in `solara.lab.on_kernel_start`: the cleanup it returns runs
  when the kernel closes and on a hot reload (`solara/server/kernel_context.py`,
  `restart`). pysepal's `setup_sessions()` works this way.
- **Leave `loop=` unset.** The map takes the kernel's running loop, and the loop
  of the new connection after a reconnect, which moves the kernel there
  (`solara/server/kernel_context.py`, `initialize_virtual_kernel`).
- **Drive the theme through `ThemeState`.** A map built without `theme_state`
  follows `get_current_theme_state()`, the kernel's own, so one user's toggle
  never recolours another user's map. `ThemeToggle` and
  `get_current_theme_state().set_mode("dark")` change it; `v.theme.dark` does
  not reach the map. `MapApp` binds the map to its `theme_state`.

<!-- fragment -->

```python
# component/model/state.py
import solara

aoi_name = solara.reactive("")  # one value per kernel: per user

store = LayerStore()  # never: one store for every user of the process
m = SepalMap(gee=False)  # never: built in a kernel closed before any user connects
```

<!-- run -->

```python
import solara

from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map
from pysepal.solara.components.map_app import ThemeToggle
from pysepal.solara.components.map_view import MapView


@solara.component
def Page():
    # no theme_state: the map follows the kernel's ThemeState, which the toggle sets
    m = use_sepal_map(lambda: SepalMap(gee=False), [])
    ThemeToggle()
    MapView(m)
```

## 3. React to map events

- **Keep map callbacks short.** `on_click`, `on_view`, `on_status` and a draw
  session's `on_change` run on the kernel's thread, in its message handler,
  under the kernel lock (`solara/server/server.py`, `context.lock`). Until one
  returns, the page handles no other message. Set a reactive, or start a task.
- **Register a callback in an effect, and remove it in the cleanup.** The map
  keeps every function it is given, and the render body makes a new one on each
  render.
- **Do not give slow work to an async callback.** It runs as a bare task on the
  kernel's loop: nothing shows it pending, and its error is only logged
  (`mapframe/_callbacks.py`). Set a reactive, and let a `use_task` run the
  work (section 4).
- **To render again on a widget trait, use
  `solara.use_trait_observe(obj, name)`**, or an effect that observes it and
  returns the unobserve
  ([use_effect](https://solara.dev/documentation/api/hooks/use_effect)).

<!-- run -->

```python
import solara

from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map
from pysepal.solara.components.map_view import MapView


@solara.component
def Page():
    m = use_sepal_map(lambda: SepalMap(gee=False), [])
    clicked = solara.use_reactive(None)

    def listen():
        def on_click(event):
            clicked.set((round(event.lng, 4), round(event.lat, 4)))

        m.on_click(on_click)
        return lambda: m.on_click(on_click, remove=True)

    solara.use_effect(listen, [m])
    text = f"Clicked at {clicked.value}" if clicked.value else "Click the map"
    MapView(m, overlays={"top-right": [solara.Text(text)]})
```

## 4. Run slow work without blocking

- **Run Earth Engine work and the map's `*_async` methods in
  `solara.lab.use_task(..., prefer_threaded=False)`.** The default,
  `prefer_threaded=True`, runs each call on a new thread with a new loop
  (`solara/tasks.py`), and the Earth Engine session works on one loop. See
  [Solara GEE patterns](./solara-gee-patterns.md).
- **Add layers with `add_ee_layer_async` and `add_raster_async` in that task.**
  They render in Earth Engine, or prepare the raster in a worker thread, without
  blocking the loop. They return `None` when a newer action on the same key
  replaced them, or when the map closed meanwhile.
- **Compute in a pool worker, and write after the `await`.** A pool worker
  (`asyncio.to_thread`, an executor) has no kernel context
  (`solara/server/patch.py`, `_is_pool_worker_thread`): a widget built there
  never reaches the browser, and a reactive or `msg()` there has no user. Only
  the layer store hands events from other threads to its loop, so a store write
  there still shows.
- **A new call of a task cancels the running one** (`solara/tasks.py`). For what
  a cancel does to Earth Engine work, see
  [cancel semantics](./solara-gee-patterns.md#cancel-semantics).

<!-- run -->

```python
import ee
import solara

from pysepal.mapping import SepalMap
from pysepal.solara import get_current_gee_interface, use_sepal_map
from pysepal.solara.components.map_view import MapView
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button

TREE_COVER = {"min": 0, "max": 100, "palette": ["#ffffcc", "#006837"]}


@solara.component
def Page():
    gee_interface = get_current_gee_interface()
    m = use_sepal_map(lambda: SepalMap(gee_interface=gee_interface), [gee_interface])

    async def show_tree_cover():
        hansen = ee.Image("UMD/hansen/global_forest_change_2023_v1_11")
        await m.add_ee_layer_async(
            hansen.select("treecover2000"), TREE_COVER, "Tree cover", key="tree_cover"
        )

    task = solara.lab.use_task(
        show_tree_cover, dependencies=None, raise_error=False, prefer_threaded=False
    )
    TaskButtonComponent(label="Show tree cover", **use_task_button(task, on_start=task))
    MapView(m)
```

<!-- run -->

```python
import asyncio
import random

import solara

from pysepal.layers import LayerSpec, VectorStyle
from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map
from pysepal.solara.components.map_view import MapView
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button


def sample_sites(count: int) -> LayerSpec:
    """Slow work for a pool worker: it builds a spec and touches no widget."""
    sites = [(random.uniform(-80, -67), random.uniform(-4, 12)) for _ in range(count)]
    pins = VectorStyle(marker="pin")
    return LayerSpec.from_points(sites, name="Sites", id="sites", style=pins)


@solara.component
def Page():
    m = use_sepal_map(lambda: SepalMap(gee=False), [])

    async def add_sites():
        spec = await asyncio.to_thread(sample_sites, 50)
        m.layer_store.add(spec, replace=True)  # back on the kernel's loop

    task = solara.lab.use_task(add_sites, dependencies=None, raise_error=False, prefer_threaded=False)
    TaskButtonComponent(label="Sample sites", **use_task_button(task, on_start=task))
    MapView(m)
```

## 5. Lay out a map with panels

- **A full app uses `MapApp`.** It holds the drawer, the panel, their insets and
  the theme. Its CSS makes the map fill the window whatever the map's `height`
  (`map_app.css`), so `fullscreen=True` changes nothing there.
- **An embedded map goes in a `MapView`, not on the page bare.** `MapView(m)`
  adds the legend, the loading status, the inspector and the overlays; `m` alone
  shows only the map.
- **Size an embedded map through the map.** The view is as tall as the map's
  `height`, 400px by default. `SepalMap(fullscreen=True)` sets `height="100%"`:
  it fills a parent that has a height of its own, and has no height in a parent
  sized by its content.
- **Put controls over the map in `overlays=`, by corner.** `MapView` stacks them
  inside the insets and past the map's own controls, which the browser measures.
  `MapApp` takes them as `map_overlays=`.
- **Key the siblings that come and go (`.key()`).** Reacton matches children by
  position and type (`reacton/core.py`), so a sibling that appears before the
  view remounts it: the browser builds a new MapLibre map, and the legend
  forgets the user's pick.
- **Give an embedded map's parent `isolation: isolate`.** The map's controls and
  corners use `z-index`, and could cover the page's own header or menus
  ([ipywidget libraries](https://solara.dev/documentation/advanced/howto/ipywidget-libraries)).
  `MapApp` needs none.
- **Inject an app's CSS once, with one `solara.Style` near the root.** Each
  `solara.Style` element adds its CSS and removes it on unmount
  (`solara/components/style.py`).

<!-- run -->

```python
import solara

from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map
from pysepal.solara.components.map_view import MapView


@solara.component
def Page():
    # fullscreen: the map takes the column's 70vh
    m = use_sepal_map(lambda: SepalMap(gee=False, fullscreen=True, coordinates=True), [])

    def show_world():
        m.set_center(0, 0, 2)

    with solara.Column(style="height: 70vh; isolation: isolate"):
        MapView(m, overlays={"top-right": [solara.Button("World", on_click=show_world)]})
```

## 6. Linked maps and compare

- **Link maps with the same `link_group` name.** They keep one camera. The first
  map shown sets it, and a map built later opens where the group is, not at its
  own `center` (`mapframe/widget.py`, "Linked maps").
- **A group is per kernel.** Under Solara it is per browser page, so a user
  never moves another user's maps.
- **Close the maps of a group you rebuild.** A closed map leaves its group. A
  hot reload keeps the kernel (`solara/server/kernel_context.py`, `restart`), so
  a map left open keeps the group's camera, and the new maps open there.
  `use_sepal_map` closes the old maps first.
- **Compare is one map with two halves.** `m.compare = True` splits it, and each
  layer draws on its side: `side=` on the add methods and on
  `layer_store.add`, or `handle.side` later. The switch is the app's; see
  [compare mode](./solara-mapapp-component.md#compare-mode).

<!-- run -->

```python
import solara

from pysepal.layers import LayerSpec
from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map
from pysepal.solara.components.map_view import MapView

OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


def detail_map() -> SepalMap:
    m = SepalMap(gee=False, link_group="overview", height="300px")
    m.layer_store.add(LayerSpec.from_tiles(OSM, name="OpenStreetMap", id="osm"), side="right")
    return m


@solara.component
def Page():
    overview = use_sepal_map(lambda: SepalMap(gee=False, link_group="overview", height="300px"), [])
    detail = use_sepal_map(detail_map, [])
    compare = solara.use_reactive(False)

    def apply_compare():
        detail.compare = compare.value

    solara.use_effect(apply_compare, [detail, compare.value])
    solara.Switch(label="Compare", value=compare)
    with solara.Columns([1, 1]):
        MapView(overview)
        MapView(detail)
```

## 7. Drawing

- **Hold the tools with `session = m.draw.begin(modes, on_change=...)`.** Every
  view of the map then shows the toolbar, and `session.features` holds what the
  user drew, as a GeoJSON FeatureCollection in `lng, lat`.
- **A map has one session at a time.** A new `begin` ends the old session: its
  `active` turns False, and its `set`, `clear`, `start` and `stop` raise
  (`mapframe/_draw.py`).
- **Begin in an effect, and end in its cleanup**, so the tools go away with the
  component.
- **`AoiView` holds its own session while its DRAW method is selected.** Begin
  no other on that map meanwhile: the newest `begin` takes the tools from the
  AOI form.
- **`on_change` is a map callback** (section 3). It runs on each drawing or edit
  a user makes, never for features Python set.

<!-- run -->

```python
import solara

from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map
from pysepal.solara.components.map_view import MapView


@solara.component
def Page():
    m = use_sepal_map(lambda: SepalMap(gee=False), [])
    shapes = solara.use_reactive(0)

    def hold_the_tools():
        session = m.draw.begin(
            ("polygon", "point"), on_change=lambda drawn: shapes.set(len(drawn["features"]))
        )
        return session.end  # the tools go when Page unmounts

    solara.use_effect(hold_the_tools, [m])
    MapView(m, overlays={"top-right": [solara.Text(f"{shapes.value} shapes")]})
```

## 8. Legends

- **Let `MapView` show the legends.** It shows one card per view area (the whole
  map, or each half of a compare), centred at the bottom, with a dropdown of the
  visible layers that have a legend. Do not mount a `LegendComponent` of your
  own over the map: it would overlap that card.
- **A layer's legend is the first of:** the one the app gave it (`legend=` on
  `add_ee_layer`, `add_raster` and their async forms, the `legend` of its
  `LayerSpec`, or `handle.legend = ...` later); the one its Earth Engine asset's
  visualization gives; one derived from its style. A style's `class_colors`
  give items, a `colormap` or a `palette` a gradient, and a vector's colour a
  chip. A local raster's gradient reads the range its tiles stretch across, the
  file's own when `vmin` and `vmax` are unset. A multiband raster has none.
- **An explicit legend is the app's.** `restyle` keeps it, and
  `handle.legend = None` goes back to the derived one.
- **An empty `Legend()` shows none.** The card does not list the layer, and the
  user's pick stays.
- **`MapView(m, legend=False)` shows no card.**

<!-- run -->

```python
import pandas as pd
import solara

from pysepal.layers import LayerSpec, Legend, LegendItem, VectorStyle
from pysepal.mapping import SepalMap
from pysepal.solara import use_sepal_map
from pysepal.solara.components.map_view import MapView

PLOTS = pd.DataFrame(
    {"lng": [-74.1, -73.9, -74.0], "lat": [4.6, 4.7, 4.5], "status": ["open", "closed", "open"]}
)
ROADS = "https://tiles.example.org/roads/{z}/{x}/{y}.png"


def build_map() -> SepalMap:
    m = SepalMap(gee=False, center=(-74.0, 4.6), zoom=9)
    # a style with classes: the derived legend lists them
    style = VectorStyle(color_by="status", class_colors={"open": "#2e7d32", "closed": "#c62828"})
    m.layer_store.add(LayerSpec.from_points(PLOTS, name="Plots", id="plots", style=style))
    # a tile layer has no style to read a legend from: give it one
    m.layer_store.add(LayerSpec.from_tiles(ROADS, name="Roads", id="roads"))
    m.find_layer("roads").legend = Legend(items=[LegendItem(label="Road", color="#f9a825")])
    return m


@solara.component
def Page():
    m = use_sepal_map(build_map, [])
    MapView(m)  # one card, with a dropdown of both layers
```

## 9. Test

- **Test without a browser first.**
  `solara.render(Page(), handle_error=False)` renders the widgets, and
  `rc.find(SepalMap).widget`, `.assert_single()` and `.wait_for()` find them
  ([Testing](https://solara.dev/documentation/advanced/howto/testing)).
- **Render on a live loop** (`asyncio.run`, or
  `unittest.IsolatedAsyncioTestCase`), as under Solara: a `use_task` needs one at
  mount, and the map takes it for its async work.
- **Close the render context.** `rc.close()` runs the effect cleanups, which
  close the maps `use_sepal_map` built: assert `m.comm is None` after it.
- **Stub Earth Engine** by patching `SessionManager.get_gee_interface` and
  `pysepal.scripts.utils.init_ee`, as pysepal's
  `tests/test_demo_apps/test_demo_apps_smoke.py` does.
- **Test per-user state with real kernel contexts.** Without them, two renders
  in one test share one theme, one locale and one link scope. pysepal's
  `tests/_kernel_contexts.py` builds Solara's `VirtualKernelContext` without a
  server.
- **Run with `SOLARA_CHECK_HOOKS=raise`**, so a hook called in a condition or a
  loop fails the test
  ([Rules of hooks](https://solara.dev/documentation/advanced/understanding/rules-of-hooks)).
- **Test in a browser with `pytest-ipywidgets[solara]` and Playwright.** Its
  fixtures (`solara_test`, `page_session`, `ipywidgets_runner`) run a page under
  Solara, Voila or Jupyter (`solara/test/pytest_plugin.py`). See also
  [Browser testing](./browser-testing.md).

<!-- fragment -->

```python
import asyncio

import solara

from pysepal.mapping import SepalMap

from my_app.app import Page


def test_the_page_shows_its_cities():
    async def run():
        root, rc = solara.render(Page(), handle_error=False)
        m = rc.find(SepalMap).widget  # exactly one map
        assert "cities" in m.layer_store
        rc.close()
        assert m.comm is None  # its owner closed it

    asyncio.run(run())
```

## 10. Deploy

- **Call `setup_solara_server()` at module level.** Under a Solara server it
  serves the map's JavaScript, about 2 MB, once per page, and the browser caches
  it; without it every map sends the bundle again. It also sets a 5-minute cull
  timeout and serves pysepal's CSS and JS.
- **Run `solara run app.py --production` outside development.** Development
  mode watches the app's files and hot-reloads them (`solara/__main__.py`).
- **Restart the server after changing pysepal.** A hot reload imports again only
  the modules under the app's root (`solara/server/reload.py`).
- **Expect a dropped page to live until the cull.** A closed tab closes its
  kernel at once. A dropped connection keeps it for `SOLARA_KERNEL_CULL_TIMEOUT`:
  24 h by Solara's default, 5 min with `setup_solara_server()`. A closing kernel
  closes its widgets, maps included
  ([Solara server](https://solara.dev/documentation/advanced/understanding/solara-server)).
- **Run several workers behind sticky sessions.** A kernel lives on the worker
  the page first reached (same page).
- **Under Voila, each page is a kernel, and each map sends its own bundle**:
  `setup_solara_server()` serves files only under a Solara server. On SEPAL,
  Voila loads an app's widget JavaScript from the app's own environment.
- **Give local tiles a route the browser can reach.** SEPAL sets
  `LOCALTILESERVER_CLIENT_PREFIX=/api/sandbox/jupyter/proxy/{port}`; under a
  Solara server with no prefix set, pysepal mounts its own route.
  `LayerSpec.from_vector(url, format="PMTiles", layer=..., style=...)` keeps a
  root-relative PMTiles URL, such as a proxied `vectortileserver` one, as the
  browser's. See [Local tile servers](./local-tile-servers.md).

<!-- fragment -->

```python
# app.py
from pysepal.solara import setup_solara_server

setup_solara_server()  # once, at import: before any page renders
```

```bash
solara run app.py --production
```
