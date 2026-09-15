"""pysepal.i18n must not pull in the Solara integration surface.

Importing anything under ``pysepal.solara`` executes its package ``__init__``,
which imports session management, notifications and the rest. A message
catalogue needs a runtime scope and a locale, nothing more. Piece 3 will add
the scope dependency through the private top-level modules, so this assertion
must keep holding then too.
"""

import subprocess
import sys
from pathlib import Path

import pysepal.i18n

PROBE = "import sys, pysepal.i18n; print('pysepal.solara' in sys.modules)"


def test_importing_the_catalogue_does_not_import_pysepal_solara():
    # cwd pinned to the repo root: -c puts cwd on sys.path first, and pysepal
    # is installed editable against a different checkout, so an inherited cwd
    # elsewhere would probe that checkout instead of this one.
    probe = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(pysepal.__file__).parent.parent,
    )
    assert probe.stdout.strip().splitlines()[-1] == "False", probe.stderr


def test_the_public_surface_is_what_the_spec_names():
    assert sorted(pysepal.i18n.__all__) == [
        "CatalogError",
        "CatalogProblem",
        "MessageFormatError",
        "MissingMessageError",
        "catalog",
        "current_locale",
        "set_locale",
    ]


def test_there_is_exactly_one_lookup_entry_point():
    """A second public lookup would recreate the failure approach B was rejected for."""
    assert not hasattr(pysepal.i18n, "use_msg")
    assert not hasattr(pysepal.i18n, "resolve")
