"""Async SEPAL clients share session identity, never another module's lifetime."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pysepal.solara import session_manager as sm
from pysepal.solara._topology import SessionPlan, SessionSource
from pysepal.solara.errors import SessionScopeClosedError


def test_async_clients_are_scoped_and_closed_on_owner_loop(monkeypatch):
    async def run():
        manager = sm.SessionManager()
        monkeypatch.setattr(
            sm,
            "_current_plan",
            lambda: SessionPlan(SessionSource.PER_CONNECTION, "test"),
        )
        scope = ["alice"]
        monkeypatch.setattr(manager, "get_scope_id", lambda: scope[0])
        created = []

        def make(**kwargs):
            value = SimpleNamespace(aclose=AsyncMock(), **kwargs)
            created.append(value)
            return value

        monkeypatch.setattr(sm, "AsyncSepalClient", make)
        for user in ("alice", "bob"):
            manager._registry.set(
                {
                    "sepal_session_id": user + "-cookie",
                    "active_module_name": "one",
                    "sepal_clients": {
                        name: SimpleNamespace(base_url="https://example.test", verify=True)
                        for name in ("one", "two")
                    },
                },
                user,
            )
        first = manager.get_async_sepal_client("one")
        assert manager.get_async_sepal_client("one") is first
        second = manager.get_async_sepal_client("two")
        assert second is not first
        scope[0] = "bob"
        third = manager.get_async_sepal_client("one")
        assert third is not first
        assert first.session_id == "alice-cookie"
        assert third.session_id == "bob-cookie"
        manager.cleanup_session("alice")
        await asyncio.sleep(0)
        assert first.aclose.await_count == second.aclose.await_count == 1
        assert third.aclose.await_count == 0
        scope[0] = "alice"
        with pytest.raises(SessionScopeClosedError):
            manager.get_async_sepal_client("one")

    asyncio.run(run())


def test_async_accessor_rejects_stale_sync_client(monkeypatch):
    async def run():
        manager = sm.SessionManager()
        monkeypatch.setattr(
            sm,
            "_current_plan",
            lambda: SessionPlan(SessionSource.PER_CONNECTION, "test"),
        )
        monkeypatch.setattr(manager, "get_scope_id", lambda: "alice")
        manager._registry.set(
            {"sepal_clients": {"one": object()}, "active_module_name": "one"}, "alice"
        )
        with pytest.raises(SessionScopeClosedError):
            manager.get_async_sepal_client("one", expected_client=object())

    asyncio.run(run())


def test_short_lived_loops_can_release_and_recreate_clients(monkeypatch):
    manager = sm.SessionManager()
    monkeypatch.setattr(
        sm, "_current_plan", lambda: SessionPlan(SessionSource.PER_CONNECTION, "test")
    )
    monkeypatch.setattr(manager, "get_scope_id", lambda: "alice")
    made = []

    def make(**kwargs):
        value = SimpleNamespace(aclose=AsyncMock())
        made.append(value)
        return value

    monkeypatch.setattr(sm, "AsyncSepalClient", make)
    manager._registry.set(
        {
            "sepal_session_id": "cookie",
            "active_module_name": "one",
            "sepal_clients": {"one": SimpleNamespace(base_url="https://example.test", verify=True)},
        },
        "alice",
    )

    async def run():
        manager.get_async_sepal_client()
        await manager.aclose_async_sepal_clients()

    asyncio.run(run())
    asyncio.run(run())
    assert len(made) == 2
    assert all(client.aclose.await_count == 1 for client in made)


def test_cleanup_on_stopped_owner_loop_closes_client():
    manager = sm.SessionManager()
    loop = asyncio.new_event_loop()
    client = SimpleNamespace(aclose=AsyncMock())
    try:
        manager._registry.set({"async_sepal_clients": {"one": (client, loop)}}, "alice")
        manager.cleanup_session("alice")
        client.aclose.assert_awaited_once()
    finally:
        loop.close()


def test_cleanup_groups_modules_on_one_stopped_loop():
    manager = sm.SessionManager()
    owner = asyncio.new_event_loop()
    clients = [SimpleNamespace(aclose=AsyncMock()) for _ in range(2)]

    async def run():
        manager._registry.set(
            {
                "async_sepal_clients": {
                    str(index): (client, owner) for index, client in enumerate(clients)
                }
            },
            "alice",
        )
        manager.cleanup_session("alice")
        pending = list(manager._async_cleanup)
        await asyncio.gather(*(asyncio.wrap_future(future) for future in pending))
        assert all(client.aclose.await_count == 1 for client in clients)

    try:
        asyncio.run(run())
    finally:
        owner.close()
