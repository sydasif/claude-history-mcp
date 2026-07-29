"""Memory decay engine for claude-history-mcp.

Vendored and adapted from Emmimal/memory-decay-engine (MIT, zero dependencies).
Implements Ebbinghaus forgetting curve with spaced-repetition reinforcement.

Retention at elapsed turns t with stability S:
    R = e^(-t / S)

Each recall reinforces stability (diminishing returns):
    S_new = S_old * (1 + ln(1 + recall_count))

Eviction when R < eviction_threshold (default 0.20).
Foundational items (is_foundational=True) never evict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class DecayedMemoryItem:
    """Internal engine item representing a memory note."""

    note_id: str
    content: str
    created_turn: int
    last_touched_turn: int
    is_foundational: bool
    stability: float = 8.0
    recall_count: int = 1


class MemoryDecayEngine:
    """Ebbinghaus forgetting-curve engine with usage-based reinforcement.

    This engine tracks memory notes across "turns" (monotonically advancing
    time units, e.g., days since epoch). Notes that are recalled get their
    stability boosted, flattening their decay curve. Notes that aren't
    recalled eventually decay below the threshold and are evicted.

    Foundational notes (architecture decisions, API keys, etc.) never decay.
    """

    def __init__(
        self,
        eviction_threshold: float = 0.20,
        baseline_stability: float = 8.0,
    ) -> None:
        """Initialize the decay engine.

        Args:
            eviction_threshold: Retention score below which items are evicted.
                Must be in (0, 1). Default 0.20.
            baseline_stability: Initial stability for new items. Higher = slower
                decay. Must be positive. Default 8.0.
        """
        if not (0.0 < eviction_threshold < 1.0):
            raise ValueError("eviction_threshold must be in (0, 1)")
        if baseline_stability <= 0:
            raise ValueError("baseline_stability must be positive")

        self.eviction_threshold = eviction_threshold
        self.baseline_stability = baseline_stability
        self._store: Dict[str, DecayedMemoryItem] = {}
        self._eviction_log: Dict[str, int] = {}  # note_id -> turn evicted

    def register(
        self,
        note_id: str,
        content: str,
        current_turn: int,
        is_foundational: bool = False,
    ) -> None:
        """Add or refresh a memory note at the current turn.

        Args:
            note_id: Unique identifier for the note.
            content: Note content (for reference).
            current_turn: Current monotonically increasing turn number.
            is_foundational: If True, note never decays or evicts.
        """
        self._store[note_id] = DecayedMemoryItem(
            note_id=note_id,
            content=content,
            created_turn=current_turn,
            last_touched_turn=current_turn,
            is_foundational=is_foundational,
            stability=self.baseline_stability,
            recall_count=1,
        )

    def recall(self, note_id: str, current_turn: int) -> bool:
        """Record a recall event for a note, boosting its stability.

        The reinforcement follows spaced-repetition research:
            S_new = S_old * (1 + ln(1 + recall_count))

        Args:
            note_id: Note to recall.
            current_turn: Current turn number.

        Returns:
            True if note was found and recalled, False if not found.
        """
        item = self._store.get(note_id)
        if item is None:
            return False

        item.recall_count += 1
        # Non-linear reinforcement: diminishing returns matching SM-2/Anki
        item.stability *= 1.0 + math.log(1.0 + item.recall_count)
        item.last_touched_turn = current_turn
        return True

    def _retention_score(self, item: DecayedMemoryItem, current_turn: int) -> float:
        """Calculate current retention score for an item.

        R = e^(-elapsed / stability)

        Args:
            item: The memory item.
            current_turn: Current turn number.

        Returns:
            Retention score in [0, 1].
        """
        elapsed = current_turn - item.last_touched_turn
        if elapsed <= 0:
            return 1.0
        return math.exp(-elapsed / item.stability)

    def step(self, current_turn: int) -> List[str]:
        """Evaluate all items at current turn, evict those below threshold.

        Args:
            current_turn: Current monotonically increasing turn number.

        Returns:
            List of note_ids evicted this step.
        """
        evicted: List[str] = []
        for note_id, item in list(self._store.items()):
            if item.is_foundational:
                continue  # Foundational items never evict

            score = self._retention_score(item, current_turn)
            if score < self.eviction_threshold:
                evicted.append(note_id)
                self._eviction_log[note_id] = current_turn
                del self._store[note_id]
        return evicted

    def is_present(self, note_id: str) -> bool:
        """Check if a note is currently in memory (not evicted)."""
        return note_id in self._store

    def working_set_size(self) -> int:
        """Number of notes currently retained."""
        return len(self._store)

    def get_item(self, note_id: str) -> Optional[DecayedMemoryItem]:
        """Get item metadata for debugging/inspection."""
        return self._store.get(note_id)

    def get_stats(self) -> dict[str, int | float]:
        """Return engine statistics."""
        foundational = sum(1 for i in self._store.values() if i.is_foundational)
        return {
            "total_items": len(self._store),
            "foundational_items": foundational,
            "evicted_total": len(self._eviction_log),
            "eviction_threshold": self.eviction_threshold,
            "baseline_stability": self.baseline_stability,
        }

    def get_eviction_log(self) -> Dict[str, int]:
        """Return copy of eviction log: note_id -> turn evicted."""
        return dict(self._eviction_log)

    def all_items(self) -> List[DecayedMemoryItem]:
        """Return list of all current items for inspection."""
        return list(self._store.values())
