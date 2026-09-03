from dc_comparison import compare, verify_findings
from dc_matching import match_entities
from dc_schemas import (
    Entity,
    FindingStatus,
    FindingType,
    Quantity,
    Severity,
)


def entity(tag, doc, **kwargs):
    return Entity(document_id=doc, page=1, tag=tag, bbox=(0, 0, 10, 10), **kwargs)


def run(drawing, spec):
    return compare(match_entities(drawing, spec))


class TestPresence:
    def test_missing_in_specification(self):
        findings = run([entity("V-17", "d")], [])
        assert findings[0].type == FindingType.MISSING_IN_SPECIFICATION
        assert findings[0].severity == Severity.HIGH
        assert findings[0].drawing_evidence is not None
        assert findings[0].spec_evidence is None

    def test_missing_on_drawing(self):
        findings = run([], [entity("R-01", "s")])
        assert findings[0].type == FindingType.MISSING_ON_DRAWING

    def test_low_confidence_entity_produces_nothing(self):
        findings = run([entity("V-17", "d", confidence=0.3)], [])
        assert findings == []


class TestQuantity:
    def test_mismatch(self):
        d = entity("R-01", "d", quantity=Quantity.of(8, "pcs"))
        s = entity("R-01", "s", quantity=Quantity.of(7, "pcs"))
        findings = run([d], [s])
        assert findings[0].type == FindingType.QUANTITY_MISMATCH
        assert findings[0].drawing_value.value == 8
        assert findings[0].spec_value.value == 7

    def test_equal_quantity_silent(self):
        d = entity("R-01", "d", quantity=Quantity.of(8, "pcs"))
        s = entity("R-01", "s", quantity=Quantity.of(8, "pcs"))
        assert run([d], [s]) == []


class TestParameters:
    def test_airflow_mismatch(self):
        d = entity("AHU-01", "d", parameters={"airflow": Quantity.of(15000, "m3/h")})
        s = entity("AHU-01", "s", parameters={"airflow": Quantity.of(12000, "м3/ч")})
        findings = run([d], [s])
        assert findings[0].type == FindingType.PARAMETER_MISMATCH
        assert findings[0].severity == Severity.HIGH
        assert findings[0].parameter == "airflow"

    def test_cross_unit_equal_values_silent(self):
        d = entity("T-1", "d", parameters={"length": Quantity.of(1500, "mm")})
        s = entity("T-1", "s", parameters={"length": Quantity.of(1.5, "м")})
        assert run([d], [s]) == []

    def test_small_diff_low_severity(self):
        d = entity("AHU-01", "d", parameters={"power": Quantity.of(5.5, "kW")})
        s = entity("AHU-01", "s", parameters={"power": Quantity.of(5.58, "kW")})
        findings = run([d], [s])
        assert findings and findings[0].severity == Severity.LOW

    def test_tolerance_swallows_rounding(self):
        d = entity("AHU-01", "d", parameters={"power": Quantity.of(5.5, "kW")})
        s = entity("AHU-01", "s", parameters={"power": Quantity.of(5.51, "kW")})
        assert run([d], [s]) == []


class TestVerificationRouting:
    def test_rule_based_keeps_strong_finding_open(self):
        d = entity("AHU-01", "d", parameters={"airflow": Quantity.of(15000, "m3/h")})
        s = entity("AHU-01", "s", parameters={"airflow": Quantity.of(12000, "m3/h")})
        verified = verify_findings(run([d], [s]))
        assert verified[0].status == FindingStatus.OPEN
        assert verified[0].confidence >= 0.9

    def test_semantic_match_goes_to_review(self):
        d = entity("AHU-01A", "d", parameters={"airflow": Quantity.of(15000, "m3/h")})
        s = entity("AHU-01B", "s", parameters={"airflow": Quantity.of(12000, "m3/h")})
        verified = verify_findings(run([d], [s]))
        mismatches = [f for f in verified if f.type == FindingType.PARAMETER_MISMATCH]
        assert mismatches and mismatches[0].status == FindingStatus.NEEDS_REVIEW
