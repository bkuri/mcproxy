"""Fuzzy matching utilities for string similarity and suggestions."""

from difflib import SequenceMatcher
from typing import List, Optional, Tuple

DEFAULT_THRESHOLD: float = 0.6
MAX_SUGGESTIONS: int = 5


def fuzzy_score(query: str, target: str, threshold: float = DEFAULT_THRESHOLD) -> float:
    """Calculate fuzzy match score between query and target.

    Uses word-level matching with substring detection for better results
    with multi-word strings.

    Args:
        query: Query string (will be lowercased)
        target: Target string to match against (will be lowercased)
        threshold: Minimum similarity threshold for word matching

    Returns:
        Similarity score (0.0 to 1.0)
    """
    query_lower = query.lower()
    target_lower = target.lower()

    if query_lower in target_lower:
        return 1.0
    if target_lower in query_lower:
        return 0.9

    query_words = query_lower.split()
    target_words = target_lower.split()

    if not query_words or not target_words:
        return SequenceMatcher(None, query_lower, target_lower).ratio()

    word_matches = 0
    for qw in query_words:
        for tw in target_words:
            if qw in tw or SequenceMatcher(None, qw, tw).ratio() >= threshold:
                word_matches += 1
                break

    return word_matches / len(query_words)


def find_best_matches(
    query: str,
    candidates: List[str],
    threshold: float = DEFAULT_THRESHOLD,
    max_results: Optional[int] = None,
) -> List[Tuple[str, float]]:
    """Find best matching candidates above threshold.

    Args:
        query: Query string to match
        candidates: List of candidate strings to search
        threshold: Minimum similarity threshold
        max_results: Maximum number of results (None for all)

    Returns:
        List of (candidate, score) tuples sorted by score descending
    """
    if not candidates:
        return []

    scored = [
        (candidate, fuzzy_score(query, candidate, threshold))
        for candidate in candidates
    ]

    matches = [(c, s) for c, s in scored if s >= threshold]
    matches.sort(key=lambda x: x[1], reverse=True)

    if max_results is not None:
        matches = matches[:max_results]

    return matches


def suggest_best_match(
    query: str,
    candidates: List[str],
    threshold: float = DEFAULT_THRESHOLD,
    max_suggestions: int = MAX_SUGGESTIONS,
) -> Optional[str]:
    """Generate a suggestion string for the best match or list alternatives.

    Args:
        query: The query string (e.g., misspelled tool name)
        candidates: List of valid candidates to search
        threshold: Minimum similarity threshold for matching
        max_suggestions: Maximum suggestions to show when no match found

    Returns:
        Suggestion string like "Did you mean 'foo'?" or "Available tools: 'a', 'b'..."
        Returns None if candidates list is empty
    """
    if not candidates:
        return None

    matches = find_best_matches(query, candidates, threshold)

    if matches:
        best_match, best_score = matches[0]
        return f"Did you mean '{best_match}'?"

    if len(candidates) <= max_suggestions:
        items_list = ", ".join(f"'{c}'" for c in candidates)
    else:
        items_list = ", ".join(f"'{c}'" for c in candidates[:max_suggestions])
        items_list += f", ... ({len(candidates) - max_suggestions} more)"

    return f"Available tools: {items_list}"
