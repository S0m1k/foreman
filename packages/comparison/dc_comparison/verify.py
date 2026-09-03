"""Finding verification.

Every candidate finding passes through verification before a user sees it.
With a vision model configured, the model receives both evidence crops plus the
structured values and answers the single question: same object, real
contradiction?  Without a model, a conservative rule-based verdict is produced
from the extraction/matching confidences.

Routing (identical for both paths):
* ``is_conflict == False``  -> the finding is dropped;
* ``confidence < 0.70``     -> shown as NEEDS_REVIEW;
* otherwise                 -> shown as OPEN with the (possibly adjusted) severity.
"""

from __future__ import annotations

import logging

from dc_pdf import crop_region
from dc_schemas import (
    Finding,
    FindingStatus,
    FindingType,
    Severity,
    VerificationResult,
)
from dc_vision import VisionModel, VisionModelError

from .engine import REVIEW_THRESHOLD

logger = logging.getLogger(__name__)

# Rule-based verifier: how much of the raw confidence each finding type keeps.
# Presence findings are the most sensitive to extraction misses, so they are
# discounted hardest — the MVP prefers NEEDS_REVIEW over a loud false alarm.
_TYPE_TRUST = {
    FindingType.PARAMETER_MISMATCH: 1.0,
    FindingType.QUANTITY_MISMATCH: 1.0,
    FindingType.MISSING_IN_SPECIFICATION: 0.9,
    FindingType.MISSING_ON_DRAWING: 0.9,
    FindingType.IDENTIFICATION_MISMATCH: 0.85,
}


def _rule_based_verdict(finding: Finding) -> VerificationResult:
    confidence = min(finding.extraction_confidence, finding.matching_confidence)
    confidence *= _TYPE_TRUST.get(finding.type, 0.8)
    return VerificationResult(
        is_conflict=True,
        confidence=round(confidence, 3),
        reason=finding.explanation,
        severity=finding.severity,
    )


def _crop(pdf_path: str | None, evidence) -> bytes | None:
    if not pdf_path or evidence is None or evidence.bbox is None:
        return None
    try:
        return crop_region(pdf_path, evidence.page, evidence.bbox)
    except Exception as exc:  # pragma: no cover - corrupt bbox etc.
        logger.warning("could not render evidence crop: %s", exc)
        return None


def _model_verdict(
    finding: Finding,
    vision_model: VisionModel,
    drawing_pdf: str | None,
    spec_pdf: str | None,
) -> VerificationResult:
    summary = {
        "finding_type": finding.type.value,
        "entity": finding.entity_key,
        "parameter": finding.parameter,
        "drawing_value": finding.drawing_value.model_dump() if finding.drawing_value else None,
        "specification_value": finding.spec_value.model_dump() if finding.spec_value else None,
        "drawing_snippet": finding.drawing_evidence.snippet if finding.drawing_evidence else None,
        "specification_snippet": finding.spec_evidence.snippet if finding.spec_evidence else None,
        "deterministic_explanation": finding.explanation,
    }
    raw = vision_model.verify_conflict(
        {
            "summary": summary,
            "drawing_crop": _crop(drawing_pdf, finding.drawing_evidence),
            "spec_crop": _crop(spec_pdf, finding.spec_evidence),
        }
    )
    severity = raw.get("severity")
    return VerificationResult(
        is_conflict=bool(raw.get("is_conflict", False)),
        confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.0)))),
        reason=str(raw.get("reason", "")),
        severity=Severity(severity) if severity in Severity._value2member_map_ else None,
    )


def verify_findings(
    findings: list[Finding],
    vision_model: VisionModel | None = None,
    drawing_pdf: str | None = None,
    spec_pdf: str | None = None,
) -> list[Finding]:
    """Filter and annotate findings; only what survives is shown to the user."""
    verified: list[Finding] = []
    for finding in findings:
        if vision_model is not None:
            try:
                verdict = _model_verdict(finding, vision_model, drawing_pdf, spec_pdf)
            except (VisionModelError, ValueError, TypeError) as exc:
                logger.warning(
                    "verification failed for %s (%s): %s — falling back to rules",
                    finding.entity_key, finding.type.value, exc,
                )
                verdict = _rule_based_verdict(finding)
        else:
            verdict = _rule_based_verdict(finding)

        if not verdict.is_conflict:
            logger.info(
                "dropping finding %s %s: verifier says not a conflict (%s)",
                finding.type.value, finding.entity_key, verdict.reason,
            )
            continue

        finding.confidence = verdict.confidence
        if verdict.reason and verdict.reason != finding.explanation:
            finding.explanation = f"{finding.explanation} {verdict.reason}".strip()
        if verdict.severity is not None:
            finding.severity = verdict.severity
        if verdict.confidence < REVIEW_THRESHOLD:
            finding.status = FindingStatus.NEEDS_REVIEW
        verified.append(finding)
    return verified
