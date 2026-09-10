"""Extend functionalities of the ipyleaflet layer control."""

from types import SimpleNamespace
from typing import Optional

from ipyleaflet import GeoJSON, Layer, Map, TileLayer
from ipywidgets import link

from pysepal import sepalwidgets as sw
from pysepal.mapping.menu_control import MenuControl
from pysepal.message import msg


class HeaderRow(sw.Html):
    def __init__(self, title: str) -> None:
        """Html Row element including a single title of 3 colspan.

        Specifically designed to work in the layer_control table

        Args:
            title: the line value
        """
        attr = {"colspan": 3}
        head = sw.Html(tag="th", attributes=attr, children=title)
        super().__init__(tag="tr", class_="v-no-hover", children=[head])


class BaseRow(sw.Html):

    w_radio: Optional[sw.SimpleCheckbox] = None
    "the radio to hide/show the layer"

    def __init__(self, layer: TileLayer) -> None:
        """Html row element to describe a base layer.

        This Html element include all the controls to manipulate the basemap displayed in the map
        - a checkbox to show/hide (it will behave like a radio)

        Args:
            layer: the layer associated to the row
        """
        # create the checkbox, by default layer are visible
        self.w_radio = sw.Radio(small=True, value=layer.name)
        kwargs = {"style": "width: 10%;", "tag": "td"}
        radio_cell = sw.Html(children=[self.w_radio], **kwargs)

        # create the label
        kwargs = {"style_": "width: 40%;", "tag": "td"}
        label_cell = sw.Html(children=[layer.name], **kwargs)

        # create an empty row to align on
        kwargs = {"style_": "width: 50%;", "tag": "td"}
        empty_cell = sw.Html(children=[""], **kwargs)

        # build a html tr from it
        super().__init__(tag="tr", children=[label_cell, empty_cell, radio_cell])

        # add js behavior
        link((layer, "visible"), (self.w_radio, "active"))


class LayerRow(sw.Html):

    w_checkbox: Optional[sw.SimpleCheckbox] = None
    "the ckeckbox to hide/show the layer"

    w_slider: Optional[sw.SimpleSlider] = None
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
        self.w_checkbox = sw.SimpleCheckbox(
            v_model=True, small=True, label=layer.name, color="primary"
        )
        kwargs = {"style": "width: 10%;", "tag": "td"}
        checkbox_cell = sw.Html(children=[self.w_checkbox], **kwargs)

        # create the label
        kwargs = {"style_": "width: 40%;", "tag": "td"}
        label_cell = sw.Html(children=[layer.name], **kwargs)

        # create the slider
        self.w_slider = sw.SimpleSlider(v_model=1, max=1, step=0.01, small=True)
        kwargs = {"style_": "width: 50%;", "tag": "td"}
        slider_cell = sw.Html(children=[self.w_slider], **kwargs)

        # build a html tr from it
        super().__init__(tag="tr", children=[label_cell, slider_cell, checkbox_cell])

        # add js behavior
        self.w_checkbox.observe(self._toggle_slider, "v_model")
        link((layer, "opacity"), (self.w_slider, "v_model"))
        link((layer, "visible"), (self.w_checkbox, "v_model"))

    def _toggle_slider(self, *args) -> None:
        """Toggle the modification of the slider."""
        self.w_slider.disabled = not self.w_checkbox.v_model

        return


class VectorRow(sw.Html):

    w_checkbox: Optional[sw.SimpleCheckbox] = None
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
        self.w_checkbox = sw.SimpleCheckbox(
            v_model=True, small=True, label=layer.name, color="primary"
        )
        kwargs = {"style": "width: 10%;", "tag": "td"}
        checkbox_cell = sw.Html(children=[self.w_checkbox], **kwargs)

        # create the label
        kwargs = {"style_": "width: 40%;", "tag": "td"}
        label_cell = sw.Html(children=[layer.name], **kwargs)

        # create the slider
        kwargs = {"style_": "width: 50%;", "tag": "td"}
        empty_cell = sw.Html(children=[""], **kwargs)

        # build a html tr from it
        super().__init__(tag="tr", children=[label_cell, empty_cell, checkbox_cell])

        # add js behavior
        link((layer, "visible"), (self.w_checkbox, "v_model"))


class ToggleRow(sw.Html):

    w_checkbox: Optional[sw.SimpleCheckbox] = None
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
        self.w_checkbox = sw.SimpleCheckbox(
            v_model=layer not in control.hidden, small=True, label=layer.name, color="primary"
        )
        kwargs = {"style": "width: 10%;", "tag": "td"}
        checkbox_cell = sw.Html(children=[self.w_checkbox], **kwargs)

        # create the label
        kwargs = {"style_": "width: 40%;", "tag": "td"}
        label_cell = sw.Html(children=[layer.name], **kwargs)

        # create an empty row to align on
        kwargs = {"style_": "width: 50%;", "tag": "td"}
        empty_cell = sw.Html(children=[""], **kwargs)

        # build a html tr from it
        super().__init__(tag="tr", children=[label_cell, empty_cell, checkbox_cell])

        # add js behavior
        self.w_checkbox.observe(self._toggle_layer, "v_model")

    def _toggle_layer(self, *args) -> None:
        """Add or remove the layer from the map."""
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

    group: Optional[sw.RadioGroup] = None
    "As radio button cannot behave individually we add an extra GroupRadio to wrap the table"

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
        self.w_loading = sw.ProgressLinear(
            indeterminate=False,
            background_color="menu",
        )
        self.tile = sw.Tile("nested", "")

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

    def update_table(self, change: dict) -> None:
        """Update the table content."""
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
        base_rows = []
        current = next((lyr for lyr in bases if lyr.visible is True), SimpleNamespace(name=None))
        if len(bases) > 0:
            head = [HeaderRow(msg("layer_control.basemap.header"))]
            empy_cell = sw.Html(tag="td", children=[" "], attributes={"colspan": 3})
            empty_row = sw.Html(tag="tr", class_="v-no-hever", children=[empy_cell])
            rows = [BaseRow(lyr) for lyr in bases] + [empty_row]
            base_rows = head + rows

        # create a table from these rows and wrap it in the radioGroup
        tbody = sw.Html(tag="tbody", children=vector_rows + layer_rows + base_rows)
        table = sw.SimpleTable(children=[tbody], dense=True, class_="v-no-border")
        self.group = sw.RadioGroup(v_model=current.name, children=[table])

        # set the table as children of the widget
        self.tile.children = [self.group]

        return
