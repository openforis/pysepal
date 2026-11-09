"""Custom widgets that are nor input nor UI interface.

Gather the customized ``ipyvuetifyWidgets``. All the content of this modules is included in the parent ``pysepal.sepalwidgets`` package. So it can be imported directly from there.

Example:
    .. jupyter-execute::

        from pysepal import sepalwidgets as sw

        sw.CopyToClip()
"""

from pathlib import Path
from typing import Optional

import ipyvuetify as v
import traitlets as t
from deprecated.sphinx import versionadded
from markdown import markdown
from traitlets import link, observe

from pysepal.model import Model
from pysepal.sepalwidgets.sepalwidget import SepalWidget, Tooltip

__all__ = ["Markdown", "CopyToClip", "StateIcon"]


class Markdown(v.Layout, SepalWidget):

    mkd_str: t.Unicode = t.Unicode("")
    "the markdown text to display; setting it rebuilds the HTML"

    def __init__(self, mkd_str: str = "", **kwargs) -> None:
        """Custom Layout based on the markdown text given.

        Args:
            mkd_str: the text to display using the markdown convention. multi-line string are also interpreted
            kwargs: Any parameter from a v.Layout. If set, 'children' will be overwritten
        """
        self._html = v.VuetifyTemplate(template=self._to_html(""))

        # set default parameters
        kwargs.setdefault("row", True)
        kwargs.setdefault("class_", "pa-5")
        kwargs.setdefault("align_center", True)
        kwargs["children"] = [v.Flex(xs12=True, children=[self._html])]

        # call the constructor
        super().__init__(mkd_str=mkd_str, **kwargs)

    @staticmethod
    def _to_html(mkd_str: str) -> str:
        """Convert the markdown text to the HTML template of the widget."""
        mkd = markdown(mkd_str, extensions=["fenced_code", "sane_lists"])

        # need to be nested in a div to be displayed
        mkd = "<div>\n" + mkd + "\n</div>"

        # make every link to point to target black (to avoid nested iframe in sepal)
        return mkd.replace("<a", '<a target="_blank"')

    @observe("mkd_str")
    def _update_html(self, change: dict) -> None:
        """Rebuild the HTML when the markdown text changes."""
        self._html.template = self._to_html(change["new"])


@versionadded(version="2.2.0", reason="New clipping widget")
class CopyToClip(v.VuetifyTemplate):

    tf: Optional[v.TextField] = None
    "v.TextField: the textfield widget that holds the v_model to copy"

    v_model: t.Unicode = t.Unicode("").tag(sync=True)
    "a v_model trait that embed the string to copy"

    def __init__(self, **kwargs) -> None:
        """Custom textField that provides a handy copy-to-clipboard javascript behaviour.

        When the clipboard btn is clicked the v_model will be copied in the local browser clipboard. You just have to change the clipboard v_model. when copied, the icon change from a copy to a check.

        Args:
            kwargs: any argument that can be used with a v.TextField
        """
        # add the default params to kwargs
        kwargs.setdefault("outlined", True)
        kwargs.setdefault("label", "Copy To clipboard")
        kwargs.setdefault("readonly", True)
        kwargs.setdefault("append_icon", "fa-solid fa-clipboard")
        kwargs.setdefault("v_model", "")
        kwargs.setdefault("class_", "ma-5")

        # set the default v_model
        self.v_model = kwargs["v_model"]

        # create component
        self.tf = v.TextField(**kwargs)
        self.components = {"mytf": self.tf}

        # template with js behaviour
        js_dir = Path(__file__).parents[1] / "frontend/js"
        clip = (js_dir / "jupyter_clip.js").read_text()
        self.template = "<mytf/>" "<script>{methods: {jupyter_clip(_txt) {%s}}}</script>" % clip

        super().__init__()

        # js behaviour
        self.tf.on_event("click:append", self._clip)
        link((self, "v_model"), (self.tf, "v_model"))

    def _clip(self, *args) -> None:
        """Launch the javascript clipping process."""
        self.send({"method": "clip", "args": [self.tf.v_model]})
        self.tf.append_icon = "fa-solid fa-clipboard-check"

        return


class StateIcon(Tooltip):

    values: t.Any = t.Any().tag(sync=True)
    "bool, str, int: key name of the current state of component. Values must be same as states_dict keys."

    states: dict = {}
    'Dictionary where keys are the state name to be linked with self value and value represented by a tuple of two elements. {"key":(tooltip_msg, color)}.'

    icon: Optional[v.Icon]
    "The colored Icon of the tooltip"

    def __init__(
        self,
        model: Optional[Model] = None,
        model_trait: str = "",
        states: dict = {},
        **kwargs,
    ):
        """Custom icon with multiple state colors.

        Args:
            model: Model to manage StateIcon behaviour from outside.
            model_trait: Name of trait to be linked with state icon. Must exists in model.
            states: Dictionary where keys are the state name to be linked with self value and value represented by a tuple of two elements. {"key":(tooltip_msg, color)}.
            kwargs: Any arguments from a v.Tooltip
        """
        # set the default parameter of the tooltip
        kwargs.setdefault("right", True)

        # init the states
        default_states = {
            "valid": ("Valid", "success"),
            "non_valid": ("Not valid", "error"),
        }
        self.states = default_states if not states else states

        # Get the first value (states first key) to use as default one
        init_value = self.states[next(iter(self.states))]

        self.icon = v.Icon(children=["fa-solid fa-circle"], color=init_value[1], small=True)

        super().__init__(self.icon, init_value[0], **kwargs)

        # Directional from there to link here.
        if all([model, model_trait]):
            link((model, model_trait), (self, "values"))

    @observe("values")
    def _swap(self, change: dict) -> None:
        """Swap between states."""
        new_val = change["new"]

        # Use the first value when there is not initial value.
        if not new_val:
            self.value = next(iter(self.states))
            return

        # Perform a little check with comprehensive error message
        if new_val not in self.states:
            raise ValueError(
                f"Value '{new_val}' is not a valid value. Use {list(self.states.keys())}"
            )
        self.icon.color = self.states[new_val][1]
        self.children = [self.states[new_val][0]]

        return
