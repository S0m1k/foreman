"""CAD (DWG/DXF) support.

DWG is converted to DXF with the free ODA File Converter (must be installed
separately); DXF is handled natively by ezdxf.  The drawing is rendered to a
vector PDF so the rest of the pipeline (page images, evidence crops) works
unchanged, and the text is pulled straight from the CAD entities — precise
coordinates, no OCR involved.
"""

from .convert import CadConversionError, convert_dwg_to_dxf, find_oda_converter
from .loader import cad_to_pdf, is_cad_file, load_cad_document

__all__ = [
    "CadConversionError",
    "cad_to_pdf",
    "convert_dwg_to_dxf",
    "find_oda_converter",
    "is_cad_file",
    "load_cad_document",
]
