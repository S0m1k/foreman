"""Entity extraction: deterministic rules, table parsing, VLM grounding."""

from .extractor import extract_page_entities
from .grounding import ground_vlm_entities
from .rules import extract_drawing_entities, guess_type
from .tables import extract_spec_lines, extract_tables_from_page, merge_by_tag
from .tags import TagHit, find_tags

__all__ = [
    "TagHit",
    "extract_drawing_entities",
    "extract_page_entities",
    "extract_spec_lines",
    "extract_tables_from_page",
    "find_tags",
    "ground_vlm_entities",
    "guess_type",
    "merge_by_tag",
]
