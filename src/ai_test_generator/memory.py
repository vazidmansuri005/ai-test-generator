"""Failure Memory — persistent learning from past diagnoses.

The agent gets smarter over time. When you correct a diagnosis,
the pattern is stored. On future runs, similar failures are matched
against stored corrections and the context is passed to Claude
for better classification.

No embeddings, no ML training. Just a growing knowledge base of
error-pattern → correct-classification mappings that compound over time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    Classification,
    Correction,
    Diagnosis,
    MemoryMatch,
)


DEFAULT_MEMORY_DIR = Path.home() / ".ai-test-gen" / "memory"


class FailureMemory:
    """Persistent memory of past diagnosis corrections.

    Stores corrections in a local JSON file. On future diagnoses,
    matches error patterns against stored corrections and returns
    relevant context to improve Claude's classification.

    Example:
        memory = FailureMemory()

        # Record a correction
        memory.record_correction(
            test_name="test_checkout::test_payment",
            original=Classification.INFRA_ISSUE,
            corrected=Classification.TEST_ISSUE,
            reason="Stale CSS selector, not a network issue",
            error_pattern="TimeoutError: wait_for_selector",
        )

        # On future diagnosis, find matching patterns
        matches = memory.find_matches("TimeoutError: wait_for_selector('#pay-btn')")
        # Returns the correction above as context
    """

    def __init__(self, memory_dir: str | Path | None = None):
        self.memory_dir = Path(memory_dir) if memory_dir else DEFAULT_MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.corrections_file = self.memory_dir / "corrections.json"
        self.stats_file = self.memory_dir / "stats.json"
        self._corrections: list[Correction] = self._load()

    def _load(self) -> list[Correction]:
        if self.corrections_file.exists():
            data = json.loads(self.corrections_file.read_text())
            return [Correction.model_validate(c) for c in data]
        return []

    def _save(self):
        data = [c.model_dump() for c in self._corrections]
        self.corrections_file.write_text(json.dumps(data, indent=2))

    def record_correction(
        self,
        test_name: str,
        original: Classification,
        corrected: Classification,
        reason: str,
        error_pattern: str,
    ) -> Correction:
        """Record a diagnosis correction for future learning.

        Args:
            test_name: The test that was misdiagnosed.
            original: What the agent classified it as.
            corrected: What it actually was.
            reason: Why the correction was made (human explanation).
            error_pattern: Key error text to match against future failures.

        Returns:
            The stored Correction.
        """
        correction = Correction(
            test_name=test_name,
            original_classification=original,
            corrected_classification=corrected,
            reason=reason,
            error_pattern=error_pattern,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._corrections.append(correction)
        self._save()
        self._update_stats(original, corrected)
        return correction

    def record_from_diagnosis(
        self,
        diagnosis: Diagnosis,
        corrected: Classification,
        reason: str,
    ) -> Correction:
        """Convenience: record a correction directly from a Diagnosis object."""
        # Extract the key error pattern from the evidence summary
        error_pattern = diagnosis.probable_cause[:200]
        return self.record_correction(
            test_name=diagnosis.test_name,
            original=diagnosis.classification,
            corrected=corrected,
            reason=reason,
            error_pattern=error_pattern,
        )

    def find_matches(self, error_text: str, limit: int = 5) -> list[MemoryMatch]:
        """Find past corrections that match the current error.

        Uses keyword overlap scoring — no embeddings needed.
        Effective because error messages have distinctive tokens
        (exception names, function names, error codes).

        Args:
            error_text: The error message or traceback from the current failure.
            limit: Maximum matches to return.

        Returns:
            List of MemoryMatch objects, sorted by relevance.
        """
        if not self._corrections:
            return []

        error_lower = error_text.lower()
        error_tokens = set(self._tokenize(error_lower))

        scored: list[tuple[float, Correction]] = []
        for correction in self._corrections:
            pattern_tokens = set(self._tokenize(correction.error_pattern.lower()))
            if not pattern_tokens:
                continue

            # Jaccard-like similarity on tokens
            intersection = error_tokens & pattern_tokens
            union = error_tokens | pattern_tokens
            score = len(intersection) / len(union) if union else 0

            # Boost score for exact substring match
            if correction.error_pattern.lower() in error_lower:
                score = max(score, 0.8)

            if score > 0.15:  # Minimum threshold
                scored.append((score, correction))

        scored.sort(key=lambda x: x[0], reverse=True)

        matches = []
        for score, correction in scored[:limit]:
            similarity = (
                f"Matched pattern from {correction.test_name}: "
                f"was {correction.original_classification.value}, "
                f"actually {correction.corrected_classification.value}. "
                f"Reason: {correction.reason}"
            )
            matches.append(MemoryMatch(
                correction=correction,
                similarity=similarity,
            ))

        return matches

    def get_context_for_diagnosis(self, failures_text: str) -> str:
        """Generate a context block to inject into the diagnosis prompt.

        Args:
            failures_text: Combined error text from all failures.

        Returns:
            Context string to append to the diagnosis prompt, or empty string.
        """
        matches = self.find_matches(failures_text, limit=10)
        if not matches:
            return ""

        lines = [
            "\n\nIMPORTANT — Past corrections from this codebase's failure memory:",
            "The following patterns have been CORRECTED by a human in past runs.",
            "Use these to adjust your classification — the original AI diagnosis was WRONG:",
            "",
        ]
        for i, m in enumerate(matches, 1):
            c = m.correction
            lines.append(
                f"{i}. Pattern: \"{c.error_pattern[:100]}\"\n"
                f"   Was classified as: {c.original_classification.value}\n"
                f"   Actually was: {c.corrected_classification.value}\n"
                f"   Reason: {c.reason}"
            )
            lines.append("")

        lines.append(
            "If you see failures matching these patterns, "
            "weight the CORRECTED classification more heavily."
        )
        return "\n".join(lines)

    @property
    def correction_count(self) -> int:
        return len(self._corrections)

    @property
    def corrections(self) -> list[Correction]:
        return list(self._corrections)

    def get_stats(self) -> dict:
        """Return learning statistics."""
        if self.stats_file.exists():
            return json.loads(self.stats_file.read_text())
        return {"total_corrections": 0, "pattern_counts": {}}

    def _update_stats(self, original: Classification, corrected: Classification):
        stats = self.get_stats()
        stats["total_corrections"] = stats.get("total_corrections", 0) + 1
        key = f"{original.value}->{corrected.value}"
        pattern_counts = stats.get("pattern_counts", {})
        pattern_counts[key] = pattern_counts.get(key, 0) + 1
        stats["pattern_counts"] = pattern_counts
        self.stats_file.write_text(json.dumps(stats, indent=2))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple tokenizer: split on non-alphanumeric, filter short tokens."""
        import re
        tokens = re.split(r'[^a-zA-Z0-9_]+', text)
        return [t for t in tokens if len(t) > 2]
