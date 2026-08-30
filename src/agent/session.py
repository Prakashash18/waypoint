"""Conversation sessions — what the agent already knows and already found.

Without this, every request started cold: "compare the top two" had no idea
what the previous turn had found and asked for the destination again.

A session holds three things:
  messages     the agent's own conversation, so a follow-up continues it
  artifacts    what the last run actually found, so a follow-up need not
               re-search to talk about it
  preferences  durable things the traveller has told us about themselves

`user_id` is nullable throughout. Today a session belongs to a browser; when
accounts arrive it belongs to a person, and nothing else has to change.
`SessionStore` is deliberately a narrow interface so a database can replace the
in-memory implementation without touching callers.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# An abandoned tab should not pin memory forever.
SESSION_TTL = 6 * 3600
MAX_SESSIONS = 500

# OpenAI rejects a tool_calls message whose tool results are missing, so
# trimming has to drop whole turns rather than individual messages.
MAX_TURNS_KEPT = 6


@dataclass
class Session:
    """One traveller's ongoing conversation."""
    id: str
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    messages: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)
    locale: Optional[Dict[str, Any]] = None

    # Set when the traveller interrupts; the agent loop checks it between steps.
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    running: bool = False

    # ── steering ─────────────────────────────────────────────────

    def cancel(self) -> None:
        self._cancel.set()

    def clear_cancel(self) -> None:
        self._cancel.clear()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # ── conversation ─────────────────────────────────────────────

    def trim(self) -> None:
        """Keep the conversation bounded without orphaning tool results.

        Turns are cut from the front in whole units — a user message and
        everything the agent did in response — so no tool_calls message is ever
        left without the tool messages that answer it.
        """
        starts = [i for i, m in enumerate(self.messages) if m.get('role') == 'user']
        if len(starts) <= MAX_TURNS_KEPT:
            return
        cut = starts[len(starts) - MAX_TURNS_KEPT]
        self.messages = self.messages[cut:]

    def remember(self, **prefs: Any) -> None:
        """Record durable preferences, ignoring empty values."""
        for key, value in prefs.items():
            if value not in (None, '', [], {}):
                self.preferences[key] = value
        self.updated_at = time.time()

    def summary(self) -> Dict[str, Any]:
        """What the UI needs to know about this session."""
        hotels = (self.artifacts.get('hotels') or [])
        return {
            'session_id': self.id,
            'user_id': self.user_id,
            'turns': sum(1 for m in self.messages if m.get('role') == 'user'),
            'preferences': self.preferences,
            'knows_about': {
                'hotels': len(hotels),
                'flights': len(self.artifacts.get('flights') or []),
                'windows': len(self.artifacts.get('windows') or []),
            },
            'running': self.running,
            'updated_at': self.updated_at,
        }


class SessionStore:
    """In-memory sessions. Swap for a database-backed store when accounts land."""

    def __init__(self, ttl: int = SESSION_TTL, limit: int = MAX_SESSIONS):
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._limit = limit

    def get_or_create(self, session_id: Optional[str] = None,
                      user_id: Optional[str] = None) -> Session:
        with self._lock:
            self._evict()
            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                session.updated_at = time.time()
                # A signed-in traveller claims the session they were already using.
                if user_id and not session.user_id:
                    session.user_id = user_id
                return session

            new_id = session_id or secrets.token_urlsafe(16)
            session = Session(id=new_id, user_id=user_id)
            self._sessions[new_id] = session
            return session

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _evict(self) -> None:
        """Caller holds the lock."""
        now = time.time()
        stale = [k for k, s in self._sessions.items() if now - s.updated_at > self._ttl]
        for key in stale:
            self._sessions.pop(key, None)

        if len(self._sessions) > self._limit:
            oldest = sorted(self._sessions.items(), key=lambda kv: kv[1].updated_at)
            for key, _ in oldest[: len(self._sessions) - self._limit]:
                self._sessions.pop(key, None)


sessions = SessionStore()
