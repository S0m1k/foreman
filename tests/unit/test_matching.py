from dc_matching import fuzzy_key, match_entities, normalize_tag
from dc_schemas import Entity, MatchLevel


def entity(tag, doc="doc", page=1, **kwargs):
    return Entity(document_id=doc, page=page, tag=tag, **kwargs)


class TestNormalizeTag:
    def test_case_and_separators(self):
        assert normalize_tag("ahu 01") == normalize_tag("AHU-01") == "AHU01"

    def test_fuzzy_zero_padding(self):
        assert fuzzy_key("AHU-01") == fuzzy_key("AHU-1")

    def test_fuzzy_homoglyphs(self):
        # Cyrillic В-3 vs Latin B-3
        assert fuzzy_key("В-3") == fuzzy_key("B-3")


class TestMatchEntities:
    def test_exact(self):
        matches = match_entities([entity("AHU-01")], [entity("AHU-01", doc="spec")])
        assert len(matches) == 1
        assert matches[0].level == MatchLevel.EXACT
        assert matches[0].confidence == 1.0

    def test_normalized(self):
        matches = match_entities([entity("AHU 01")], [entity("ahu-01", doc="spec")])
        assert matches[0].level == MatchLevel.NORMALIZED
        assert matches[0].confidence >= 0.9

    def test_orphans(self):
        matches = match_entities([entity("V-17")], [entity("R-01", doc="spec")])
        pairs = {(m.drawing_entity.tag if m.drawing_entity else None,
                  m.spec_entity.tag if m.spec_entity else None) for m in matches}
        assert ("V-17", None) in pairs
        assert (None, "R-01") in pairs

    def test_semantic_capped_confidence(self):
        matches = match_entities([entity("AHU-01A")], [entity("AHU-01B", doc="spec")])
        semantic = [m for m in matches if m.level == MatchLevel.SEMANTIC]
        assert semantic and semantic[0].confidence <= 0.75

    def test_richest_duplicate_kept(self):
        from dc_schemas import Quantity
        poor = entity("R-01")
        rich = entity("R-01")
        rich.quantity = Quantity.of(8, "pcs")
        matches = match_entities([poor, rich], [entity("R-01", doc="spec")])
        assert matches[0].drawing_entity.quantity is not None
