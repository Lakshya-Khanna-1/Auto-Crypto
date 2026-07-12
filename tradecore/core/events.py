import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Asynchronous publish/subscribe event bus using asyncio.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, callback: EventHandler) -> None:
        """
        Register an async callback for a specific event type.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: EventHandler) -> None:
        """
        Unsubscribe a callback from an event type.
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
            except ValueError:
                pass

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all registered subscribers concurrently.
        """
        callbacks = self._subscribers.get(event.type, [])
        if not callbacks:
            return

        tasks = [asyncio.create_task(cb(event)) for cb in callbacks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for cb, result in zip(callbacks, results, strict=True):
            if isinstance(result, Exception):
                cb_name = getattr(cb, "__name__", str(cb))
                logger.error(
                    f"Error running subscriber {cb_name} for event {event.type}", exc_info=result
                )


# Global event bus instance
_global_bus = EventBus()


def get_event_bus() -> EventBus:
    return _global_bus
