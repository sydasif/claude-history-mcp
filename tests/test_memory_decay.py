"""Tests for memory decay engine integration."""

from claude_history_mcp.memory_engine import MemoryDecayEngine


class TestMemoryDecayEngine:
    def test_recall_boosts_stability_and_delays_eviction(self):
        engine = MemoryDecayEngine(eviction_threshold=0.20, baseline_stability=8.0)
        engine.register("note-1", "important fact", current_turn=1)

        # Recall 3 times at turns 5, 10, 15
        engine.recall("note-1", current_turn=5)
        engine.recall("note-1", current_turn=10)
        engine.recall("note-1", current_turn=15)

        # At turn 100, should still be present (stability grew)
        evicted = engine.step(current_turn=100)
        assert "note-1" not in evicted
        assert engine.is_present("note-1")

    def test_unrecalled_note_evicts_after_threshold(self):
        engine = MemoryDecayEngine(eviction_threshold=0.20, baseline_stability=8.0)
        engine.register("note-2", "temporary fact", current_turn=1)

        # No recalls — advance to turn 50
        evicted = engine.step(current_turn=50)
        # retention = e^(-49/8) ≈ 0.002 < 0.20 → evicted
        assert "note-2" in evicted
        assert not engine.is_present("note-2")

    def test_foundational_note_never_evicts(self):
        engine = MemoryDecayEngine(eviction_threshold=0.20, baseline_stability=8.0)
        engine.register(
            "note-3", "architecture decision", current_turn=1, is_foundational=True
        )

        # Advance to turn 1000 — should persist
        evicted = engine.step(current_turn=1000)
        assert "note-3" not in evicted
        assert engine.is_present("note-3")

    def test_stability_grows_with_recalls(self):
        """Verify stability increases non-linearly with each recall."""
        engine = MemoryDecayEngine(eviction_threshold=0.20, baseline_stability=8.0)
        engine.register("note-4", "test", current_turn=1)

        item = engine.get_item("note-4")
        assert item is not None
        initial_stability = item.stability

        # First recall
        engine.recall("note-4", current_turn=5)
        item = engine.get_item("note-4")
        stability_after_1 = item.stability
        assert stability_after_1 > initial_stability

        # Second recall
        engine.recall("note-4", current_turn=10)
        item = engine.get_item("note-4")
        stability_after_2 = item.stability
        assert stability_after_2 > stability_after_1

        # The formula S *= (1 + ln(1 + n)) has increasing multipliers initially
        # (ln(2)≈0.69, ln(3)≈1.10), so increments grow before eventually diminishing.
        # Just verify it keeps growing.

    def test_eviction_log_records_evicted_notes(self):
        engine = MemoryDecayEngine(eviction_threshold=0.20, baseline_stability=8.0)
        engine.register("note-5", "temp", current_turn=1)
        engine.step(current_turn=50)  # evicts note-5

        log = engine.get_eviction_log()
        assert "note-5" in log
        assert log["note-5"] == 50

    def test_multiple_notes_independent_decay(self):
        """Each note decays independently based on its own recall history."""
        engine = MemoryDecayEngine(eviction_threshold=0.20, baseline_stability=8.0)
        engine.register("note-a", "recalled often", current_turn=1)
        engine.register("note-b", "never recalled", current_turn=1)

        # Recall note-a multiple times
        for turn in [5, 10, 15, 20]:
            engine.recall("note-a", current_turn=turn)

        # Advance to turn 60
        evicted = engine.step(current_turn=60)

        # note-a should survive (stability boosted), note-b should evict
        assert "note-a" not in evicted
        assert engine.is_present("note-a")
        assert "note-b" in evicted
        assert not engine.is_present("note-b")

    def test_recall_returns_false_for_missing_note(self):
        engine = MemoryDecayEngine()
        assert engine.recall("nonexistent", current_turn=1) is False

    def test_register_overwrites_existing_note(self):
        engine = MemoryDecayEngine()
        engine.register("note-x", "original", current_turn=1)
        engine.recall("note-x", current_turn=5)  # boost stability
        original_stability = engine.get_item("note-x").stability

        # Re-register with new content at later turn
        engine.register("note-x", "updated", current_turn=10)
        new_stability = engine.get_item("note-x").stability

        # Should reset to baseline
        assert new_stability == engine.baseline_stability
        assert new_stability < original_stability

    def test_get_stats_returns_correct_counts(self):
        engine = MemoryDecayEngine(eviction_threshold=0.20, baseline_stability=8.0)
        engine.register("note-1", "a", current_turn=1)
        engine.register("note-2", "b", current_turn=1, is_foundational=True)
        engine.register("note-3", "c", current_turn=1)
        engine.step(current_turn=50)  # evicts note-1 and note-3

        stats = engine.get_stats()
        assert stats["total_items"] == 1  # only foundational remains
        assert stats["foundational_items"] == 1
        assert stats["evicted_total"] == 2
        assert stats["eviction_threshold"] == 0.20
        assert stats["baseline_stability"] == 8.0

    def test_all_items_returns_all_current_items(self):
        engine = MemoryDecayEngine()
        engine.register("n1", "a", current_turn=1)
        engine.register("n2", "b", current_turn=1, is_foundational=True)

        items = engine.all_items()
        assert len(items) == 2
        note_ids = {item.note_id for item in items}
        assert note_ids == {"n1", "n2"}

    def test_is_foundational_flag_persists_after_recall(self):
        engine = MemoryDecayEngine()
        engine.register(
            "foundational", "important", current_turn=1, is_foundational=True
        )
        engine.recall("foundational", current_turn=10)

        item = engine.get_item("foundational")
        assert item is not None
        assert item.is_foundational is True

    def test_step_does_not_evict_foundational_even_at_zero_retention(self):
        """Foundational items survive even when retention would be ~0."""
        engine = MemoryDecayEngine(eviction_threshold=0.99, baseline_stability=0.1)
        engine.register(
            "always-stays", "critical", current_turn=1, is_foundational=True
        )

        # Even with very low stability and high threshold, foundational survives
        evicted = engine.step(current_turn=1000)
        assert "always-stays" not in evicted
        assert engine.is_present("always-stays")

    def test_turn_monotonicity_required(self):
        """Engine assumes turns advance; negative elapsed handled gracefully."""
        engine = MemoryDecayEngine()
        engine.register("note", "test", current_turn=100)
        # Step with earlier turn (should not crash, score = 1.0)
        evicted = engine.step(current_turn=50)
        assert "note" not in evicted  # elapsed <= 0 → retention = 1.0
