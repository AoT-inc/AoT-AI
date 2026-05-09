# coding=utf-8
"""
SSEManager — Thread-safe Server-Sent Events broadcast manager.

Usage:
    from aot.utils.sse_manager import sse_manager
    sse_manager.broadcast("anomaly_alert", {"message": "...", "level": "warning"})
"""
import json
import logging
import queue
import threading

logger = logging.getLogger(__name__)


class SSEManager:
    """Singleton registry that maps client IDs to per-client event queues."""

    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls):
        with cls._singleton_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._clients = {}
                inst._clients_lock = threading.Lock()
                cls._instance = inst
        return cls._instance

    def register(self, client_id: str) -> queue.Queue:
        """Register a new SSE client and return its dedicated queue."""
        q = queue.Queue(maxsize=50)
        with self._clients_lock:
            self._clients[client_id] = q
        logger.debug("[SSE] Client registered: %s (total: %d)", client_id, len(self._clients))
        return q

    def unregister(self, client_id: str) -> None:
        """Remove a client from the registry."""
        with self._clients_lock:
            self._clients.pop(client_id, None)
        logger.debug("[SSE] Client unregistered: %s (total: %d)", client_id, len(self._clients))

    def broadcast(self, event_type: str, payload: dict) -> None:
        """Serialize payload and enqueue to all connected clients."""
        data = json.dumps(payload)
        message = f"event: {event_type}\ndata: {data}\n\n"

        with self._clients_lock:
            clients_snapshot = dict(self._clients)

        dead = []
        for client_id, q in clients_snapshot.items():
            try:
                q.put_nowait(message)
            except queue.Full:
                logger.warning("[SSE] Queue full for client %s, dropping event", client_id)
                dead.append(client_id)

        if dead:
            with self._clients_lock:
                for cid in dead:
                    self._clients.pop(cid, None)


# Module-level singleton instance
sse_manager = SSEManager()
