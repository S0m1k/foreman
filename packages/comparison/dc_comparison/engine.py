"""Deterministic comparison engine.

Plain backend code: given matched entity pairs it decides what differs.
``15000 != 12000`` is decided here, never by a model.  Every finding carries
evidence pointers (document, page, bbox, snippet) for both sides.
"""

from __future__ import annotations

from dc_schemas import (
    Entity,
    EntityMatch,
    Evidence,
    Finding,
    FindingStatus,
    FindingType,
    Quantity,
    Severity,
    units,
)

# Relative difference below this is treated as rounding noise, not a conflict.
VALUE_TOLERANCE = 0.01
# Findings whose overall confidence falls below this go to human review.
REVIEW_THRESHOLD = 0.70
# Entities extracted with less confidence than this never produce hard findings.
MIN_EXTRACTION_CONFIDENCE = 0.55

HIGH_RELATIVE_DIFF = 0.10
MEDIUM_RELATIVE_DIFF = 0.02


def _evidence(entity: Entity | None) -> Evidence | None:
    if entity is None:
        return None
    return Evidence(
        document_id=entity.document_id,
        page=entity.page,
        bbox=entity.bbox,
        snippet=(entity.context or entity.tag)[:300],
    )


def _relative_diff(a: float, b: float) -> float:
    denominator = max(abs(a), abs(b))
    if denominator == 0:
        return 0.0
    return abs(a - b) / denominator


def _values_differ(a: Quantity, b: Quantity) -> bool:
    if a.canonical_value is None or b.canonical_value is None:
        return False
    if a.dimension and b.dimension and a.dimension != b.dimension:
        return True  # same parameter written in incomparable units
    return _relative_diff(a.canonical_value, b.canonical_value) > VALUE_TOLERANCE


def _parameter_severity(a: Quantity, b: Quantity) -> Severity:
    if a.dimension and b.dimension and a.dimension != b.dimension:
        return Severity.MEDIUM
    diff = _relative_diff(a.canonical_value or 0.0, b.canonical_value or 0.0)
    if diff > HIGH_RELATIVE_DIFF:
        return Severity.HIGH
    if diff > MEDIUM_RELATIVE_DIFF:
        return Severity.MEDIUM
    return Severity.LOW


def _quantity_severity(a: float, b: float) -> Severity:
    if abs(a - b) >= 2 or _relative_diff(a, b) > 0.2:
        return Severity.HIGH
    return Severity.MEDIUM


def _base(
    match: EntityMatch,
    finding_type: FindingType,
    severity: Severity,
    explanation: str,
    **kwargs,
) -> Finding:
    drawing, spec = match.drawing_entity, match.spec_entity
    extraction_confidence = min(
        drawing.confidence if drawing else 1.0,
        spec.confidence if spec else 1.0,
    )
    matching_confidence = match.confidence if (drawing and spec) else 1.0
    finding = Finding(
        type=finding_type,
        severity=severity,
        entity_key=(drawing or spec).tag,
        drawing_entity_id=drawing.id if drawing else None,
        spec_entity_id=spec.id if spec else None,
        drawing_evidence=_evidence(drawing),
        spec_evidence=_evidence(spec),
        explanation=explanation,
        extraction_confidence=extraction_confidence,
        matching_confidence=matching_confidence,
        confidence=min(extraction_confidence, matching_confidence),
        **kwargs,
    )
    if finding.confidence < REVIEW_THRESHOLD:
        finding.status = FindingStatus.NEEDS_REVIEW
    return finding


def compare(matches: list[EntityMatch]) -> list[Finding]:
    """Turn matched entity pairs into candidate findings."""
    findings: list[Finding] = []
    for match in matches:
        drawing, spec = match.drawing_entity, match.spec_entity

        # -- presence ------------------------------------------------------
        if drawing is not None and spec is None:
            if drawing.confidence < MIN_EXTRACTION_CONFIDENCE:
                continue  # too shaky to accuse the specification of an omission
            findings.append(
                _base(
                    match,
                    FindingType.MISSING_IN_SPECIFICATION,
                    Severity.HIGH,
                    f"{drawing.tag} is present on the drawing (p.{drawing.page}) "
                    "but was not found in the specification.",
                )
            )
            continue
        if drawing is None and spec is not None:
            if spec.confidence < MIN_EXTRACTION_CONFIDENCE:
                continue
            findings.append(
                _base(
                    match,
                    FindingType.MISSING_ON_DRAWING,
                    Severity.HIGH,
                    f"{spec.tag} is listed in the specification (p.{spec.page}) "
                    "but was not found on the drawing.",
                )
            )
            continue
        if drawing is None or spec is None:  # defensive; both None never happens
            continue

        # -- identification ------------------------------------------------
        if drawing.tag.strip() != spec.tag.strip():
            severity = Severity.LOW if match.confidence >= 0.9 else Severity.MEDIUM
            findings.append(
                _base(
                    match,
                    FindingType.IDENTIFICATION_MISMATCH,
                    severity,
                    f"The drawing labels this object {drawing.tag!r} while the "
                    f"specification uses {spec.tag!r}; they appear to be the same object.",
                )
            )

        # -- quantity ------------------------------------------------------
        dq, sq = drawing.quantity, spec.quantity
        if dq and sq and dq.value is not None and sq.value is not None and dq.value != sq.value:
            findings.append(
                _base(
                    match,
                    FindingType.QUANTITY_MISMATCH,
                    _quantity_severity(dq.value, sq.value),
                    f"{drawing.tag}: the drawing shows {dq.display()} but the "
                    f"specification lists {sq.display()}.",
                    drawing_value=dq,
                    spec_value=sq,
                )
            )

        # -- parameters ----------------------------------------------------
        for name in sorted(set(drawing.parameters) & set(spec.parameters)):
            dv, sv = drawing.parameters[name], spec.parameters[name]
            if not units.same_dimension(dv.unit, sv.unit) and (
                dv.dimension is None or sv.dimension is None
            ):
                continue  # unknown units on either side — refuse to guess
            if _values_differ(dv, sv):
                findings.append(
                    _base(
                        match,
                        FindingType.PARAMETER_MISMATCH,
                        _parameter_severity(dv, sv),
                        f"{drawing.tag}: {name} differs — drawing {dv.display()}, "
                        f"specification {sv.display()}.",
                        parameter=name,
                        drawing_value=dv,
                        spec_value=sv,
                    )
                )
    return findings
