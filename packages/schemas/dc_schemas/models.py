"""Domain models shared by every stage of the pipeline.

These are transport/processing models (Pydantic), not database rows.  Every
value a model carries must be traceable to the source document — that is what
the ``raw``/``bbox``/``page`` fields are for.
"""

from __future__ import annotations

import enum
import uuid

from pydantic import BaseModel, Field

from . import units


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --- enums -----------------------------------------------------------------


class DocumentType(str, enum.Enum):
    DRAWING = "DRAWING"
    SPECIFICATION = "SPECIFICATION"


class FindingType(str, enum.Enum):
    MISSING_IN_SPECIFICATION = "MISSING_IN_SPECIFICATION"
    MISSING_ON_DRAWING = "MISSING_ON_DRAWING"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    PARAMETER_MISMATCH = "PARAMETER_MISMATCH"
    IDENTIFICATION_MISMATCH = "IDENTIFICATION_MISMATCH"


class Severity(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FindingStatus(str, enum.Enum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ExtractionSource(str, enum.Enum):
    """Where an entity (or a text block) came from."""

    PDF_TEXT = "pdf_text"
    OCR = "ocr"
    TABLE = "table"
    VLM = "vlm"
    HEURISTIC = "heuristic"


# --- geometry / text -------------------------------------------------------


BBox = tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points


class TextBlock(BaseModel):
    text: str
    bbox: BBox
    confidence: float = 1.0
    source: ExtractionSource = ExtractionSource.PDF_TEXT


class PageContent(BaseModel):
    page_number: int  # 1-based
    width: float
    height: float
    text: str = ""
    text_blocks: list[TextBlock] = Field(default_factory=list)
    image_path: str | None = None
    needs_ocr: bool = False


class DocumentContent(BaseModel):
    document_id: str
    type: DocumentType
    filename: str
    sha256: str
    pages: list[PageContent] = Field(default_factory=list)


# --- measurements ----------------------------------------------------------


class Quantity(BaseModel):
    """A measured value with its canonical form and the exact source text."""

    value: float | None = None
    unit: str | None = None
    canonical_value: float | None = None
    canonical_unit: str | None = None
    dimension: str | None = None
    raw: str | None = None  # exact substring the value was read from

    @classmethod
    def of(cls, value: float | None, unit: str | None, raw: str | None = None) -> Quantity:
        canonical_value, canonical_unit, dimension = units.canonicalize(value, unit)
        return cls(
            value=value,
            unit=unit,
            canonical_value=canonical_value,
            canonical_unit=canonical_unit,
            dimension=dimension,
            raw=raw,
        )

    def display(self) -> str:
        if self.value is None:
            return "—"
        value = f"{self.value:,.10g}".replace(",", " ")
        return f"{value} {self.unit}" if self.unit else value


# --- entities --------------------------------------------------------------


class Entity(BaseModel):
    """One identifiable object (a tag on a drawing, a row in a specification)."""

    id: str = Field(default_factory=lambda: new_id("entity"))
    document_id: str
    page: int
    tag: str
    type: str | None = None
    name: str | None = None
    parameters: dict[str, Quantity] = Field(default_factory=dict)
    quantity: Quantity | None = None  # piece count, when stated
    bbox: BBox | None = None
    confidence: float = 1.0
    source: ExtractionSource = ExtractionSource.HEURISTIC
    context: str | None = None  # nearby text the entity was read from


# --- matching --------------------------------------------------------------


class MatchLevel(str, enum.Enum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    SEMANTIC = "semantic"


class EntityMatch(BaseModel):
    drawing_entity: Entity | None = None
    spec_entity: Entity | None = None
    level: MatchLevel | None = None
    confidence: float = 0.0


# --- findings --------------------------------------------------------------


class Evidence(BaseModel):
    document_id: str
    page: int
    bbox: BBox | None = None
    snippet: str | None = None
    crop_path: str | None = None


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: new_id("finding"))
    type: FindingType
    severity: Severity
    status: FindingStatus = FindingStatus.OPEN
    entity_key: str  # the tag both sides agree on (or the orphan tag)
    parameter: str | None = None  # for PARAMETER_MISMATCH
    drawing_value: Quantity | None = None
    spec_value: Quantity | None = None
    drawing_entity_id: str | None = None
    spec_entity_id: str | None = None
    drawing_evidence: Evidence | None = None
    spec_evidence: Evidence | None = None
    explanation: str = ""
    # The three confidences are deliberately separate (extraction / matching /
    # conflict) — see the spec.  ``confidence`` is the conflict confidence.
    extraction_confidence: float = 1.0
    matching_confidence: float = 1.0
    confidence: float = 1.0


class VerificationResult(BaseModel):
    """Output of the VLM conflict-verification step."""

    is_conflict: bool
    confidence: float = 0.0
    reason: str = ""
    severity: Severity | None = None
