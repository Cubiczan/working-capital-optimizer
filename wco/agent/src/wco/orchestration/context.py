"""Shared organisational context for the WCO agent mesh.

The ``ContextEngine`` provides a lightweight, thread-safe in-memory store
that agents can read from and write to during orchestration.  It supports
entity-centric lookups with simple lexical relevance scoring — no external
embedding service required.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any

from wco.rust_core import select_context as select_context_rust


class EntryKind(str, Enum):
    """Type of context entry."""

    ENTITY = "entity"
    EVENT = "event"
    TASK = "task"
    RESULT = "result"


@dataclass
class Entity:
    """An organisational entity (customer, vendor, SKU, etc.)."""

    entity_id: str
    entity_type: str  # e.g. "customer", "vendor", "sku"
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """A time-stamped event relevant to working capital."""

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    event_type: str = ""  # e.g. "invoice_issued", "payment_received"
    timestamp: str = ""  # ISO-8601
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    """A unit of work assigned to or produced by an agent."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    status: str = "pending"  # pending | in_progress | completed
    agent_name: str = ""
    result: Any = None


@dataclass
class ContextEntry:
    """A single entry in the context store."""

    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: EntryKind = EntryKind.ENTITY
    source_agent: str = ""
    key: str = ""
    value: Any = None
    text: str = ""  # searchable text representation
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextEngine:
    """Thread-safe, in-memory context store for the agent mesh.

    Provides write / select / snapshot operations so agents can share
    intermediate results without tight coupling.

    Usage::

        ctx = ContextEngine()
        ctx.write("ar_analysis", turn_result, source_agent="AR Agent")
        results = ctx.select("accounts receivable")
        snapshot = ctx.snapshot_for("CashFlow Agent")
    """

    def __init__(self) -> None:
        self._store: list[ContextEntry] = []
        self._lock = threading.RLock()

    # ── Write ────────────────────────────────────────────────────────────

    def write(
        self,
        key: str,
        value: Any,
        *,
        kind: EntryKind = EntryKind.RESULT,
        source_agent: str = "",
        text: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ContextEntry:
        """Insert or update a context entry.

        Args:
            key: Unique key for the entry (update if exists).
            value: Arbitrary payload.
            kind: Entry kind (entity, event, task, result).
            source_agent: Name of the writing agent.
            text: Human-readable text for lexical search.
            metadata: Additional key-value metadata.

        Returns:
            The created / updated ``ContextEntry``.
        """
        entry = ContextEntry(
            key=key,
            value=value,
            kind=kind,
            source_agent=source_agent,
            text=text or str(value)[:2000],
            metadata=metadata or {},
        )

        with self._lock:
            # Upsert by key
            for i, existing in enumerate(self._store):
                if existing.key == key:
                    entry.entry_id = existing.entry_id
                    self._store[i] = entry
                    return entry
            self._store.append(entry)
            return entry

    # ── Select ───────────────────────────────────────────────────────────

    def select(
        self,
        query: str,
        *,
        kind: EntryKind | None = None,
        source_agent: str | None = None,
        top_k: int = 10,
    ) -> list[ContextEntry]:
        """Retrieve context entries matching a query using lexical relevance.

        Args:
            query: Free-text search string.
            kind: Optional filter by entry kind.
            source_agent: Optional filter by producing agent.
            top_k: Maximum number of entries to return.

        Returns:
            Entries sorted by relevance score (descending).
        """
        def _tokenise(text: str) -> set[str]:
            tokens = set(re.findall(r"[a-z0-9_]+", text.lower()))
            return {token for token in tokens if len(token) > 1}

        def _overlap_score(query_terms: set[str], doc_terms: set[str]) -> float:
            if not query_terms:
                return 0.0
            return len(query_terms & doc_terms) / len(query_terms)

        with self._lock:
            candidates = list(self._store)

        # Apply filters
        if kind is not None:
            candidates = [e for e in candidates if e.kind == kind]
        if source_agent is not None:
            candidates = [e for e in candidates if e.source_agent == source_agent]

        payload_entries = [
            {
                "entry_id": entry.entry_id,
                "kind": entry.kind.value,
                "source_agent": entry.source_agent,
                "key": entry.key,
                "text": entry.text,
            }
            for entry in candidates
        ]

        selected_ids = select_context_rust(
            payload_entries,
            query,
            kind=kind.value if kind is not None else None,
            source_agent=source_agent,
            top_k=top_k,
        )
        if selected_ids is not None:
            index = {entry.entry_id: entry for entry in candidates}
            return [index[entry_id] for entry_id in selected_ids if entry_id in index]

        query_terms = _tokenise(query)
        scored: list[tuple[float, int, ContextEntry]] = []
        for i, entry in enumerate(candidates):
            doc_terms = _tokenise(entry.text + " " + entry.key)
            score = _overlap_score(query_terms, doc_terms)
            scored.append((score, i, entry))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [entry for _, _, entry in scored[:top_k]]

    # ── Snapshot ─────────────────────────────────────────────────────────

    def snapshot_for(self, agent_name: str) -> dict[str, Any]:
        """Build a context snapshot suitable for a specific agent.

        Serialises all entries into a plain dict the agent can consume.

        Args:
            agent_name: Name of the target agent.

        Returns:
            Dict with all context entries keyed by their ``key`` field.
        """
        with self._lock:
            entries = list(self._store)

        snapshot: dict[str, Any] = {}
        for entry in entries:
            # Serialise dataclass values to dicts
            val = entry.value
            val = _to_jsonable(val)
            snapshot[entry.key] = {
                "value": val,
                "kind": entry.kind.value,
                "source_agent": entry.source_agent,
                "timestamp": entry.timestamp,
            }
        return snapshot

    # ── Dump ─────────────────────────────────────────────────────────────

    def dump(self) -> list[dict[str, Any]]:
        """Return a full dump of all entries as dicts.

        Useful for debugging and persistence.
        """
        with self._lock:
            entries = list(self._store)
        return [
            {
                "entry_id": e.entry_id,
                "kind": e.kind.value,
                "key": e.key,
                "text": e.text[:200],
                "source_agent": e.source_agent,
                "timestamp": e.timestamp,
            }
            for e in entries
        ]

    # ── Lexical scoring helpers ──────────────────────────────────────────

    @staticmethod
    def _dataclass_to_dict(obj: Any) -> Any:
        """Backwards-compatible JSON serializer for dataclasses and enums."""
        return _to_jsonable(obj)

def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        obj = asdict(obj)
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj
