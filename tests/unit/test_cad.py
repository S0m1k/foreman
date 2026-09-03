from pathlib import Path

import ezdxf
import pytest

from dc_cad import cad_to_pdf, find_oda_converter, is_cad_file, load_cad_document
from dc_cad.convert import CadConversionError


def make_dxf(path: Path) -> None:
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    msp.add_text("AHU-01", dxfattribs={"height": 5}).set_placement((10, 100))
    msp.add_text("15 000 м3/ч", dxfattribs={"height": 3}).set_placement((10, 92))
    msp.add_mtext("R-01\n8 шт.", dxfattribs={"char_height": 3}).set_location((80, 100))
    msp.add_lwpolyline([(0, 0), (200, 0), (200, 120), (0, 120), (0, 0)])
    doc.saveas(str(path))


class TestIsCadFile:
    def test_extensions(self):
        assert is_cad_file("plan.dwg")
        assert is_cad_file("PLAN.DXF")
        assert not is_cad_file("plan.pdf")


class TestCadToPdf:
    @pytest.fixture(scope="class")
    def loaded(self, tmp_path_factory):
        root = tmp_path_factory.mktemp("cad")
        dxf = root / "plan.dxf"
        pdf = root / "plan.pdf"
        make_dxf(dxf)
        page = cad_to_pdf(dxf, pdf)
        return page, pdf

    def test_pdf_is_produced(self, loaded):
        _, pdf = loaded
        assert pdf.exists()
        assert pdf.read_bytes().startswith(b"%PDF")

    def test_text_blocks_extracted(self, loaded):
        page, _ = loaded
        texts = "\n".join(b.text for b in page.text_blocks)
        assert "AHU-01" in texts
        assert "15 000 м3/ч" in texts
        assert "R-01" in texts  # from MTEXT

    def test_no_ocr_needed(self, loaded):
        page, _ = loaded
        assert page.needs_ocr is False

    def test_bboxes_inside_page(self, loaded):
        page, _ = loaded
        for block in page.text_blocks:
            x0, y0, x1, y1 = block.bbox
            assert 0 <= x0 < x1 <= page.width + 1
            assert 0 <= y0 < y1 <= page.height + 1

    def test_extraction_pipeline_works(self, loaded):
        from dc_extraction import extract_page_entities
        from dc_schemas import DocumentType

        page, pdf = loaded
        entities = extract_page_entities(str(pdf), page, "doc", DocumentType.DRAWING)
        by_tag = {e.tag: e for e in entities}
        assert by_tag["AHU-01"].parameters["airflow"].value == 15000

    def test_crop_from_rendered_pdf(self, loaded):
        from dc_pdf import crop_region

        page, pdf = loaded
        png = crop_region(str(pdf), 1, page.text_blocks[0].bbox)
        assert png.startswith(b"\x89PNG")


class TestDwg:
    def test_missing_converter_message_is_actionable(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ODA_CONVERTER_PATH", raising=False)
        monkeypatch.setattr("dc_cad.convert.find_oda_converter", lambda *_: None)
        fake_dwg = tmp_path / "plan.dwg"
        fake_dwg.write_bytes(b"AC1032")
        with pytest.raises(CadConversionError, match="ODA File Converter"):
            load_cad_document(fake_dwg, tmp_path / "out.pdf")

    @pytest.mark.skipif(find_oda_converter() is None, reason="ODA converter not installed")
    def test_dwg_roundtrip(self, tmp_path):
        # Requires a real converter; exercised on machines that have it.
        dxf = tmp_path / "plan.dxf"
        make_dxf(dxf)
        # ezdxf cannot write DWG; the DWG path is covered by conversion of
        # real files where the converter exists. Here we only assert that a
        # DXF passed to the same entry point works.
        page = load_cad_document(dxf, tmp_path / "plan.pdf")
        assert page.text_blocks
