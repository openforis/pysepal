"""Old ``export_*`` module paths, kept as aliases until pysepal 5."""

import importlib
import sys
import warnings


def alias(old_name: str, new_name: str) -> None:
    """Make the module ``old_name`` the module ``new_name``, with a deprecation warning.

    The import system returns whatever ``sys.modules`` holds once a module has
    run, so ``from <old_name> import x`` and monkeypatching the old path both
    reach the new module.
    """
    warnings.warn(
        f"{old_name} is deprecated and will be removed in pysepal 5. "
        f"Import from {new_name} instead.",
        DeprecationWarning,
        stacklevel=3,
    )
    sys.modules[old_name] = importlib.import_module(new_name)
