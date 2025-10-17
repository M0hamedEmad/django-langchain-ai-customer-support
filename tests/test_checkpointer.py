"""Checkpointer: per-company thread isolation on a scratch file."""

import pytest

from apps.ai import graph as G


@pytest.fixture
def scratch_checkpointer(tmp_path, settings, monkeypatch):
    settings.LANGGRAPH_CHECKPOINT_DB = str(tmp_path / "cp.sqlite3")
    monkeypatch.setattr(G, "_checkpointer", None)
    yield G.get_checkpointer()
    monkeypatch.setattr(G, "_checkpointer", None)


def test_thread_ids_isolate_companies(scratch_checkpointer):
    a = {
        "configurable": {"thread_id": G.thread_id_for(type("C", (), {"id": 1})(), "s")}
    }
    b = {
        "configurable": {"thread_id": G.thread_id_for(type("C", (), {"id": 2})(), "s")}
    }
    assert a != b
    assert scratch_checkpointer.get_tuple(a) is None
    assert scratch_checkpointer.get_tuple(b) is None


def test_singleton_per_process(scratch_checkpointer):
    assert G.get_checkpointer() is scratch_checkpointer
