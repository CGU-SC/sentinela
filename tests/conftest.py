"""Consistent test categories for the Python suite.

Category rules live here so ``pytest -m unit|contract|integration`` has one
transparent source of truth. New test modules under unknown directories must
be added to a registered test area or collection fails with a useful message.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_INTEGRATION_MODULES = {
    "tests/backend/analytics/test_crm_analysis_end_to_end.py",
    "tests/backend/api/test_application_lifecycle.py",
    "tests/backend/services/test_request_logging.py",
    "tests/test_evidencias.py",
    "tests/test_watchlist_recovery.py",
}

_UNIT_MODULES = {
    "tests/backend/api/test_text_search.py",
}
_PRIMARY_CATEGORIES = {"unit", "contract", "integration"}


def _category_for(path: str) -> str:
    if path in _INTEGRATION_MODULES:
        return "integration"
    if path in _UNIT_MODULES:
        return "unit"
    if path.startswith("tests/backend/api/"):
        return "contract"
    if (
        path.startswith("tests/backend/analytics/")
        or path.startswith("tests/backend/cache/")
        or path.startswith("tests/backend/services/")
        or (path.startswith("tests/backend/") and "/" not in path.removeprefix("tests/backend/"))
        or (path.startswith("tests/") and "/" not in path.removeprefix("tests/"))
    ) and path.endswith(".py") and Path(path).name.startswith("test_"):
        return "unit"
    raise pytest.UsageError(
        f"Módulo de teste sem categoria: {path}. Classifique-o em tests/conftest.py."
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply exactly one primary category and the backend layer marker."""
    for item in items:
        absolute_path = Path(item.path).resolve()
        try:
            relative_path = absolute_path.relative_to(_PROJECT_ROOT).as_posix()
        except ValueError as exc:
            raise pytest.UsageError(
                f"Teste fora da árvore do projeto não pode ser categorizado: {absolute_path}"
            ) from exc

        category = _category_for(relative_path)
        declared_categories = {
            marker.name for marker in item.iter_markers()
            if marker.name in _PRIMARY_CATEGORIES
        }
        if declared_categories and declared_categories != {category}:
            raise pytest.UsageError(
                f"Categorias conflitantes em {relative_path}: "
                f"declaradas {sorted(declared_categories)}, esperada {category}."
            )
        if category not in declared_categories:
            item.add_marker(getattr(pytest.mark, category))
        if relative_path.startswith("tests/backend/"):
            if "backend" not in {marker.name for marker in item.iter_markers()}:
                item.add_marker(pytest.mark.backend)
