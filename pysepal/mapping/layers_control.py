"""Extend functionalities of the ipyleaflet layer control."""

from types import SimpleNamespace
from typing import Optional, Sequence

import ipyvuetify as v
import traitlets as t
from ipyleaflet import GeoJSON, Layer, Map, TileLayer
from ipywidgets import link

from pysepal._sepal_widget import SepalWidget
from pysepal.mapping._widget_tree import close_tree
from pysepal.mapping.menu_control import MenuControl
from pysepal.message import msg

# an input lets its grid shrink below the control, which then overflows the cell
_FIT_CELL = "min-width: max-content;"


def _checkbox(**kwargs) -> v.VuetifyWidget:
    """Return a checkbox showing neither label nor messages, to fit in a table cell."""
    return v.Checkbox(density="compact", hide_details=True, style_=_FIT_CELL, **kwargs)


def _slider(**kwargs) -> v.Slider:
    """Return a slider showing no messages, so it can be centred in a table cell."""
    kwargs.update(density="compact", hide_details=True, color="primary")
    return v.Slider(class_="v-no-messages", **kwargs)


class _Radio(v.Radio):
    """A radio exposing whether it is the selected one of its group."""

    active: t.Bool = t.Bool(allow_none=True).tag(sync=True)
    "True when the radio is the selected one, False when not"

    def __init__(self, **kwargs) -> None:
        kwargs.update(density="compact", color="primary")
        super().__init__(**kwargs)


class _SoloGroup(v.RadioGroup):
    """A radio group holding one radio, its ``v_model`` mirrors ``active``.

    A Vuetify 3 radio reports a click through its group only (it declares
    ``modelValue``, so Vue drops the ``update:modelValue`` listener on its way to
    the selection control), and a group around the whole table would also drive
    the checkboxes of the other rows: a selection control reads the nearest group.
    """

    def __init__(self, radio: _Radio) -> None:
        self._radio = radio
        super().__init__(children=[radio], density="compact", hide_details=True, style_=_FIT_CELL)
        self._from_radio()
        radio.observe(self._from_radio, "active")
        self.observe(self._from_group, "v_model")

    def _from_radio(self, *args) -> None:
        self.v_model = self._radio.value if self._radio.active else None

    def _from_group(self, change: dict) -> None:
        if change["new"] == self._radio.value:
            self._radio.active = True


class _Selection(t.HasTraits):
    """The selected basemap, kept in sync with the ``active`` trait of the radios.

    Each radio sits in its own ``_SoloGroup``, so the selection is held in python.
    """

    v_model: t.Any = t.Any(None)
    "the value of the selected radio"

    def __init__(self, radios: Sequence[_Radio], **kwargs) -> None:
        self._radios = list(radios)
        super().__init__(**kwargs)
        self._update_radios()
        self.observe(self._update_radios, "v_model")
        for radio in self._radios:
            radio.observe(self._update_v_model, "active")

    def _update_v_model(self, change: dict) -> None:
        """Select the radio that became active."""
        if change["new"] is True:
            self.v_model = change["owner"].value

    def _update_radios(self, *args) -> None:
        """Activate the radio matching the ``v_model`` and deactivate the others."""
        for radio in self._radios:
            radio.active = radio.value == self.v_model


class _Card(v.Card, SepalWidget):
    """The card holding the table, ``get_children`` reaches the rows."""


class HeaderRow(v.Html, SepalWidget):
    def __init__(self, title: str) -> None:
        """Html Row element including a single title of 3 colspan.

        Specifically designed to work in the layer_control table

        Args:
            title: the line value
        """
        attr = {"colspan": 3}
        head = v.Html(tag="th", attributes=attr, children=title)
        super().__init__(tag="tr", class_="v-no-hover", children=[head])


class _LinkedRow(v.Html, SepalWidget):
    """A row whose widgets are linked to the traits of a layer."""

    _links: tuple = ()

    def close(self) -> None:
        """Unlink the layer before closing the row.

        A link observes both ends, so the layer would keep the row alive.
        """
        links, self._links = self._links, ()
        for item in links:
            item.unlink()
        super().close()


class BaseRow(_LinkedRow):

    w_radio: Optional[_Radio] = None
    "the radio to hide/show the layer"

    def __init__(self, layer: TileLayer) -> None:
        """Html row element to describe a base layer.

        This Html element include all the controls to manipulate the basemap displayed in the map
        - a checkbox to show/hide (it will behave like a radio)

        Args:
            layer: the layer associated to the row
        """
        # create the checkbox, by default layer are visible
        self.w_radio = _Radio(value=layer.name)
        kwargs = {"style_": "width: 10%;", "tag": "td"}
        radio_cell = v.Html(children=[_SoloGroup(self.w_radio)], **kwargs)

        # create the label
        kwargs = {"style_": "width: 40%;", "tag": "td"}
        label_cell = v.Html(children=[layer.name], **kwargs)

        # create an empty row to align on
        kwargs = {"style_": "width: 50%;", "tag": "td"}
        empty_cell = v.Html(children=[""], **kwargs)

        # build a html tr from it
        super().__init__(tag="tr", children=[label_cell, empty_cell, radio_cell])

        # add js behavior
        self._links = (link((layer, "visible"), (self.w_radio, "active")),)


