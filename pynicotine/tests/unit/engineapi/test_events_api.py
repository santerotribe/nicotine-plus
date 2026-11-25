# SPDX-FileCopyrightText: 2026 Schema Apps
# SPDX-License-Identifier: GPL-3.0-or-later

"""The push channel: ordering, filtering, backpressure and coalescing."""

import queue

import pynicotine.engineapi.hub as hub_module
from pynicotine.engineapi.hub import EventHub, Subscriber, type_filter


class FakeTransfer:

    username = "dj"
    virtual_path = "Music\\track.mp3"
    folder_path = "/tmp"
    size = 1000
    current_byte_offset = 500
    status = "Transferring"
    queue_position = 0
    speed = 1024


def _hub() -> EventHub:

    hub = EventHub()
    # Skip event wiring: these tests only exercise the delivery mechanics.
    hub._started = True
    return hub


def test_publish_delivers_in_order_with_sequence_numbers():

    hub = _hub()
    subscriber = hub.subscribe()

    hub.publish("login", username="santero")
    hub.publish("disconnect", manual=True)

    first = subscriber.queue.get_nowait()
    second = subscriber.queue.get_nowait()

    assert [first["type"], second["type"]] == ["login", "disconnect"]
    assert second["seq"] == first["seq"] + 1
    assert first["username"] == "santero"


def test_publish_without_subscribers_is_free():

    hub = _hub()
    hub.publish("login", username="nobody")

    assert hub.subscriber_count == 0


def test_type_filter_includes_and_excludes():

    hub = _hub()
    only_transfers = hub.subscribe(*type_filter("transfers"))
    no_transfers = hub.subscribe(*type_filter("-transfers"))

    hub.publish("transfers", transfers=[])
    hub.publish("browse", username="dj")

    assert only_transfers.queue.get_nowait()["type"] == "transfers"
    assert only_transfers.queue.empty()

    assert no_transfers.queue.get_nowait()["type"] == "browse"
    assert no_transfers.queue.empty()


def test_hello_is_always_delivered_even_when_filtered():

    hub = _hub()
    subscriber = hub.subscribe(*type_filter("transfers"))

    subscriber.offer({"type": "hello"})
    assert subscriber.queue.get_nowait()["type"] == "hello"


def test_full_queue_drops_oldest_and_counts_the_gap():

    subscriber = Subscriber()
    deepest = subscriber.queue.maxsize

    for index in range(deepest + 5):
        subscriber.offer({"type": "transfers", "index": index})

    assert subscriber.queue.qsize() == deepest
    assert subscriber.take_dropped() == 5

    # The newest event survived, the oldest ones were dropped.
    newest = None

    while not subscriber.queue.empty():
        newest = subscriber.queue.get_nowait()

    assert newest["index"] == deepest + 4


def test_unsubscribe_stops_delivery():

    hub = _hub()
    subscriber = hub.subscribe()
    hub.unsubscribe(subscriber)

    hub.publish("login")

    assert subscriber.queue.empty()
    assert hub.subscriber_count == 0


def test_transfer_updates_are_coalesced_per_file():

    hub = _hub()
    subscriber = hub.subscribe()

    # update-download passes (transfer, update_parent); abort-download passes
    # (transfer, status, update_parent). Both must be accepted.
    hub._on_transfer(FakeTransfer())
    hub._on_transfer(FakeTransfer(), "Paused", False)
    hub.flush_transfers()

    payload = subscriber.queue.get_nowait()
    assert payload["type"] == "transfers"
    assert len(payload["transfers"]) == 1
    assert payload["transfers"][0]["filename"] == "track.mp3"
    assert payload["transfers"][0]["percent"] == 50.0
    assert subscriber.queue.empty()


def test_browse_completion_only_fires_for_the_last_message(monkeypatch):

    hub = _hub()
    monkeypatch.setattr(hub_module, "_browse_payload", lambda username: {"folders": 2, "files": 10,
                                                                        "shared_size": 100, "messages": 1})
    scheduled = []

    class FakeEvents:

        @staticmethod
        def schedule(delay, callback, args):
            scheduled.append((callback, args))

    monkeypatch.setattr(hub_module, "events", FakeEvents)

    class Msg:
        username = "dj"

    subscriber = hub.subscribe()

    hub._on_browse_response(Msg())
    hub._on_browse_response(Msg())

    assert len(scheduled) == 2
    assert subscriber.queue.get_nowait()["done"] is False
    assert subscriber.queue.get_nowait()["done"] is False

    # A stale completion from the first message must not be published.
    callback, args = scheduled[0]
    callback(*args)

    assert subscriber.queue.empty()

    callback, args = scheduled[1]
    callback(*args)

    done = subscriber.queue.get_nowait()
    assert done["done"] is True
    assert done["files"] == 10


def test_a_failing_listener_never_escapes_the_guard():
    """events.emit() quits the client on listener errors; the API must not."""

    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    assert hub_module.guard(broken)() is None
    assert hub_module.guard(lambda value: value + 1)(1) == 2


def test_digging_status_becomes_a_crate_event():

    hub = _hub()
    subscriber = hub.subscribe()

    hub._on_digging_status("track-1", status="ready", als_path="/tmp/x.als")

    payload = subscriber.queue.get_nowait()
    assert payload["type"] == "crate"
    assert payload["track_id"] == "track-1"
    assert payload["status"] == "ready"


def test_dropped_counter_resets_after_read():

    subscriber = Subscriber()
    subscriber.queue = queue.Queue(maxsize=1)
    subscriber.offer({"type": "one"})
    subscriber.offer({"type": "two"})

    assert subscriber.take_dropped() == 1
    assert subscriber.take_dropped() == 0
