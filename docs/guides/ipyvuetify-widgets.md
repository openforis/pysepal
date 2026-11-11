# Creating ipyvuetify VuetifyTemplate Widgets

> **This guide describes the deprecated `pysepal.sepalwidgets` layer.** It works
> only on ipyvuetify 1 (Vue 2) and is removed in pysepal 5.0
> ([sepalwidgets-deprecation.md](./sepalwidgets-deprecation.md)). Data sync,
> events and the troubleshooting below still apply. A new template must also run
> on ipyvuetify 3 (Vue 3):
>
> - Keep one shared script and one markup file per major: `X.js`, `X.v2.vue`,
>   `X.v3.vue`. In Python, build the template with
>   `compose_vue(vuetify_markup(VUE_DIR / "X"), VUE_DIR / "X.js")` from
>   `pysepal/_vuetify.py`. FileInput
>   (`pysepal/solara/components/inputs/_file_input_widget.py`) and LocaleSelect
>   (`pysepal/solara/components/_locale_widget.py`) are built this way. A small
>   template with no markup difference stays one file.
> - Write `module.exports = {...}`, not `export default`. Do not declare the
>   synced traits as `props`: they arrive as data, and on Vue 3 the template
>   would read the unset props instead.
> - Define `beforeUnmount` next to `beforeDestroy`. Avoid components that Vuetify
>   3 removed, such as `v-list-item-content` below.
> - The `SepalWidget` mixin now lives in `pysepal/_sepal_widget.py`.
>
> The examples below still show the Vue 2 form. The template rules are listed in
> [solara-upstream.md](./solara-upstream.md) (ipyvuetify 3 entry).

Guide for building custom Vue.js widgets with Python backend integration using
ipyvuetify's `VuetifyTemplate` in pysepal.

## When to Use Vue vs Pure Solara

