from starlette.routing import Route

from backend.app.main import app


def _paths() -> set[str]:
    return {r.path for r in app.routes if isinstance(r, Route)}


def test_health_route_present() -> None:
    assert "/health" in _paths()


def test_docs_routes_present() -> None:
    paths = _paths()
    assert "/docs" in paths
    assert "/docs/health" in paths


def test_search_route_present() -> None:
    assert "/search" in _paths()


def test_ask_route_present() -> None:
    assert "/ask" in _paths()
