"""Decorators used in sepal-ui.

used for multiple use-case sucha as (but not limited):
- catch errors in scripts to avoid Voila app freeze
- redirect error to a specific Alert object
- Initialize EE
- debug widgets
...
"""

import warnings
from functools import wraps
from itertools import product
from typing import Any, List, Optional
from warnings import warn

import ipyvuetify as v
from deprecated.sphinx import versionadded

from pysepal.message import msg
from pysepal.scripts.gee import init_ee, need_ee  # noqa: F401 - backward compatibility
from pysepal.scripts.warning import SepalWarning


@versionadded(version="3.0", reason="moved from utils to a dedicated module")
def catch_errors(alert: Optional[v.Alert] = None, debug: Optional[bool] = None) -> Any:
    """Decorator to execute try/except sentence and catch errors in the alert message.

    If debug is True then the error is raised anyway.

    Args:
        alert: Alert to display errors
        debug: Whether to raise the error or not, default to false

    Returns:
        The return statement of the decorated method
    """
    if debug is not None:
        warn("debug argument defaults to `True`. It will be removed in v3.2")

    def decorator_alert_error(func):
        @wraps(func)
        def wrapper_alert_error(self, *args, **kwargs):
            # Change name of variable to assign it again in this scope
            # check if alert exist in the parent object if alert is not set manually
            assert hasattr(self, "alert") or alert, msg("decorator.no_alert")
            alert_ = self.alert if not alert else alert
            alert_.reset()

            # try to execute the method
            value = None
            try:
                # Catch warnings in the process function
                with warnings.catch_warnings(record=True) as w_list:
                    value = func(self, *args, **kwargs)

                # Check if there are warnings in the function and append them
                # Use append msg as several warnings could be triggered
                if w_list:
                    # split the warning list
                    w_list_sepal = [w for w in w_list if isinstance(w.message, SepalWarning)]

                    # display the sepal one
                    ms_list = [f"{w.category.__name__}: {w.message.args[0]}" for w in w_list_sepal]
                    [alert_.append_msg(ms, type_="warning") for ms in ms_list]

                    def custom_showwarning(w):
                        return warnings.showwarning(
                            message=w.message,
                            category=w.category,
                            filename=w.filename,
                            lineno=w.lineno,
                            line=w.line,
                        )

                    [custom_showwarning(w) for w in w_list]

            except Exception as e:
                alert_.add_msg(f"{e}", type_="error")
                raise e

            return value

        return wrapper_alert_error

    return decorator_alert_error


@versionadded(version="3.0", reason="moved from utils to a dedicated module")
def loading_button(
    alert: Optional[v.Alert] = None,
    button: Optional[v.Btn] = None,
    debug: Optional[bool] = None,
) -> Any:
    """Decorator to execute try/except sentence and toggle loading button object.

    Designed to work within the Tile object, or any object that have a self.btn and self.alert set.

    Args:
        button: Toggled button
        alert: the alert to display the error message
        debug: Whethers or not the exception should stop the execution. default to False

    Returns:
        The return statement of the decorated method
    """
    if debug is not None:
        warn("debug argument defaults to `True`. It will be removed in v3.2")

    def decorator_loading(func):
        @wraps(func)
        def wrapper_loading(self, *args, **kwargs):
            # set btn and alert
            # Change name of variable to assign it again in this scope
            # check if they exist in the parent object if alert is not set manually
            assert hasattr(self, "alert") or alert, msg("decorator.no_alert")
            assert hasattr(self, "btn") or button, msg("decorator.no_button")
            button_ = self.btn if not button else button
            alert_ = self.alert if not alert else alert

            # Clean previous loaded messages in alert
            alert_.reset()

            button_.toggle_loading()  # Start loading

            value = None

            try:
                # run the function using the catch_error decorator
                value = catch_errors(alert=alert_)(func)(self, *args, **kwargs)

            except Exception as e:
                button_.toggle_loading()
                raise e

            # normal behavior where we stop the loading state after the function is executed
            button_.toggle_loading()

            return value

        return wrapper_loading

    return decorator_loading


@versionadded(version="3.0", reason="moved from utils to a dedicated module")
def switch(
    *params, debug: bool = True, on_widgets: List[str] = [], targets: List[bool] = []
) -> Any:
    r"""Decorator to switch the state of input boolean parameters on class widgets or the class itself.

    If on_widgets is defined, it will switch the state of every widget
    parameter, otherwise it will change the state of the class (self). You can also set
    two decorators on the same function, one could affect the class and other the widgets.

    Args:
        \*params: any boolean parameter of a SepalWidget.
        debug: Whether trigger or not an Exception if the decorated function fails.
        on_widgets: List of widget names into the class
        targets: list of the target value (value that will be set on switch. default to the inverse of the current state.

    Returns:
        The return statement of the decorated method
    """

    def decorator_switch(func):
        @wraps(func)
        def wrapper_switch(self, *args, **kwargs):
            widgets_len = len(on_widgets)
            targets_len = len(targets)

            # sanity check on targets and on_widgets
            if widgets_len and targets_len:
                if widgets_len != targets_len:
                    raise IndexError(
                        f'the length of "on_widgets" ({widgets_len}) is different from the length of "targets" ({targets_len})'
                    )

            # create the list of target values based on the target list
            # or the initial values of the widgets params
            # The first one is taken as reference
            if not targets_len:
                w = getattr(self, on_widgets[0]) if widgets_len else self
                targets_ = [bool(getattr(w, p)) for p in params]
            else:
                targets_ = targets

            if widgets_len:
                # Verify that the input elements are strings
                wrong_types = [(w, type(w)) for w in on_widgets if not isinstance(w, str)]

                if len(wrong_types):
                    errors = [f"Received:{w_type} for widget: {w}." for w, w_type in wrong_types]

                    raise TypeError(
                        f"All on_widgets list elements has to be strings. [{' '.join(errors)}]"
                    )

                missing_widgets = [w for w in on_widgets if not hasattr(self, w)]

                if missing_widgets:
                    raise Exception(
                        f"The provided {missing_widgets} widget(s) does not exist in the current class"
                    )

                def w_assign(bool_targets):
                    params_targets = [(p, bool_targets[i]) for i, p in enumerate(params)]

                    for w_name, p_t in product(on_widgets, params_targets):
                        param, target = p_t
                        widget = getattr(self, w_name)
                        setattr(widget, param, target)

            else:

                def w_assign(bool_targets):
                    for i, p in enumerate(params):
                        setattr(self, p, bool_targets[i])

            # assgn the parameters to the target inverse
            w_assign([not t for t in targets_])

            # execute the function and catch errors
            try:
                func(self, *args, **kwargs)

            except Exception as e:
                if debug:
                    w_assign(targets_)
                    raise e

            # reassign the parameters to the targets
            w_assign(targets_)

        return wrapper_switch

    return decorator_switch
