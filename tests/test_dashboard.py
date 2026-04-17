"""Tests for dashboard module — SharedState, EventBus, settings mutation."""

import threading

import pytest

from claude_auto_continue.config import Settings
from claude_auto_continue.dashboard import EventBus, SharedState


class TestEventBus:
    def test_publish_reaches_subscriber(self):
        bus = EventBus()
        q = bus.subscribe()
        bus.publish({"type": "test", "msg": "hello"})
        event = q.get(timeout=1)
        assert event["type"] == "test"
        assert event["msg"] == "hello"
        assert "ts" in event

    def test_unsubscribe_stops_delivery(self):
        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.publish({"type": "test"})
        assert q.empty()

    def test_backlog_replayed_to_new_subscriber(self):
        bus = EventBus(backlog=10)
        for i in range(5):
            bus.publish({"type": "test", "i": i})
        q = bus.subscribe()
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        assert len(events) == 5
        assert events[0]["i"] == 0
        assert events[4]["i"] == 4

    def test_backlog_limited(self):
        bus = EventBus(backlog=3)
        for i in range(10):
            bus.publish({"type": "test", "i": i})
        q = bus.subscribe()
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        assert len(events) == 3
        assert events[0]["i"] == 7

    def test_full_queue_drops_subscriber(self):
        bus = EventBus()
        q = bus.subscribe()
        for i in range(600):
            bus.publish({"type": "flood", "i": i})
        bus.publish({"type": "after_flood"})
        assert q.qsize() <= 500

    def test_multiple_subscribers(self):
        bus = EventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        bus.publish({"type": "broadcast"})
        assert q1.get(timeout=1)["type"] == "broadcast"
        assert q2.get(timeout=1)["type"] == "broadcast"

    def test_double_unsubscribe_safe(self):
        bus = EventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        bus.unsubscribe(q)


class TestSharedState:
    def test_initial_status(self):
        state = SharedState(settings=Settings())
        snap = state.status_snapshot()
        assert snap["state"] == "Starting…"
        assert snap["total_continues"] == 0
        assert "uptime" in snap

    def test_set_status(self):
        state = SharedState(settings=Settings())
        state.set_status(state="Watching", total_continues=5)
        snap = state.status_snapshot()
        assert snap["state"] == "Watching"
        assert snap["total_continues"] == 5

    def test_settings_snapshot(self):
        state = SharedState(settings=Settings(interval=3.0, silent=True))
        snap = state.settings_snapshot()
        assert snap["interval"] == 3.0
        assert snap["silent"] is True

    def test_update_settings_valid(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"interval": 5.0})
        assert applied == {"interval": 5.0}
        assert state.settings.interval == 5.0

    def test_update_settings_invalid_rejected(self):
        state = SharedState(settings=Settings())
        with pytest.raises(ValueError):
            state.update_settings({"interval": 0.01})
        assert state.settings.interval == 1.5

    def test_update_settings_unknown_key_ignored(self):
        state = SharedState(settings=Settings())
        applied = state.update_settings({"bogus_key": 999})
        assert applied == {}

    def test_update_settings_callback(self):
        called = {}

        def on_change(s):
            called["settings"] = s

        state = SharedState(settings=Settings(), on_settings_change=on_change)
        state.update_settings({"silent": True})
        assert "settings" in called
        assert called["settings"].silent is True

    def test_terminal_patterns_list_to_tuple(self):
        state = SharedState(settings=Settings())
        state.update_settings({"terminal_patterns": ["a", "b"]})
        assert state.settings.terminal_patterns == ("a", "b")

    def test_full_snapshot_structure(self):
        state = SharedState(settings=Settings())
        snap = state.full_snapshot()
        assert "status" in snap
        assert "settings" in snap
        assert "uptime" in snap["status"]

    def test_publish_log(self):
        state = SharedState(settings=Settings())
        q = state.bus.subscribe()
        state.publish_log("info", "test message")
        event = q.get(timeout=1)
        assert event["type"] == "log"
        assert event["level"] == "info"
        assert event["message"] == "test message"

    def test_thread_safety(self):
        state = SharedState(settings=Settings())
        errors = []

        def reader():
            for _ in range(100):
                try:
                    state.status_snapshot()
                    state.settings_snapshot()
                except Exception as e:
                    errors.append(e)

        def writer():
            for i in range(100):
                try:
                    state.set_status(total_continues=i)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(3)]
        threads += [threading.Thread(target=writer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert len(errors) == 0
