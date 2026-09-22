#!/usr/bin/env python3
"""Discover the live pysepal Solara component surface.

This script is intentionally lightweight so a skill can run it before
scaffolding and avoid hallucinating components that do not exist.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class FunctionInfo:
    name: str
    lineno: int
    is_async: bool


@dataclass
class ModuleInfo:
    module: str
    path: str
    exports: list[str]
    solara_components: list[FunctionInfo]
    helpers: list[FunctionInfo]
    classes: list[str]


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _decorator_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _read_exports(module: ast.Module) -> list[str]:
    exports: list[str] = []
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for item in node.value.elts:
                        if isinstance(item, ast.Constant) and isinstance(item.value, str):
                            exports.append(item.value)
    return exports


def _iter_python_files(components_dir: Path, include_legacy: bool) -> Iterable[Path]:
    for path in sorted(components_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if not include_legacy and "legacy" in path.parts:
            continue
        yield path


def inspect_module(path: Path, repo_root: Path) -> ModuleInfo:
    """Parse a Python module and return its public surface as a ModuleInfo."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    exports = _read_exports(tree)
    solara_components: list[FunctionInfo] = []
    helpers: list[FunctionInfo] = []
    classes: list[str] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            decorators = {_decorator_name(item) for item in node.decorator_list}
            info = FunctionInfo(
                name=node.name,
                lineno=node.lineno,
                is_async=isinstance(node, ast.AsyncFunctionDef),
            )
            if {"solara.component", "component"} & decorators:
                solara_components.append(info)
            else:
                helpers.append(info)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            classes.append(node.name)

    module = path.relative_to(repo_root).with_suffix("").as_posix().replace("/", ".")
    return ModuleInfo(
        module=module,
        path=str(path.relative_to(repo_root)),
        exports=exports,
        solara_components=solara_components,
        helpers=helpers,
        classes=classes,
    )


def find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` until a directory containing the pysepal package is found."""
    current = start.resolve()
    candidates = [current, *current.parents]
    for candidate in candidates:
        if (candidate / "pysepal" / "solara" / "components").exists():
            return candidate
    raise FileNotFoundError(
        f"Could not locate a pysepal repo root from {start}. Expected pysepal/solara/components/."
    )


def installed_package_root() -> Path:
    """Return the directory that contains the ``pysepal`` package importable right now.

    For an editable install this is the checkout; otherwise it is ``site-packages``.
    Either way it satisfies :func:`find_repo_root`.
    """
    spec = importlib.util.find_spec("pysepal")
    if spec is None or spec.origin is None:
        raise ModuleNotFoundError(
            "pysepal is not installed in this environment; pass --repo-root <checkout>."
        )
    return find_repo_root(Path(spec.origin).parents[1])


def render_markdown(modules: list[ModuleInfo], repo_root: Path) -> str:
    """Render the discovered modules as a Markdown summary."""
    lines = [
        "# Pysepal Solara Surface",
        "",
        f"Repo root: `{repo_root}`",
        "",
    ]
    for module in modules:
        lines.append(f"## `{module.module}`")
        lines.append("")
        lines.append(f"- Path: `{module.path}`")
        if module.exports:
            lines.append(f"- __all__: {', '.join(f'`{name}`' for name in module.exports)}")
        if module.solara_components:
            joined = ", ".join(
                f"`{item.name}`{' async' if item.is_async else ''}"
                for item in module.solara_components
            )
            lines.append(f"- Solara components: {joined}")
        if module.helpers:
            joined = ", ".join(
                f"`{item.name}`{' async' if item.is_async else ''}" for item in module.helpers
            )
            lines.append(f"- Helpers: {joined}")
        if module.classes:
            lines.append(f"- Classes: {', '.join(f'`{name}`' for name in module.classes)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """CLI entry point for the discovery script."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        help="Path inside a pysepal checkout. Default: the pysepal installed in this environment.",
    )
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--include-legacy", action="store_true")
    args = parser.parse_args()

    repo_root = find_repo_root(Path(args.repo_root)) if args.repo_root else installed_package_root()
    components_dir = repo_root / "pysepal" / "solara" / "components"
    modules = [
        inspect_module(path, repo_root)
        for path in _iter_python_files(components_dir, include_legacy=args.include_legacy)
    ]

    if args.format == "json":
        print(json.dumps([asdict(module) for module in modules], indent=2))
    else:
        print(render_markdown(modules, repo_root))


if __name__ == "__main__":
    main()
