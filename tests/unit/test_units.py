from dc_schemas import units


class TestParseNumber:
    def test_plain(self):
        assert units.parse_number("15000") == 15000

    def test_space_thousands(self):
        assert units.parse_number("15 000") == 15000

    def test_comma_thousands(self):
        assert units.parse_number("15,000") == 15000

    def test_comma_decimal(self):
        assert units.parse_number("15,5") == 15.5

    def test_dot_decimal(self):
        assert units.parse_number("15.5") == 15.5

    def test_mixed_european(self):
        assert units.parse_number("1.234,56") == 1234.56

    def test_mixed_english(self):
        assert units.parse_number("1,234.56") == 1234.56

    def test_garbage(self):
        assert units.parse_number("abc") is None
        assert units.parse_number("") is None


class TestCanonicalize:
    def test_cyrillic_flow(self):
        value, unit, dim = units.canonicalize(15000, "м³/ч")
        assert (value, unit, dim) == (15000.0, "m3/h", units.FLOW)

    def test_latin_flow_matches_cyrillic(self):
        assert units.canonicalize(1, "m3/h")[1] == units.canonicalize(1, "м3/ч")[1]

    def test_mm_to_m(self):
        assert units.canonicalize(1500, "mm")[0] == 1.5

    def test_litres_to_m3(self):
        assert units.canonicalize(500, "л")[0] == 0.5

    def test_kw(self):
        value, unit, dim = units.canonicalize(5.5, "кВт")
        assert (value, unit, dim) == (5.5, "kW", units.POWER)

    def test_unknown_unit_passthrough(self):
        value, unit, dim = units.canonicalize(10, "furlong")
        assert (value, unit, dim) == (10, "furlong", None)

    def test_none_value(self):
        assert units.canonicalize(None, "m") == (None, None, None)


class TestSameDimension:
    def test_cross_script(self):
        assert units.same_dimension("m3/h", "м³/ч")

    def test_length_family(self):
        assert units.same_dimension("mm", "м")

    def test_different(self):
        assert not units.same_dimension("kW", "м³/ч")


class TestFindMeasurements:
    def test_flow_with_superscript(self):
        found = units.find_measurements("15 000 м³/ч")
        assert len(found) == 1
        assert found[0].value == 15000
        assert units.lookup(found[0].unit).dimension == units.FLOW

    def test_does_not_merge_tag_digits(self):
        found = units.find_measurements("AHU-01 15000 m3/h")
        values = [m.value for m in found]
        assert 15000 in values
        assert 115000 not in values and 1.15 not in values

    def test_pieces(self):
        found = units.find_measurements("8 шт.")
        assert found[0].value == 8
        assert units.lookup(found[0].unit).dimension == units.COUNT

    def test_empty(self):
        assert units.find_measurements("") == []
