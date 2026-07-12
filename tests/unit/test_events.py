import pytest

from tradecore.core.events import Event, EventBus


@pytest.mark.asyncio
async def test_pub_sub_success():
    bus = EventBus()
    received_events = []

    async def callback(event: Event):
        received_events.append(event)

    bus.subscribe("test_event", callback)
    event = Event(type="test_event", data={"key": "value"})
    await bus.publish(event)

    assert len(received_events) == 1
    assert received_events[0].type == "test_event"
    assert received_events[0].data["key"] == "value"


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = EventBus()
    call_count = 0

    async def callback(event: Event):
        nonlocal call_count
        call_count += 1

    bus.subscribe("test_event", callback)
    await bus.publish(Event(type="test_event"))
    assert call_count == 1

    bus.unsubscribe("test_event", callback)
    await bus.publish(Event(type="test_event"))
    assert call_count == 1


@pytest.mark.asyncio
async def test_subscriber_exception_isolation():
    bus = EventBus()
    completed = []

    async def throwing_callback(event: Event):
        raise ValueError("Simulated subscriber crash")

    async def safe_callback(event: Event):
        completed.append(event)

    bus.subscribe("crash_test", throwing_callback)
    bus.subscribe("crash_test", safe_callback)

    await bus.publish(Event(type="crash_test"))

    assert len(completed) == 1
    assert completed[0].type == "crash_test"
