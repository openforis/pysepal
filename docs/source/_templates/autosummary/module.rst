{% extends "!autosummary/module.rst" %}

{% block modules -%}
{# The stubs only raise an ImportError, so autosummary cannot import them. -#}
{% set stubs = ["aoi_control", "draw_control", "fullscreen_control", "geojson_utils", "inspector_control", "layer", "layer_state_control", "layers_control", "legend_control", "marker_cluster", "menu_control", "zoom_control"] -%}
{% if modules -%}
.. rubric:: Modules

.. autosummary::
   :toctree:
   :recursive:

   {% for item in modules -%}
   {% if item.split(".")[-1] not in stubs -%}
   {{ item }}
   {% endif -%}
   {% endfor -%}

{% endif -%}
{% endblock -%}

{% block functions -%}
{% if functions -%}
.. rubric:: Functions

.. autosummary::
   :toctree:
   :nosignatures:

   {% for item in functions -%}
   {% if item not in inherited_members -%}
   {{ item }}
   {% endif -%}
   {% endfor -%}

{% endif -%}
{% endblock -%}

{% block classes -%}
{% if classes -%}
.. rubric:: Classes

.. autosummary::
   :toctree:
   :template: autosummary/class.rst

   {% for item in classes -%}
   {% if item not in inherited_members -%}
   {{ item }}
   {% endif -%}
   {% endfor -%}

{% endif -%}
{% endblock -%}
