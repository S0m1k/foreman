from dc_extraction import find_tags


def tags_of(text):
    return [hit.tag for hit in find_tags(text)]


class TestFindTags:
    def test_latin_hyphen(self):
        assert tags_of("установка AHU-01 в осях") == ["AHU-01"]

    def test_short_tag(self):
        assert tags_of("клапан V-17") == ["V-17"]

    def test_cyrillic(self):
        assert "П-1" in tags_of("приточная система П-1")

    def test_cyrillic_two_letters(self):
        assert "ВК-3" in tags_of("стояк ВК-3")

    def test_suffix_letter(self):
        assert tags_of("K-12a") == ["K-12a"]

    def test_space_separator_normalised(self):
        assert tags_of("AHU 01") == ["AHU-01"]

    def test_gost_rejected(self):
        assert tags_of("ГОСТ 123") == []

    def test_sp_norm_rejected(self):
        assert tags_of("СП 60") == []

    def test_paper_size_rejected(self):
        assert tags_of("формат А1") == []

    def test_dn_rejected(self):
        assert tags_of("труба DN 50") == []
        assert tags_of("DN50") == []

    def test_unit_prefix_rejected(self):
        assert tags_of("3 м2 площади") == []

    def test_sentence_end(self):
        assert tags_of("установить V-17.") == ["V-17"]

    def test_no_partial_word(self):
        assert tags_of("КОД-2000-X") == []  # digits too long / embedded