class LayerRow(_LinkedRow):

    w_checkbox: Optional[v.VuetifyWidget] = None
    "the ckeckbox to hide/show the layer"

    w_slider: Optional[v.Slider] = None
    "the slider linked to the opacity of the layer"

    def __init__(self, layer: TileLayer) -> None:
        """Html row element to describe a normal layer.

        This Html element include all the controls to manipulate the layer displayed in the map
        - a checkbox to show/hide
        - a slider to change alpha channel

        Args:
            layer: the layer associated to the row
        """
        # create the checkbox, by default layer are visible
        self.w_checkbox = _checkbox(v_model=True, color="primary")
        kwargs = {"style_": "width: 10%;", "tag": "td"}
        checkbox_cell = v.Html(children=[self.w_checkbox], **kwargs)

        # create the label
        kwargs = {"style_": "width: 40%;", "tag": "td"}
        label_cell = v.Html(children=[layer.name], **kwargs)

        # create the slider
        self.w_slider = _slider(v_model=1, max=1, step=0.01)
        kwargs = {"style_": "width: 50%;", "tag": "td"}
        slider_cell = v.Html(children=[self.w_slider], **kwargs)

        # build a html tr from it
        super().__init__(tag="tr", children=[label_cell, slider_cell, checkbox_cell])

        # add js behavior
        self.w_checkbox.observe(self._toggle_slider, "v_model")
        self._links = (
            link((layer, "opacity"), (self.w_slider, "v_model")),
            link((layer, "visible"), (self.w_checkbox, "v_model")),
        )

    def _toggle_slider(self, *args) -> None:
        """Toggle the modification of the slider."""
        self.w_slider.disabled = not self.w_checkbox.v_model

        return


class VectorRow(_LinkedRow):

    w_checkbox: Optional[v.VuetifyWidget] = None
    "the ckeckbox to hide/show the layer"

    def __init__(self, layer: TileLayer) -> None:
        """Html row element to describe a vector layer.

        This Html element include all the controls to manipulate the layer displayed in the map
        - a checkbox to show/hide
        Vector are always placed on top of the map

        Args:
            layer: the vector layer associated to the row
        """
        # create the checkbox, by default layer are visible
        self.w_checkbox = _checkbox(v_model=True, color="primary")
        kwargs = {"style_": "width: 10%;", "tag": "td"}
        checkbox_cell = v.Html(children=[self.w_checkbox], **kwargs)

        # create the label
        kwargs = {"style_": "width: 40%;", "tag": "td"}
        label_cell = v.Html(children=[layer.name], **kwargs)

        # create the slider
        kwargs = {"style_": "width: 50%;", "tag": "td"}
        empty_cell = v.Html(children=[""], **kwargs)

        # build a html tr from it
        super().__init__(tag="tr", children=[label_cell, empty_cell, checkbox_cell])

        # add js behavior
        self._links = (link((layer, "visible"), (self.w_checkbox, "v_model")),)


class ToggleRow(v.Html, SepalWidget):

    w_checkbox: Optional[v.VuetifyWidget] = None
    "the checkbox to hide/show the layer"

    def __init__(self, layer: Layer, control: "LayersControl", index: int) -> None:
        """Html row element to describe a layer exposing no visibility trait.

        Layers such as the ipyleaflet ``PMTilesLayer`` inherit from ``Layer`` rather
        than ``RasterLayer``, so they have neither ``visible`` nor ``opacity`` to link
        a widget to. They are hidden by removing them from the map instead, which means
        the control has to remember them, and where they sat, to keep the row in place.

        Showing a layer again appends it to the map, so it lands on top of anything
        added while it was hidden. That cannot be undone from python: ipywidgets reuses
        the views of the models already present, so reordering ``m.layers`` never
        replays leaflet's ``addLayer`` and the stack stays as it is.

        Args:
            layer: the layer associated to the row
            control: the layer control owning the registry of hidden layers
            index: the position of the row, restored as is when the layer is hidden
        """
        self.layer = layer
        self.control = control
        self.index = index

        # create the checkbox, by default layer are visible
        self.w_checkbox = _checkbox(v_model=layer not in control.hidden, color="primary")
        kwargs = {"style_": "width: 10%;", "tag": "td"}
        checkbox_cell = v.Html(children=[self.w_checkbox], **kwargs)

        # create the label
        kwargs = {"style_": "width: 40%;", "tag": "td"}
        label_cell = v.Html(children=[layer.name], **kwargs)

        # create an empty row to align on
        kwargs = {"style_": "width: 50%;", "tag": "td"}
        empty_cell = v.Html(children=[""], **kwargs)

        # build a html tr from it
        super().__init__(tag="tr", children=[label_cell, empty_cell, checkbox_cell])

        # add js behavior
        self.w_checkbox.observe(self._toggle_layer, "v_model")

    def _toggle_layer(self, *args) -> None:
        """Add or remove the layer from the map."""
        if self.control.m is None:
            return
        # the registry drives the rebuild triggered by the map, so update it first
        if self.w_checkbox.v_model:
            self.control.hidden.pop(self.layer, None)
            self.control.m.add(self.layer)
        else:
            self.control.hidden[self.layer] = self.index
            self.control.m.remove(self.layer)

        return


