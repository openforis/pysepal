Translate my application
========================

SEPAL tries to be as inclusive as possible. To do so the platform is translated in these languages:

.. csv-table::

    English, Français, Español

:code:`pysepal` gives you a message catalogue so your own application can do the same.

A catalogue is a folder of JSON files, one subfolder per language. You read a
message from it with :code:`msg()`, and the text follows the language the user
picked. Nothing in your code passes a language around.

.. note::

    :code:`Translator` still exists for modules written against pysepal 3. It
    resolves its language when it is constructed, and modules construct it at
    import, so its text cannot follow a language change. New code
    should use :code:`catalog()` and :code:`msg()` described here. See
    ``docs/guides/migration-v4.md`` to move an existing app.


Bind the catalogue
------------------

Bind it once, when your message module is imported. English is read and checked
at that moment, so a mistake in your own file stops the app at startup rather
than on a user's screen.

.. code-block:: python

    # component/message/__init__.py

    from pathlib import Path

    from pysepal.i18n import catalog

    messages = catalog(Path(__file__).parent)
    msg = messages.msg

Then import :code:`msg` anywhere in your module:

.. code-block:: python

    # component/tile/my_tile.py

    from component.message import msg


Write the English messages
--------------------------

English is the source of truth. Every key your application can ask for has to
exist there; the other languages only replace what they translate.

.. code-block:: json

    {
        "app": {
            "title": "My first module",
            "drawer_item": {
                "aoi": "AOI selection",
                "about": "About"
            }
        },
        "error": {
            "no_aoi": "No AOI has been set, please provide one in step 1"
        }
    }

.. danger::

    JSON accepts only " (double quotes).

Read a message with the key path, joined by dots:

.. code-block:: python

    msg("error.no_aoi")
    msg("app.drawer_item.aoi")

A key you did not define raises :code:`MissingMessageError`. That is deliberate:
a missing message is a bug in your app, and it is easier to fix when it names
itself. While you are still filling the catalogue you can ask for a marker
instead:

.. code-block:: python

    messages = catalog(Path(__file__).parent, strict=False)

    msg("error.not_written_yet")   # '⟦error.not_written_yet⟧', and one warning

Put a value in a message
------------------------

Give every placeholder a name and pass it by that name:

.. code-block:: json

    {
        "error": {
            "occurred": "The following error occurred: {detail}"
        }
    }

.. code-block:: python

    try:
        ...
    except Exception as e:
        print(msg("error.occurred", detail=e))

.. important::

    A positional placeholder -- :code:`{}` or :code:`{0}` -- is refused when the
    catalogue binds. A translator cannot reorder positional slots, and word order
    differs between languages, so a named placeholder is the only form accepted.
    Rename :code:`"{}"` to something like :code:`"{detail}"` and update the call
    at the same time.


One or many
-----------

When a message counts something, write it as a node with :code:`one` and
:code:`other` instead of "layer(s)":

.. code-block:: json

    {
        "toasts": {
            "cleared": {
                "one": "1 layer removed",
                "other": "{count} layers removed"
            }
        }
    }

.. code-block:: python

    msg("toasts.cleared", count=1)   # '1 layer removed'
    msg("toasts.cleared", count=3)   # '3 layers removed'

Each language writes its own forms, so French can say "1 couche supprimée" and
"3 couches supprimées".

.. note::

    :code:`count` only selects a form when the English key names a plural node.
    On any other key it is an ordinary named placeholder that fills in a number.

    This release supports :code:`one` and :code:`other`. Languages that need more
    categories fall back to these two.


Translate into the other languages
----------------------------------

Automatic
^^^^^^^^^

If your application is part of the OpenForis initiative and hosted on SEPAL, you
can request to add your project to the **Pontoon** application list. Pontoon is an
open-source translation solution that will deal with the trouble of creating the
files and keeping the keys updated. To learn more, please see their
`documentation <https://mozilla-l10n.github.io/localizer-documentation/tools/pontoon/>`__.
From the developer's side you'll need to add the folder corresponding to the
language you want to support and open a request for a new project in our
`issue tracker <https://github.com/openforis/pysepal/issues/new/choose>`__.

.. note::

    The :code:`pysepal` keys for built-in components are managed on this application.

.. image:: ../_image/tutorials/translate-app/pontoon.png

.. important::

    Pontoon does not support a JSON list and only provides support for named keys.
    Replace a list with a numbered object:

.. code-block:: json

    {
        "paragraph": {
            "0": "I'm a multiline",
            "1": "paragraph."
        }
    }

The numbers become part of the key path:

.. code-block:: python

    msg("paragraph.0")
    msg("paragraph.1")

Manual
^^^^^^

If this is your first translation, copy :code:`en/locale.json` to the target
folder and replace each message with its translation.

If it is not the first, do not copy over what is already translated. Use
:code:`check()` below to find what is missing.

.. note::

    Pontoon exports a string nobody has translated yet as :code:`""`. An empty
    translation is treated as absent, so English shows through rather than a blank
    label.


Check the catalogue
-------------------

:code:`check()` compares every language against English and returns what it finds.
It never raises, so you can call it in a test:

.. code-block:: python

    from component.message import messages

    def test_the_catalogue_is_clean():
        problems = messages.check()
        assert problems == (), [(p.code, p.locale, p.key) for p in problems]

Each record carries :code:`code`, :code:`locale`, :code:`key` and :code:`detail`:

.. csv-table::
    :header: code, meaning

    ``missing_key``, English defines it and this language does not
    ``extra_key``, this language defines a key English does not; it is ignored
    ``placeholder_mismatch``, the translation asks for different values than English
    ``malformed_template``, the translation is not something ``str.format`` can render
    ``shape_mismatch``, one side is a plural node and the other is a plain string
    ``unsupported_plural_category``, a plural form this release cannot select
    ``unreadable_locale``, the folder could not be read at all

A translator's mistake never breaks a render. When a translation cannot be used,
English stays active for that key and :code:`check()` reports it.


Change the language
-------------------

The language lives in the connection, not in your components. Read it and set it
with:

.. code-block:: python

    from pysepal.i18n import current_locale, set_locale

    current_locale()   # 'en' until something sets one
    set_locale("fr")   # any IETF BCP 47 code, in any casing

A component that calls :code:`msg()` re-renders on its own when the language
changes. You do not need to rebuild anything or reload the page.

The language selector in the app bar writes the user's choice here. Offer it the
languages your catalogue actually ships:

.. code-block:: python

    MapApp.element(
        app_title=msg("app.title"),
        locales=messages.available_locales(),
    )

.. note::

    :code:`set_locale()` cannot choose the language your app starts in. A mounted
    selector resolves the browser's language on its first mount and writes that
    back, overwriting anything set before it. Call :code:`set_locale()` from a user
    action instead.

.. warning::

    An ipywidget keeps the text it was given when it was built. Widgets from
    :code:`pysepal.sepalwidgets` therefore show the language that was active at
    that moment. Solara components re-render and follow the language live.
