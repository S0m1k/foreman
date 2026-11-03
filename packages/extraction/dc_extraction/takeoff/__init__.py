"""Duct takeoff from vector HVAC drawings.

Produces the table an estimator actually works with - system, section,
insulation, length - by measuring the drawing rather than reading it with a
vision model, and cross-checks the result against the designer's own
specification embedded in the same PDF.
"""

from .album import AlbumFitting, AlbumRun, AlbumSheet, AlbumTakeoff, remeasure_plan, run_album
from .assign import Component, assign_systems, build_components, exceeds_specification
from .callouts import COLOUR_FAMILY, leaders, normalise_size, size_dimensions
from .fittings import Fitting, fittings, spec_fitting_counts
from .geometry import DuctRun, centrelines, detect_scale, snap_width
from .network import Trunk, connect, merge_trunks
from .pipeline import (
    SheetTakeoff,
    TakeoffRow,
    measure_sheet,
    summarise,
    takeoff,
    totals_by_system,
)
from .qa import overlay
from .report import write_ru_csv, write_xlsx
from .sheets import Sheet, SheetKind, classify_sheet
from .spec import SpecSystem, parse_specification, unique_equipment

__all__ = [
    "AlbumFitting",
    "AlbumRun",
    "AlbumSheet",
    "AlbumTakeoff",
    "COLOUR_FAMILY",
    "Component",
    "Fitting",
    "DuctRun",
    "Sheet",
    "SheetKind",
    "SheetTakeoff",
    "SpecSystem",
    "TakeoffRow",
    "Trunk",
    "assign_systems",
    "build_components",
    "centrelines",
    "classify_sheet",
    "connect",
    "detect_scale",
    "exceeds_specification",
    "fittings",
    "leaders",
    "measure_sheet",
    "merge_trunks",
    "normalise_size",
    "overlay",
    "parse_specification",
    "remeasure_plan",
    "run_album",
    "size_dimensions",
    "snap_width",
    "spec_fitting_counts",
    "summarise",
    "takeoff",
    "totals_by_system",
    "unique_equipment",
    "write_ru_csv",
    "write_xlsx",
]
