"""Custom widgets relative to user outputs.

Gather the customized ``ipyvuetifyWidgets`` used to communicate with the end user.
All the content of this modules is included in the parent ``pysepal.sepalwidgets`` package. So it can be imported directly from there.

Example:
    .. jupyter-execute::

        from pysepal import sepalwidgets as sw

        sw.Alert().show()
"""

from datetime import datetime
from typing import Any, Optional

import ipyvuetify as v
import traitlets as t
from deprecated.sphinx import deprecated
from ipywidgets import Output
from tqdm.notebook import tqdm
from traitlets import directional_link, link, observe
from typing_extensions import Self

from pysepal import color
from pysepal.frontend.styles import TYPES
from pysepal.message import msg

# Two methods below take a `msg` parameter, which shadows the lookup.
from pysepal.message import msg as _msg
from pysepal.scripts import utils as su
from pysepal.scripts.utils import set_type
from pysepal.sepalwidgets.sepalwidget import SepalWidget

__all__ = ["Divider", "Alert", "StateBar", "Banner"]


class Divider(v.Divider, SepalWidget):

    type_: t.Unicode = t.Unicode("").tag(sync=True)
    "Added type\\_ trait to specify the current color of the divider"

    def __init__(self, class_: str = "", **kwargs) -> None:
        r"""A custom Divider with the ability to dynamically change color.

        Whenever the type\_ trait is modified, the divider class will change accordingly.

        Args:
            class\_: the initial color of the divider
            kwargs (optional): any parameter from a v.Divider. if set, 'class\_' will be overwritten.
        """
        kwargs["class_"] = class_
        super().__init__(**kwargs)

    @observe("type_")
    def add_class_type(self, change: dict) -> Self:
        r"""Change the color of the divider according to the type\_.

        It is binded to the type\_ traitlet but can also be called manually.

        Args:
            change: the only useful key is 'new' which is the new required color
        """
        self.class_list.remove(*TYPES)
        self.class_list.add(change["new"])

        return self


class Alert(v.Alert, SepalWidget):

    progress_bar: Optional[tqdm] = None
    "the progress bar of the alert"

    progress_output: Optional[Output] = None
    "the output object where the progress bar is stored"

    def __init__(self, type_: str = "info", **kwargs) -> None:
        r"""A custom Alert widget.

        It is used as the output of all processes in the framework.
        In the voila interfaces, print statement will not be displayed.
        Instead use the sw.Alert method to provide information to the user.
        It's hidden by default.

        Args:
            type\_: The color of the Alert
            kwargs (optional): any parameter from a v.Alert. If set, 'type' will be overwritten.
        """
        # set default parameters
        kwargs.setdefault("text", True)
        kwargs["type"] = set_type(type_)
        kwargs.setdefault("class_", "mt-5")

        # call the constructor
        super().__init__(**kwargs)

        self.hide()
        self.progress_output = Output()
        # self.progress_bar = None

    def update_progress(self, progress: float, msg: str = "Progress", **tqdm_args) -> None:
        """Update the Alert message with a tqdm progress bar.

        .. note::

            set the ``total`` argumentent of tqdm to use different values than [0, 1]

        Args:
            progress: the progress status in float
            msg: The message to use before the progress bar
            tqdm_args (optional): any arguments supported by a tqdm progress bar, they will only be taken into account after a call to ``self.reset()``.
        """
        # show the alert
        self.show()

        # cast the progress to float and perform sanity checks
        progress = float(progress)
        if self.progress_output not in self.children:
            total = tqdm_args.get("total", 1)
        else:
            total = self.progress_bar.total
        if not (0 <= progress <= total):
            raise ValueError(f"progress should be in [0, {total}], {progress} given")

        # Prevent adding multiple times
        if self.progress_output not in self.children:

            self.children = [self.progress_output]

            tqdm_args.setdefault("bar_format", "{l_bar}{bar}{n_fmt}/{total_fmt}")
            tqdm_args.setdefault("dynamic_ncols", False)
            tqdm_args.setdefault("total", 1)
            tqdm_args.setdefault("desc", msg)
            tqdm_args.setdefault("colour", getattr(color, self.type))

            with self.progress_output:
                self.progress_output.clear_output()
                self.progress_bar = tqdm(**tqdm_args)
                self.progress_bar.container.children[0].add_class(f"{self.type}--text")
                self.progress_bar.container.children[2].add_class(f"{self.type}--text")

                # Initialize bar
                self.progress_bar.update(0)

        self.progress_bar.update(progress - self.progress_bar.n)

        if progress == total:
            self.progress_bar.close()

        return

    def add_msg(self, msg: str, type_: str = "info") -> Self:
        r"""Add a message in the alert by replacing all the existing one.

        The color can also be changed dynamically.

        Args:
            msg: the message to display
            type\_: the color to use in the widget
        """
        self.show()
        self.type = set_type(type_)
        self.children = [v.Html(tag="p", children=[msg])]

        return self

    def add_live_msg(self, msg: str, type_: str = "info") -> Self:
        r"""Add a message in the alert by replacing all the existing one.

        Also add the timestamp of the display. The color can also be changed dynamically.

        Args:
            msg: the message to display
            type\_: the color to use in the widget
        """
        current_time = datetime.now().strftime("%Y/%m/%d, %H:%M:%S")

        self.show()
        self.type = set_type(type_)
        self.children = [
            v.Html(tag="p", children=["[{}]".format(current_time)]),
            v.Html(tag="p", children=[msg]),
        ]

        return self

    def append_msg(self, msg: str, section: bool = False, type_: str = "info") -> Self:
        r"""Append a message in a new parragraph, with or without divider.

        Args:
            msg: the message to display
            section: add a Divider before the added message
            type\_: the color to use in the widget
        """
        self.show()
        self.type = type_

        if len(self.children):
            current_children = self.children[:]
            if section:
                # As the list is mutable, and the trait is only triggered when
                # the children is changed, so have to create a copy.
                divider = Divider(class_="my-4", style="opacity: 0.22")

                # link Alert type with divider type
                directional_link((self, "type"), (divider, "type_"))
                current_children.extend([divider, v.Html(tag="p", children=[msg])])
                self.children = current_children

            else:
                current_children.append(v.Html(tag="p", children=[msg]))
                self.children = current_children
        else:
            self.add_msg(msg)

        return self

    def remove_last_msg(self) -> Self:
        """Remove the last msg printed in the Alert widget."""
        if len(self.children) > 1:
            current_children = self.children[:]
            self.children = current_children[:-1]
        else:
            self.reset()

        return self

    def reset(self) -> Self:
        """Empty the messages and hide it."""
        self.children = [""]
        self.hide()
        self.type = set_type("info")

        return self

    @deprecated(version="3.0", reason="This method is now part of the utils module")
    def check_input(self, input_: Any, msg: str = "") -> bool:
        r"""Check if the inpupt value is initialized.

        If not return false and display an error message else return True.

        Args:
            input\_: the input to check
            msg: the message to display if the input is not set

        Returns:
            check if the value is initialized
        """
        msg = msg or _msg("utils.check_input.error")

        return su.check_input(input_, msg)


