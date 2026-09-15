"""The built-in message import stays independent of legacy translation and UI."""

import subprocess
import sys


def test_message_import_is_lazy_and_leaves_home_untouched(tmp_path):
    home = tmp_path / "home"
    home.mkdir(mode=0o500)
    source = """
import sys

class BlockDependencies:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"pysepal.translator", "pysepal.i18n", "solara", "pandas", "box"}:
            raise ImportError(f"eager dependency: {fullname}")

sys.meta_path.insert(0, BlockDependencies())
import pysepal.message
assert callable(pysepal.message.msg)
assert not hasattr(pysepal.message, "ms")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-c", source],
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert list(home.iterdir()) == []
    finally:
        home.chmod(0o700)