class LayersControl(MenuControl):

    m: Optional[Map] = None
    "the map controlled by the layercontrol"

    hidden: Optional[dict] = None
    "the layers this control removed from the map to hide them, and their row position"

    group: Optional[_Selection] = None
    "the selected basemap, shared by the radios of the table"

    tile: Optional[v.Card] = None
    "the card holding the table"

    w_loading: Optional[v.ProgressLinear] = None
    "a progress bar, not displayed"

    def __init__(self, m: Map, **kwargs) -> None:
        """Richer layerControl to add some controls over the lyers displayed on the map.

        Each layer is associated to a line where the user can adapt the alpha channel or even hide it completely

        Args:
            m: the map to display the layers
            kwargs: optional extra parameters for the ipyleaflet.WidgetControl
        """
        # save the map
        self.m = m
        self.hidden = {}

        # create a loading to place it on top of the card. It will always be visible
        # even when the card is scrolled
        self.w_loading = v.ProgressLinear(indeterminate=False, bg_color="menu")
        self.tile = _Card(elevation=0)

        # set the kwargs parameters
        kwargs.setdefault("position", "topright")
        super().__init__(
            icon_content="fa-solid fa-layer-group", card_content=self.tile, m=m, **kwargs
        )

        # customize the menu to make it look more like a layercontrol
        self.menu.open_on_hover = True
        self.menu.close_delay = 200

        # set the height according to the content
        self.set_size(min_height=None, max_height=None)

        # update the table at instance creation
        self.update_table({})

        # add js behavior
        self.m.observe(self.update_table, "layers")

    def close(self) -> None:
        """Stop following the map and close the table."""
        if self.m is not None:
            self.m.unobserve(self.update_table, "layers")
        close_tree(self.tile, self.w_loading)
        self.hidden = {}
        super().close()

    def update_table(self, change: dict) -> None:
        """Update the table content."""
        if self.m is None:
            return
        # create the vector line
        vectors = [lyr for lyr in reversed(self.m.layers) if isinstance(lyr, GeoJSON)]

        # overlays owning no visible trait (PMTiles, ...) cannot be linked to a
        # checkbox, they are displayed alongside the vectors and toggled by hand
        others = [
            lyr
            for lyr in reversed(self.m.layers)
            if lyr.base is False and not lyr.has_trait("visible")
        ]

        # splice the hidden ones back where they sat, else a row would jump away
        # from the cursor that just unchecked it
        for layer, index in sorted(self.hidden.items(), key=lambda item: item[1]):
            others.insert(min(index, len(others)), layer)

        vector_rows = []
        if len(vectors) > 0 or len(others) > 0:
            head = [HeaderRow(msg("layer_control.vector.header"))]
            rows = [VectorRow(lyr) for lyr in vectors]
            rows += [ToggleRow(lyr, self, i) for i, lyr in enumerate(others)]
            vector_rows = head + rows

        # create a table of layerLine
        layers = [
            lyr
            for lyr in reversed(self.m.layers)
            if lyr.base is False and isinstance(lyr, TileLayer)
        ]
        layer_rows = []
        if len(layers) > 0:
            head = [HeaderRow(msg("layer_control.layer.header"))]
            rows = [LayerRow(lyr) for lyr in layers]
            layer_rows = head + rows

        # create another table of basemapLine it should always be a basemap
        # the error raised if you delete the last one is a feature
        bases = [lyr for lyr in self.m.layers if lyr.base is True]
        base_rows, radios = [], []
        current = next((lyr for lyr in bases if lyr.visible is True), SimpleNamespace(name=None))
        if len(bases) > 0:
            head = [HeaderRow(msg("layer_control.basemap.header"))]
            empy_cell = v.Html(tag="td", children=[" "], attributes={"colspan": 3})
            empty_row = v.Html(tag="tr", class_="v-no-hover", children=[empy_cell])
            rows = [BaseRow(lyr) for lyr in bases]
            radios = [row.w_radio for row in rows]
            base_rows = head + rows + [empty_row]

        # create a table from these rows
        tbody = v.Html(tag="tbody", children=vector_rows + layer_rows + base_rows)
        table = v.Table(children=[tbody], density="compact", class_="v-no-border")
        self.group = _Selection(radios, v_model=current.name)

        # set the table as children of the widget, the previous one is discarded
        previous = self.tile.children
        self.tile.children = [table]
        close_tree(*previous)

        return
