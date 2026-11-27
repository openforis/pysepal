"""The sepal_ui compatibility package is gone in pysepal 4.0.

Absence is asserted against *this* checkout -- see ``tests._import_probe`` for
why the interpreter at large is the wrong thing to ask.
"""

import subprocess
import sys

from tests._import_probe import REPO_ROOT, defined_in_repo, shipped_locations


def test_sepal_ui_is_not_shipped():
    """Named for what it checks: another clone on the path may still import."""
    shipped = shipped_locations("sepal_ui")
    assert shipped == [], shipped


def test_no_meta_path_finder_resolves_an_import():
    """The shim inserted a MetaPathFinder at sys.meta_path[0]; this tree may not.

    Matching on the class name would both miss a finder that came back under a
    new one and go red for a foreign finder imported from some other clone on
    the path. What settles it is whether the code defining the finder lives in
    this checkout. The one allowed is the removal finder, which resolves nothing:
    it only raises the message for a module or name pysepal 5 removed.
    """
    from pysepal._removed import _FINDER

    ours = [finder for finder in sys.meta_path if defined_in_repo(finder)]
    assert ours == [_FINDER]
    for name in ("sepal_ui", "sepal_ui.mapping", "pysepal.mapping.sepal_map"):
        assert _FINDER.find_spec(name) is None


def test_the_probe_still_sees_a_finder_from_this_checkout():
    """Positive control for the assertion above, which is a claim about absence.

    ``defined_in_repo`` has to reject an in-tree virtualenv's dependencies, and
    the way to get that wrong is to reject everything -- which would leave the
    test above passing no matter what got installed at ``sys.meta_path[0]``.
    """
    from pysepal._removed import _FINDER

    class LocalFinder:
        pass

    sys.meta_path.insert(0, LocalFinder())
    try:
        ours = [finder for finder in sys.meta_path if defined_in_repo(finder)]
    finally:
        sys.meta_path.remove(sys.meta_path[0])

    assert [type(finder).__name__ for finder in ours if finder is not _FINDER] == ["LocalFinder"]


def test_the_package_directory_is_gone():
    assert not (REPO_ROOT / "sepal_ui").exists()


def test_importing_pysepal_emits_no_rename_deprecation():
    code = (
        "import warnings; "
        "warnings.filterwarnings('error', message=\".*'sepal_ui' package is deprecated.*\"); "
        "import pysepal"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
