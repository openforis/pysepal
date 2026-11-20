"""Browser test fixtures: a Solara page with the pysepal-map probes."""

import os
from pathlib import Path

import pytest

# The generic widget has no Vuetify to warm up.
os.environ.setdefault("SOLARA_TEST_VUETIFY_WARMUP", "false")

HARNESS = Path(__file__).parent / ".build" / "harness.js"


@pytest.fixture
def harness(solara_test, page_session):
    """The test page with the probes of harness.ts loaded as ``psmHarness``."""
    if not HARNESS.exists():
        pytest.fail(f"{HARNESS} is missing: run `npm run build:harness`")
    page_session.add_script_tag(path=HARNESS)
    return page_session
