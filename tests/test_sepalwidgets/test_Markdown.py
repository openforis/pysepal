"""Test the Markdown widget."""

import ipyvuetify as v
import solara

from pysepal import sepalwidgets as sw


def test_init() -> None:
    """Init the widget."""
    # default init
    mkd_widget = sw.Markdown()
    expected = "<div>\n\n</div>"
    assert isinstance(mkd_widget, v.Layout)
    assert isinstance(mkd_widget.children[0], v.Flex)
    assert mkd_widget.children[0].children[0].html == expected

    return


def test_init_exhaustive() -> None:
    """Init the widget."""
    # exhaustive
    txt = "toto"
    expected = f"<div>\n<p>{txt}</p>\n</div>"
    mkd_widget = sw.Markdown(txt)
    assert mkd_widget.children[0].children[0].html == expected

    return


def test_init_link() -> None:
    """Test links are set to be opened in a blank page."""
    # add a link
    link_name = "toto"
    link = "#"
    txt = f"[{link_name}]({link})"
    expected = f'<div>\n<p><a target="_blank" href="{link}">{link_name}</a></p>\n</div>'
    mkd_widget = sw.Markdown(txt)
    assert mkd_widget.children[0].children[0].html == expected

    return


def test_set_mkd_str() -> None:
    """Setting the text rebuilds the HTML and keeps the template."""
    mkd_widget = sw.Markdown("toto")
    template = mkd_widget.children[0].children[0].template
    mkd_widget.mkd_str = "tutu"
    assert mkd_widget.children[0].children[0].html == "<div>\n<p>tutu</p>\n</div>"
    # a new template makes the frontend build all the widgets around it again
    assert mkd_widget.children[0].children[0].template == template

    return


def test_element_rerender_updates_html() -> None:
    """A re-render with a new text updates the same widget."""
    text = solara.reactive("toto")

    @solara.component
    def Page():
        sw.Markdown.element(mkd_str=text.value)

    _, rc = solara.render(Page(), handle_error=False)
    try:
        mkd_widget = rc.find(sw.Markdown).widget
        text.value = "tutu"
        assert rc.find(sw.Markdown).widget is mkd_widget
        assert mkd_widget.children[0].children[0].html == "<div>\n<p>tutu</p>\n</div>"
    finally:
        rc.close()

    return
