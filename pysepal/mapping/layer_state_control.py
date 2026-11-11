"""A specific statebar dedicated to the the counting of loading tiles in the map."""

from typing import Optional

import ipyvuetify as v
import traitlets as t
from ipyleaflet import Map, WidgetControl
from ipywidgets import link
from traitlets import observe
from typing_extensions import Self

from pysepal._sepal_widget import SepalWidget
from pysepal.mapping._widget_tree import close_tree
from pysepal.message import msg


class _StateBar(v.Sheet, SepalWidget):

    msg: t.Unicode = t.Unicode("").tag(sync=True)
    "the displayed message"

    loading: t.Bool = t.Bool(False).tag(sync=True)
    "either or not the circular progress is spinning"

    progress: Optional[v.ProgressCircular] = None
    "The ProgressCircular widget that will be displayed in the statebar"

    def __init__(self, **kwargs) -> None:
        """Inline status bar: a small spinner and a message.

        A ``v.Sheet`` rather than a ``v.SystemBar``, which is a layout item that needs a
        ``v-layout`` parent.

        Args:
            kwargs (optional): any parameter from the Sheet widget. If set, 'children' will be overwritten.
        """
        self.progress = v.ProgressCircular(
            indeterminate=self.loading, size=15, color="primary", class_="mr-2", model_value=100
        )

        kwargs.setdefault("class_", "d-flex align-center px-2 text-body-2")
        kwargs.setdefault("height", 24)
        kwargs.setdefault("color", "surface-light")

        kwargs["children"] = [self.progress, self.msg]

        super().__init__(**kwargs)

        link((self, "loading"), (self.progress, "indeterminate"))

    @observe("loading")
    def _change_loading(self, *args) -> None:
        """Change progress wheel state."""
        self.progress.indeterminate = self.loading

    @observe("msg")
    def _change_msg(self, *args) -> None:
        """Change state bar message."""
        self.children = [self.progress, self.msg]

    def add_msg(self, msg: str, loading: bool = False) -> Self:
        """Change current status message.

        Args:
            msg: the message to display
            loading: the loading status of the progress circular
        """
        self.msg = msg
        self.loading = loading

        return self


class LayerStateControl(WidgetControl):

    m: Optional[Map] = None
    "the map connected to the control"

    w_state: Optional[_StateBar] = None
    "the stateBar displaying the number of layer loading on the map"

    nb_layer: t.Int = t.Int(0).tag(sync=True)
    "the number of layers in the map"

    nb_loading_layer: t.Int = t.Int(0).tag(sync=True)
    "the number of loading layer in the map"

    _watched: tuple = ()
    "the layers whose loading trait this control observes"

    def __init__(self, m: Map, **kwargs) -> None:
        """A specific statebar dedicated to the the counting of loading tiles in the map.

        every time a map is added to the map the counter will be raised by one. same behaviour with removed.

        Args:
            m: The map the component is listening to
        """
        # save the map as a member of the widget
        self.m = m
        self._watched = []

        # create a statebar
        text = msg("layer_state.complete", count=self.nb_layer)
        self.w_state = _StateBar(loading=False, msg=text)

        # overwrite the widget set in the kwargs (if any)
        kwargs["widget"] = self.w_state
        kwargs.setdefault("position", "topleft")
        kwargs["transparent_bg"] = True

        # create the widget
        super().__init__(**kwargs)

        # add js behaviour
        self.m.observe(self.update_nb_layer, "layers")

    def close(self) -> None:
        """Stop observing the map and its layers, then close the statebar."""
        if self.m is not None:
            self.m.unobserve(self.update_nb_layer, "layers")
        watched, self._watched = self._watched, []
        for layer in watched:
            layer.unobserve(self.update_loading, "loading")
        close_tree(self.w_state)
        self.m = None
        super().close()

    def update_nb_layer(self, change: dict) -> None:
        """Update the number of layer monitored by the statebar."""
        # exit if nothing changed
        # for example we change a layer parameters and it trigger this one
        if len(change["new"]) == len(change["old"]):
            return

        self.nb_layer = len([lyr for lyr in change["new"] if not lyr.base])

        # identify the modified layer
        modified_layer = list(set(change["new"]) ^ set(change["old"]))[0]
        if modified_layer.base is True:
            return

        # add a layer
        if len(change["new"]) > len(change["old"]):
            modified_layer.observe(self.update_loading, "loading")
            self._watched.append(modified_layer)

        # remove a layer
        elif len(change["new"]) < len(change["old"]):
            # the layer may outlive the map, and a bound method holds this control
            if modified_layer in self._watched:
                self._watched.remove(modified_layer)
                modified_layer.unobserve(self.update_loading, "loading")

            # the test is split as not all the layers have a loading trait
            if hasattr(modified_layer, "loading") is True:
                if modified_layer.loading is True:
                    self.nb_loading_layer += -1

        return

    def update_loading(self, change: dict) -> None:
        """Update the nb_loading_layer value according to the number of tile loading on the map."""
        increment = [-1, 1]
        self.nb_loading_layer += increment[change["new"]]

        return

    @observe("nb_loading_layer", "nb_layer")
    def _update_state(self, *args) -> None:

        # check if anything is loading
        self.loading = bool(self.nb_loading_layer)

        # update the message
        if self.loading is True:
            text = msg("layer_state.loading", loading=self.nb_loading_layer, total=self.nb_layer)
        else:
            text = msg("layer_state.complete", count=self.nb_layer)

        self.w_state.msg = text

        return
