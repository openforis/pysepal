"""Decorators used in sepal-ui.

used for multiple use-case sucha as (but not limited):
- catch errors in scripts to avoid Voila app freeze
- redirect error to a specific Alert object
- Initialize EE
- debug widgets
...
"""

from functools import wraps
from itertools import product
from typing import Any, List

from deprecated.sphinx import versionadded

from pysepal.scripts.gee import init_ee, need_ee  # noqa: F401 - backward compatibility


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
