"""The suite must not depend on a developer's local logging configuration."""

import logging


def test_caplog_captures_a_sepalui_record(caplog):
    """A local logging_config.toml must not blind caplog.

    ``pysepal.logger`` runs ``dictConfig`` at import when it finds a
    ``logging_config.toml`` beside the package, and the shipped example sets
    ``propagate = false`` on ``sepalui``. ``caplog`` attaches at the root, so
    every test that asserts on a log record fails on that developer's machine
    and passes everywhere else.
    """
    with caplog.at_level(logging.WARNING, logger="sepalui"):
        logging.getLogger("sepalui.probe").warning("a message worth capturing")

    assert "a message worth capturing" in caplog.text
