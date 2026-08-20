"""Serializable record of an AOI selection.

``AoiSpec`` holds what the user picked; ``AoiResult`` holds what that selection
produced. Only the spec is JSON-safe, so it is the thing an app persists — the
GeoDataFrame and the Earth Engine object are rebuilt from it on load.
"""

from copy import deepcopy
from dataclasses import dataclass, fields
from typing import Any, Dict, Mapping, Optional, Tuple

from deprecated.sphinx import versionadded

#: Bumped whenever a persisted payload stops being readable by ``from_dict``.
AOI_SPEC_SCHEMA_VERSION: int = 1

ADMIN_METHODS: Tuple[str, ...] = ("ADMIN0", "ADMIN1", "ADMIN2")


@dataclass(frozen=True)
@versionadded(version="4.0", reason="Serializable AOI selection state")
class AoiSpec:
    """The inputs that produced an AOI, in a JSON-safe form.

    Attributes:
        method: Selection method ("ADMIN0", "ADMIN1", "ADMIN2", "SHAPE", "POINTS",
            "DRAW" or "ASSET").
        schema_version: Payload version, checked by :meth:`from_dict`.
        admin_codes: For admin methods, every GAUL code from level 0 down to the
            method's level, e.g. ``("101", "1001", "100001")`` for ADMIN2. The whole
            path is stored so the cascade can be restored without a reverse lookup.
        pathname: For SHAPE and POINTS, the vector or table file path.
        column: For SHAPE and ASSET, the filter column, or ``"ALL"``.
        value: For SHAPE and ASSET, the filter value.
        id_column: For POINTS, the id column name.
        lat_column: For POINTS, the latitude column name.
        lng_column: For POINTS, the longitude column name.
        geo_json: For DRAW, the raw GeoJSON from the draw control.
        name: For DRAW, the optional user-supplied name.
        asset_id: For ASSET, the Earth Engine asset path.
        asset_type: For ASSET, the Earth Engine asset type.

    Note:
        ``pathname`` is a path on the machine that ran the picker. SHAPE and POINTS
        are not safe in multi-user container apps (see
        ``docs/guides/solara-gee-patterns.md`` "AOI Method Restrictions"), so a
        persisted path is only meaningful for local and Voila deployments.
    """

    method: str
    schema_version: int = AOI_SPEC_SCHEMA_VERSION
    admin_codes: Tuple[str, ...] = ()
    pathname: Optional[str] = None
    column: Optional[str] = None
    value: Optional[Any] = None
    id_column: Optional[str] = None
    lat_column: Optional[str] = None
    lng_column: Optional[str] = None
    geo_json: Optional[Dict[str, Any]] = None
    name: Optional[str] = None
    asset_id: Optional[str] = None
    asset_type: Optional[str] = None

    def __hash__(self) -> int:
        """Hash by content, skipping the unhashable ``geo_json`` dict.

        Hashing a subset of the compared fields is legal: equal specs still hash
        equal, which is all the contract requires.
        """
        return hash((self.method, self.admin_codes, self.pathname, self.asset_id, self.name))

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe payload with only the fields this method uses.

        Returns:
            A dict carrying ``method``, ``schema_version`` and every set field.
        """
        data: Dict[str, Any] = {"method": self.method, "schema_version": self.schema_version}
        for spec_field in fields(self):
            if spec_field.name in ("method", "schema_version"):
                continue
            current = getattr(self, spec_field.name)
            if current is None or current == () or current == "":
                continue
            if isinstance(current, tuple):
                data[spec_field.name] = list(current)
            else:
                # deepcopy: geo_json is a nested dict held by reference, and a caller
                # mutating it afterwards would silently change what this spec equals
                # and what it serializes to.
                data[spec_field.name] = deepcopy(current)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AoiSpec":
        """Rebuild a spec from a persisted payload.

        Args:
            data: A payload previously produced by :meth:`to_dict`.

        Returns:
            The restored spec.

        Raises:
            ValueError: If ``method`` is missing or the payload is from a newer schema.
        """
        version = int(data.get("schema_version", AOI_SPEC_SCHEMA_VERSION))
        if version > AOI_SPEC_SCHEMA_VERSION:
            raise ValueError(
                f"AOI spec schema version {version} is newer than this pysepal "
                f"understands ({AOI_SPEC_SCHEMA_VERSION}). Upgrade pysepal to read it."
            )

        method = data.get("method")
        if not method:
            raise ValueError("An AOI spec payload must carry a method")

        known = {spec_field.name for spec_field in fields(cls)}
        kwargs = {key: deepcopy(value) for key, value in data.items() if key in known}
        kwargs["method"] = method
        kwargs["schema_version"] = version
        if "admin_codes" in kwargs:
            kwargs["admin_codes"] = tuple(str(code) for code in kwargs["admin_codes"])
        return cls(**kwargs)

    def shape_data(self) -> Optional[Dict[str, Any]]:
        """Return the SHAPE picker payload, or None for other methods."""
        if self.method != "SHAPE" or not self.pathname:
            return None
        return {"pathname": self.pathname, "column": self.column or "ALL", "value": self.value}

    def points_data(self) -> Optional[Dict[str, Any]]:
        """Return the POINTS picker payload, or None for other methods."""
        if self.method != "POINTS" or not self.pathname:
            return None
        return {
            "pathname": self.pathname,
            "id_column": self.id_column,
            "lat_column": self.lat_column,
            "lng_column": self.lng_column,
        }

    def asset_data(self) -> Optional[Dict[str, Any]]:
        """Return the ASSET picker payload, or None for other methods."""
        if self.method != "ASSET" or not self.asset_id:
            return None
        return {
            "asset_id": self.asset_id,
            "type": self.asset_type,
            "column": self.column or "ALL",
            "value": self.value,
        }