From [Solara's official guidance](https://solara.dev/documentation/api/utilities/component_vue):

> _"Although many components can be made from the Python side, sometimes it
> is easier to write components using Vue directly. It can also be beneficial
> for performance, since instead of creating many widgets from the Python
> side we only send data to the frontend. If event handling is also done on
> the frontend, this reduces latency and makes your app feel much smoother."_

**Use Vue (`VuetifyTemplate` or `component_vue`) when:**

- The UI has complex layout logic (responsive positioning, CSS variables,
  viewport-aware sizing, animations)
- Frontend event handling would reduce latency (drag, resize, hover)
- You need the full Vuetify component API (watchers, computed, lifecycle hooks)
- You're wrapping a JavaScript library that has no ipywidget binding
- Performance matters — fewer Python-to-frontend roundtrips

**Use pure Solara (`@solara.component` with `rv.*`) when:**

- The component is straightforward form inputs, buttons, state display
- All logic is Python-side (no frontend event handling needed)
- Type safety and IDE support are a priority
- The component doesn't need custom CSS or complex layout

**Hybrid approach (recommended for complex widgets):**
Keep the Vue template for rendering and frontend logic. Wrap it in a Solara
component that provides a typed Python API with `value`/`on_value` reactive
parameters. This gives you the best of both: proven Vue rendering + clean
Solara integration.

## Two Approaches

### Approach 1: `solara.component_vue` (recommended for new widgets)

The simplest way to create a Vue-backed Solara component. The decorator
auto-generates traitlets from the function signature:

```python
import solara

@solara.component_vue("MyWidget.vue")
def MyWidget(
    title: str = "Default",
    items: list = [],
    value: dict = {},
    on_value: Callable[[dict], None] = None,
    event_item_click: Callable[[str], None] = None,
):
    pass
```

- `foo` + `on_foo` pairs become reactive props (Solara handles the
  callback wiring)
- `event_foo` arguments become Vue-callable methods (accessible as
  `this.foo()` or `this.event_foo()` in Vue)
- The `.vue` file path is relative to the Python file
- No traitlets, no `__init__`, no widget class — just a function signature

**Vue template** (`MyWidget.vue`):

```vue
<template>
  <v-card>
    <v-card-title>{{ title }}</v-card-title>
    <v-list>
      <v-list-item
        v-for="item in items"
        :key="item"
        @click="event_item_click(item)"
      >
        {{ item }}
      </v-list-item>
    </v-list>
  </v-card>
</template>
```

**Usage in Solara apps:**

```python
@solara.component
def Page():
    value = solara.use_reactive({})
    MyWidget(title="Picker", items=["a", "b"], value=value)
```

### Approach 2: `v.VuetifyTemplate` subclass (existing pysepal pattern)

More control, needed when you want `SepalWidget` helpers, custom
`__init__`, or complex traitlet configuration:

## File Structure

```
pysepal/sepalwidgets/
├── your_widget.py              # Python VuetifyTemplate class
├── vue/
│   └── YourWidget.vue          # Vue component template
```

Existing pysepal VuetifyTemplate widgets follow this layout:

| Widget       | Python file                                         | Vue template                                                           |
| ------------ | --------------------------------------------------- | ---------------------------------------------------------------------- |
| MapApp       | `vue_app.py`                                        | `vue/MapApp.vue`                                                       |
| ThemeToggle  | `vue_app.py`                                        | `vue/Theming.vue`                                                      |
| RightPanel   | `vue_app.py`                                        | `vue/RightPanel.vue`                                                   |
| FileInput    | `../solara/components/inputs/_file_input_widget.py` | `../solara/components/inputs/vue/FileInput.js` + `.v2.vue` / `.v3.vue` |
| TaskButton   | `btn.py`                                            | `vue/TaskButton.vue`                                                   |
| Dialog       | `sepalwidget.py`                                    | `vue/Dialog.vue`                                                       |
| Tabs         | `vue_widgets.py`                                    | `vue/Tabs.vue`                                                         |
| LocaleSelect | `../solara/components/_locale_widget.py`            | `../solara/components/vue/LocaleSelect.js` + `.v2.vue` / `.v3.vue`     |
| DrawerItem   | `app.py`                                            | `vue/DrawerItem.vue`                                                   |

## Python Backend

```python
from pathlib import Path

import ipyvuetify as v
from traitlets import Bool, Dict, List, Unicode, observe

from pysepal.sepalwidgets.widget import SepalWidget


class YourWidget(v.VuetifyTemplate, SepalWidget):
    # Point to Vue template
    template_file = Unicode(
        str(Path(__file__).parent / "vue/YourWidget.vue")
    ).tag(sync=True)

    # Synchronized properties — .tag(sync=True) is required
    title = Unicode("Default Title").tag(sync=True)
    items = List([]).tag(sync=True)
    v_model = Dict({}).tag(sync=True)
    loading = Bool(False).tag(sync=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.items = ["Item 1", "Item 2"]

    @observe("v_model")
    def _on_model_changed(self, change):
        """React to v_model changes from Vue."""
        pass

    # Vue-callable methods — prefix with 'vue_'
    def vue_add_item(self, item_name):
        """Callable from Vue as this.add_item(...)."""
        self.items = list(self.items) + [item_name]  # new list triggers sync
```

Inherit from `SepalWidget` alongside `v.VuetifyTemplate` to get visibility
helpers (`hide()`, `show()`, `toggle_viz()`, `reset()`).

## Vue Frontend

```vue
<template>
  <v-card>
    <v-card-title>{{ title }}</v-card-title>
    <v-card-text>
      <v-list>
        <v-list-item v-for="(item, index) in items" :key="index">
          <v-list-item-content>{{ item }}</v-list-item-content>
        </v-list-item>
      </v-list>
      <v-btn @click="addItem" :loading="loading">Add Item</v-btn>
    </v-card-text>
  </v-card>
</template>

<script>
export default {
  name: "YourWidget",
  props: {
    title: { type: String, default: "Default Title" },
    items: { type: Array, default: () => [] },
    v_model: { type: Object, default: () => ({}) },
    loading: { type: Boolean, default: false },
  },
  methods: {
    addItem() {
      // Call Python method — drop the vue_ prefix
      this.add_item("New Item");
    },
  },
};
</script>
```

## Data Synchronization

- Python properties with `.tag(sync=True)` auto-sync with Vue props.
- **Always create new objects** to trigger sync:
  `self.items = list(self.items) + [new_item]`
- **Never mutate in place**: `self.items.append(...)` will NOT sync.

## Event Handling

### Vue → Python

Python methods prefixed with `vue_` are callable from Vue (without the prefix):

```python
# Python
def vue_handle_click(self, data):
    pass
```

```vue
<!-- Vue -->
<v-btn @click="handle_click('save')">Save</v-btn>
```

### Python → Vue

Use `self.send()` to call Vue methods (which must have a `jupyter_` prefix):

```python
# Python
def notify_vue(self):
    self.send({"method": "highlight", "args": ["success"]})
```

```vue
<!-- Vue -->
<script>
export default {
  methods: {
    jupyter_highlight(type) {
      this.showNotification(type);
    },
  },
};
</script>
```

### Python property observation

Use `@observe` to react to property changes from Vue:

```python
@observe("v_model")
def _on_model_changed(self, change):
    new_value = change["new"]
```

## Component Composition (Embedding Widgets)

VuetifyTemplate supports embedding other widgets via `Instance(DOMWidget)`.
This is how `MapApp` embeds `ThemeToggle`, `RightPanel`, and step content.

### Python side

```python
from ipywidgets import DOMWidget
from ipywidgets.widgets.widget import widget_serialization
from traitlets import Instance, List

class ParentWidget(v.VuetifyTemplate):
    # Single component — must still be a List
    theme_toggle = List(Instance(DOMWidget)).tag(sync=True, **widget_serialization)

    # Multiple components
    panels = List(Instance(DOMWidget)).tag(sync=True, **widget_serialization)

    def __init__(self, theme_toggle=None, **kwargs):
        kwargs["theme_toggle"] = [theme_toggle] if theme_toggle else []
        super().__init__(**kwargs)

        # Parent-child communication: observe Python traits, not Vue events
        if theme_toggle:
            theme_toggle.observe(self._on_theme_change, "dark")
```

### Vue side

```vue
<template>
  <v-app>
    <!-- Always guard with length check -->
    <jupyter-widget
      v-if="theme_toggle && theme_toggle.length > 0"
      :widget="theme_toggle[0]"
    />
  </v-app>
</template>
```

### Rules

1. **Always use Lists** — even single components: `[widget]`
2. **Include `**widget_serialization`** on every `Instance(DOMWidget)` trait
3. **Guard in Vue**: `v-if="prop && prop.length > 0"`
4. **None handling**: `[component] if component else []`
5. **Parent-child communication** uses Python `.observe()`, not Vue `$emit`
   (Vue events do not cross `<jupyter-widget>` boundaries)

## Troubleshooting

### 1. `TypeError: n[o].bind is not a function`

**Cause**: Object-style watchers on Python-synchronized props.

```vue
<!-- WRONG — object watcher causes binding error -->
watch: { is_open: { immediate: true, handler(newValue) { this.internalOpen =
newValue; } } }

<!-- CORRECT — simple function watcher -->
watch: { is_open(newValue) { this.internalOpen = newValue; } }
```

ipyvuetify's binding mechanism conflicts with Vue's object watcher syntax.
**Never use `deep: true` or `immediate: true`** on Python-synced props.
Use `mounted()` instead of `immediate: true` for initialization.

### 2. Vue reactivity with object properties

Vue 2 cannot detect property additions/deletions on objects. Use `$set`
and `$delete`:

```vue
<!-- WRONG — no reactivity -->
this.v_model[nextId] = { name: null };

<!-- CORRECT -->
this.$set(this.v_model, nextId, { name: null }); this.$delete(this.v_model,
oldId);
```

### 3. Props not synchronizing

Check:

- Python property has `.tag(sync=True)`
- Vue prop name matches Python property name exactly
- You are creating new objects, not mutating in place

### 4. Methods not available in Vue

Check:

- Python method is prefixed with `vue_`
- Vue calls it without the prefix: `this.my_method()`
- `on_event` is not available in VuetifyTemplate — use `vue_` methods

### 5. Initial state wrong on mount

**Problem**: Widget starts with wrong state (e.g. panel open when
`is_open=False`).

```vue
<!-- WRONG — timing issue -->
data() { return { internalOpen: this.is_open }; }

<!-- CORRECT — safe default + mounted -->
data() { return { internalOpen: false }; }, watch: { is_open(newValue) {
this.internalOpen = newValue; } }, mounted() { this.internalOpen = this.is_open;
}
```

### 6. `TypeError: this.send is not a function`

`this.send()` is not available in Vue. Call Python methods directly instead:

```vue
<!-- WRONG -->
this.send({ event: "action", data: payload });

<!-- CORRECT — calls vue_handle_action in Python -->
this.handle_action(payload);
```

### 7. Parent-child communication across `<jupyter-widget>`

Vue `$emit` does **not** propagate across `<jupyter-widget>` boundaries.
Use Python `.observe()` on the child's traitlets instead:

```python
# Child
class RightPanel(v.VuetifyTemplate):
    is_open = Bool(False).tag(sync=True)

    def vue_panel_state_changed(self, state):
        self.is_open = state  # triggers parent's observer

# Parent
class MapApp(v.VuetifyTemplate):
    def __init__(self, **kwargs):
        self.right_panel = RightPanel()
        self.right_panel.observe(self._on_panel_change, "is_open")
        super().__init__(**kwargs)

    def _on_panel_change(self, change):
        self.right_panel_open = change["new"]
```