class StateBar(v.SystemBar, SepalWidget):

    msg: t.Unicode = t.Unicode("").tag(sync=True)
    "the displayed message"

    loading: t.Bool = t.Bool(False).tag(sync=True)
    "either or not the circular progress is spinning"

    progress: Optional[v.ProgressCircular] = None
    "The ProgressCircular widget that will be displayed in the statebar"

    def __init__(self, **kwargs) -> None:
        """Widget to display quick messages on simple inline status bar.

        Args:
            kwargs (optional): any parameter from a v.SystemBar. If set, 'children' will be overwritten.
        """
        self.progress = v.ProgressCircular(
            indeterminate=self.loading,
            value=100,
            small=True,
            size=15,
            color="primary",
            class_="mr-2",
        )

        # set default parameter
        kwargs["children"] = [self.progress, self.msg]

        # call the constructor
        super().__init__(**kwargs)

        link((self, "loading"), (self.progress, "indeterminate"))

    @observe("loading")
    def _change_loading(self, *args) -> None:
        """Change progress wheel state."""
        self.progress.indeterminate = self.loading

        return

    @observe("msg")
    def _change_msg(self, *args) -> None:
        """Change state bar message."""
        self.children = [self.progress, self.msg]

        return

    def add_msg(self, msg: str, loading: bool = False) -> Self:
        """Change current status message.

        Args:
            msg: the message to display
            loading: the loading status of the progress circular
        """
        self.msg = msg
        self.loading = loading

        return self


class Banner(v.Snackbar, SepalWidget):

    btn_close: Optional[v.Btn] = None
    "v.Btn: the closing btn of the banner"

    def __init__(
        self,
        msg: str = "",
        type_: str = "info",
        id_: str = "",
        persistent: bool = True,
        **kwargs,
    ) -> None:
        r"""Custom Snackbar widget to display messages as a banner in module App.

        Args:
            msg: Message to display in application banner. default to nothing
            type\_: Used to display an appropriate banner color. fallback to "info".
            id_: unique banner identificator.
            persistent: Whether to close automatically based on the length of message (False) or make it indefinitely open (True). Overridden if timeout duration is set.
            kwargs (optional): any parameter from a v.Alert. If set, 'vertical' and 'top' will be overwritten.
        """
        # compute the type and default to "info" if it's not existing
        type_ = set_type(type_)

        # create the closing btn
        self.btn_close = v.Btn(small=True, text=True, children=[_msg("widgets.banner.close")])

        # compute timeout based on the persistent and timeout parameter
        computed_timeout = 0 if persistent is True else self.get_timeout(msg)

        kwargs.setdefault("color", type_)
        kwargs.setdefault("transition", "scroll-x-transition")
        kwargs["attributes"] = {"id": id_}
        kwargs.setdefault("v_model", True)
        kwargs.setdefault("timeout", computed_timeout)
        kwargs["top"] = True
        kwargs["vertical"] = True
        kwargs["children"] = [msg] + [self.btn_close]
        kwargs["class_"] = "mb-1"

        super().__init__(**kwargs)

        self.btn_close.on_event("click", self.close)

    def close(self, *args) -> None:
        """Close button event to close snackbar alert."""
        self.v_model = False  # mypy: ignore-errors

        return

    def get_timeout(self, text: str) -> int:
        """Calculate timeout in milliseconds to read the message.

        Args:
            text: the text displayed in the banner to adapt the duration of the timeout

        Returns:
            the duration of the timeout in milliseconds
        """
        wpm = 180  # readable words per minute
        word_length = 5  # standardized number of chars in calculable word
        words = len(text) / word_length
        words_time = ((words / wpm) * 60) * 1000

        delay = 1500  # milliseconds before user starts reading the notification
        bonus = 1000  # extra time

        return int(delay + words_time + bonus)

    def set_btn(self, nb_banner: int) -> None:
        """Change the btn display to inform the user on the number of banners in the queue.

        Args:
            nb_banner: the number of banners in the queue
        """
        # do not wrap ms.widget.banner. If you do it won't be recognized by the key-checker of the Translator
        if nb_banner == 0:
            txt = msg("widgets.banner.close")
        else:
            txt = msg("widgets.banner.next", count=nb_banner)
        self.btn_close.children = [txt]

        return
