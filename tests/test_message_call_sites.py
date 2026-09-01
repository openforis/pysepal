"""Every ``msg()`` call in pysepal must render.

A ``Translator`` lookup returned the raw template, so a message could hold
literal braces -- ``projects/{project}/assets/asset_name`` -- and display them.
``msg()`` formats instead, which turns those braces into a required value and
raises at render time. Only the GEE-marked tests exercised some of these call
sites, so the mistake reached CI before anything caught it.
"""

import ast
from pathlib import Path
from typing import List, Set, Tuple

import pytest

from pysepal.message import msg

PYSEPAL = Path(__file__).parent.parent / "pysepal"


def _literal_call_sites() -> List[Tuple[str, int, str, Set[str]]]:
    """Collect every ``msg("literal", ...)`` call in pysepal.

    Returns:
        One tuple per call: file, line, key, and the names it passes.
    """
    found = []
    for path in sorted(PYSEPAL.rglob("*.py")):
        source = path.read_text()
        if "msg(" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id in ("msg", "_msg")):
                continue
            if not (node.args and isinstance(node.args[0], ast.Constant)):
                continue
            if not isinstance(node.args[0].value, str):
                continue
            names = {k.arg for k in node.keywords if k.arg}
            found.append((str(path), node.lineno, node.args[0].value, names))
    return found


SITES = _literal_call_sites()


def test_the_scan_finds_call_sites() -> None:
    """A scan that finds nothing would pass the test below for the wrong reason."""
    assert len(SITES) > 50, len(SITES)


@pytest.mark.parametrize("path,line,key,names", SITES, ids=[f"{s[2]}" for s in SITES])
def test_call_site_renders(path: str, line: int, key: str, names: Set[str]) -> None:
    """The key exists and the message needs exactly the values the call passes.

    Args:
        path: file holding the call
        line: line of the call
        key: the catalogue key it asks for
        names: the placeholder names it passes
    """
    msg(key, **{name: "x" for name in names})
