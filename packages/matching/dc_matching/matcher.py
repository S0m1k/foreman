"""Entity matching between drawing and specification.

Three levels, tried in order, each with its own confidence:

1. exact tag equality;
2. normalised tag equality (case, separators, zero padding, homoglyphs);
3. semantic similarity (fuzzy string ratio, optionally confirmed by an LLM).

Low-confidence semantic matches are still returned — the comparison engine
turns them into ``NEEDS_REVIEW`` findings instead of hard contradictions.
"""

from __future__ import annotations

from collections import defaultdict

from rapidfuzz import fuzz

from dc_schemas import Entity, EntityMatch, MatchLevel

from .normalize import fuzzy_key, normalize_tag, strip_leading_zeros

EXACT_CONFIDENCE = 1.0
NORMALIZED_CONFIDENCE = 0.95
FUZZY_FOLD_CONFIDENCE = 0.85
SEMANTIC_MIN_RATIO = 80  # rapidfuzz percentage
# Below the review threshold on purpose: a guessed pairing must never surface
# as a hard contradiction, only as NEEDS_REVIEW.
SEMANTIC_MAX_CONFIDENCE = 0.65


def _group_by(entities: list[Entity], key_fn) -> dict[str, list[Entity]]:
    grouped: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        key = key_fn(entity.tag)
        if key:
            grouped[key].append(entity)
    return grouped


import re

_DIGITS = re.compile(r"\d+")


def _semantically_compatible(tag_a: str, tag_b: str) -> bool:
    """Guard against aggressive guessing (spec §3.5).

    Two tags may only be paired semantically when their numeric parts are
    equal (OCR/formatting noise in the letters) or adjacent (the V-03/V-04
    renumbering case).  AHU-36 and AHU-06 are different objects, full stop.
    """
    numbers_a = [int(n) for n in _DIGITS.findall(fuzzy_key(tag_a))]
    numbers_b = [int(n) for n in _DIGITS.findall(fuzzy_key(tag_b))]
    if numbers_a == numbers_b:
        return True
    if len(numbers_a) == len(numbers_b) == 1:
        return abs(numbers_a[0] - numbers_b[0]) == 1
    return False


def _pick(entities: list[Entity]) -> Entity:
    """When one tag appears several times, keep the richest occurrence."""
    return max(entities, key=lambda e: (len(e.parameters), e.quantity is not None, e.confidence))


def match_entities(
    drawing_entities: list[Entity],
    spec_entities: list[Entity],
) -> list[EntityMatch]:
    """Pair up drawing and specification entities.

    Returns one :class:`EntityMatch` per distinct object; unmatched entities
    come back with the opposite side set to ``None``.
    """
    matches: list[EntityMatch] = []
    drawing_left = list(drawing_entities)
    spec_left = list(spec_entities)

    for level, key_fn, confidence in (
        (MatchLevel.EXACT, lambda t: (t or "").strip(), EXACT_CONFIDENCE),
        (MatchLevel.NORMALIZED, lambda t: strip_leading_zeros(normalize_tag(t)), NORMALIZED_CONFIDENCE),
        (MatchLevel.NORMALIZED, fuzzy_key, FUZZY_FOLD_CONFIDENCE),
    ):
        drawing_groups = _group_by(drawing_left, key_fn)
        spec_groups = _group_by(spec_left, key_fn)
        for key, drawing_group in drawing_groups.items():
            spec_group = spec_groups.get(key)
            if not spec_group:
                continue
            matches.append(
                EntityMatch(
                    drawing_entity=_pick(drawing_group),
                    spec_entity=_pick(spec_group),
                    level=level,
                    confidence=confidence,
                )
            )
            for entity in drawing_group:
                drawing_left.remove(entity)
            for entity in spec_group:
                spec_left.remove(entity)

    # Level 3 — semantic/fuzzy pairing of the leftovers.  Deliberately
    # conservative: best mutual ratio above a high threshold, capped
    # confidence so downstream can route it to review.
    for drawing_entity in list(drawing_left):
        best: tuple[float, Entity] | None = None
        for spec_entity in spec_left:
            if not _semantically_compatible(drawing_entity.tag, spec_entity.tag):
                continue
            ratio = fuzz.ratio(fuzzy_key(drawing_entity.tag), fuzzy_key(spec_entity.tag))
            if ratio >= SEMANTIC_MIN_RATIO and (best is None or ratio > best[0]):
                best = (ratio, spec_entity)
        if best is not None:
            ratio, spec_entity = best
            matches.append(
                EntityMatch(
                    drawing_entity=drawing_entity,
                    spec_entity=spec_entity,
                    level=MatchLevel.SEMANTIC,
                    confidence=min(SEMANTIC_MAX_CONFIDENCE, ratio / 100.0),
                )
            )
            drawing_left.remove(drawing_entity)
            spec_left.remove(spec_entity)

    # Orphans — one per distinct tag, not one per occurrence: a specification
    # that lists the same system on twenty rows is still one missing object.
    orphan_key = lambda t: strip_leading_zeros(normalize_tag(t))  # noqa: E731
    for group in _group_by(drawing_left, orphan_key).values():
        matches.append(EntityMatch(drawing_entity=_pick(group), spec_entity=None))
    for group in _group_by(spec_left, orphan_key).values():
        matches.append(EntityMatch(drawing_entity=None, spec_entity=_pick(group)))
    return matches
