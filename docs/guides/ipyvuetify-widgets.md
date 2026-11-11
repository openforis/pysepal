# Writing Vue templates for Vuetify 3

pysepal 5 runs on ipyvuetify 3: Vue 3 and Vuetify 3. This guide shows how to
write a widget backed by a `.vue` file, with `solara.component_vue` or a
`v.VuetifyTemplate` subclass, and the rules a template must follow.

## When to write a template

Write the widget in Python (`@solara.component` with `rv.*` or `solara.*`
elements) when you can. Write a `.vue` template when:

- the browser must do the work: window size, `localStorage`, drag, resize,
  animations, or other events that would be slow through the kernel;
- you wrap a JavaScript library that has no ipywidget binding;
- the layout needs CSS that the Python elements cannot set.

Then wrap the template in a Solara component with a typed `value` / `on_value`
API, so the rest of the app only sees Python.

## `solara.component_vue` (prefer this)

Solara builds the widget from the function signature:

```python
from typing import Callable, Optional

import solara


@solara.component_vue("ItemList.vue")
def ItemList(
    title: str = "Items",
    items: list = [],
    event_item_click: Optional[Callable[[str], None]] = None,
):
    pass
```

- Each argument becomes a synced trait, read in the template by its name.
- An `event_foo` argument becomes a method the template calls as `this.foo(...)`
  (or `foo(...)` in the markup).
- The `.vue` path is relative to the Python file.

pysepal examples: `LegendComponent` (`pysepal/solara/components/legend.py`) and
the `MapApp` bridges (`pysepal/solara/components/map_app/bridges.py`).

## `v.VuetifyTemplate` subclass

Use a class when you need Python-side traits with observers, or a custom
`__init__`:

```python
from pathlib import Path

import ipyvuetify as v
from traitlets import Bool, List, Unicode

VUE_DIR = Path(__file__).parent / "vue"


class ItemListWidget(v.VuetifyTemplate):
    template_file = Unicode(str(VUE_DIR / "ItemList.vue")).tag(sync=True)

    title = Unicode("Items").tag(sync=True)
    items = List([]).tag(sync=True)
    loading = Bool(False).tag(sync=True)

    def vue_add_item(self, name):
        """Called from the template as this.add_item(name)."""
        self.items = [*self.items, name]
```

Wrap it in a Solara component. A trait `foo` gets its `on_foo` callback for
free:

```python
@solara.component
def ItemListComponent(value: list, on_value):
    return ItemListWidget.element(items=value, on_items=on_value)
```

pysepal examples: `LocaleSelectWidget`
(`pysepal/solara/components/_locale_widget.py`, `vue/LocaleSelect.vue`) and
`FileInputWidget` (`pysepal/solara/components/inputs/_file_input_widget.py`,
`vue/FileInput.vue`).

## The template

```vue
<template>
  <v-card>
    <v-card-title>{{ title }}</v-card-title>
    <v-card-text>
      <v-list density="compact">
        <v-list-item
          v-for="(item, index) in items"
          :key="index"
          :title="item"
        />
      </v-list>
      <v-menu v-model="open">
        <template v-slot:activator="{ props }">
          <v-btn v-bind="props" variant="flat" size="small" :loading="loading">
            Add
          </v-btn>
        </template>
        <v-list>
          <v-list-item title="New item" @click="addItem('New item')" />
        </v-list>
      </v-menu>
    </v-card-text>
  </v-card>
</template>

<script>
module.exports = {
  name: "ItemList",
  data() {
    return { open: false };
  },
  mounted() {
    this.onResize = () => (this.open = false);
    window.addEventListener("resize", this.onResize);
  },
  beforeUnmount() {
    window.removeEventListener("resize", this.onResize);
  },
  methods: {
    addItem(name) {
      // calls vue_add_item in Python
      this.add_item(name);
    },
  },
};
</script>
```

## Rules

1. **Write `module.exports = {...}`**, not `export default`.
2. **Keep everything inside the exported object.** ipyvue evaluates only that
   object, so a top-level `const` or function outside it is undefined. Put
   constants in `data()` or in a method.
3. **Do not declare synced traits as `props`.** They arrive as data. With a
   `props` block the template reads the unset props, and ipyvue warns that the
   two clash.
4. **Use `beforeUnmount`** to remove listeners. Vue 3 has no `beforeDestroy`.
5. **Activator slots bind `props`:** `v-slot:activator="{ props }"` and
   `v-bind="props"`. On a Python element:
   `v_slots=[{"name": "activator", "variable": "x", "children": rv.Btn(v_bind="x.props")}]`.
6. **Use Vuetify 3 names:** `density="compact"`, `size="small"`,
   `variant="text"`, `start` on icons, select items with `title`. The full table
   is in [migrating-to-pysepal-5.md](./migrating-to-pysepal-5.md).
7. **A watcher on a synced trait is a plain function**, `foo(value) { ... }`.
   The object form (`{ immediate: true, handler }`) breaks on synced traits; do
   the first run from `mounted()` instead.
   `tests/test_frontend/test_watcher_contract.py` checks pysepal's templates.
8. **`<style scoped>` is global.** ipyvue adds no `data-v-*` attribute, so the
   styles reach the whole page. Use namespaced classes (`sepal-...`) and child
   combinators.
9. **Check it in a browser** with `scripts/browser_probe.mjs --console`
   ([browser-testing.md](./browser-testing.md)). Vue 3 reports an unknown
   component or a template error only in the console.

## Data and events

- **Python → template:** set the trait. Always assign a new object:
  `self.items = [*self.items, x]`. `self.items.append(x)` does not sync.
- **Template → Python:** assign the trait in the template (`this.value = code`),
  or call a `vue_` method without its prefix (`this.add_item(x)`). With
  `component_vue`, call an `event_` method the same way.
- **Python → template call:** `self.send({"method": "highlight", "args": ["ok"]})`
  calls the template method `jupyter_highlight("ok")`.
- **Embedding widgets:** a `List(Instance(DOMWidget)).tag(sync=True, **widget_serialization)`
  trait renders with `<jupyter-widget v-for="(w, i) in children" :key="i" :widget="w" />`.
  Vue `$emit` does not cross a `<jupyter-widget>`: let the parent observe the
  child's traits in Python.

## Troubleshooting

- **Blank widget, `Failed to resolve component` in the console:** a Vuetify 2
  component (`v-list-item-content`, `v-flex`, `v-tabs-items`, ...). See the
  table in [migrating-to-pysepal-5.md](./migrating-to-pysepal-5.md).
- **A method or constant is undefined:** it was defined outside the exported
  object (rule 2).
- **The template shows the default instead of the Python value:** the trait is
  also declared as a prop (rule 3).
- **Wrong state on mount:** do not copy a synced trait in `data()`. Start from a
  safe default and copy it in `mounted()`, then follow it with a watcher.
- **A menu or dialog does not open:** the activator still uses `v-on="on"`
  (rule 5).
