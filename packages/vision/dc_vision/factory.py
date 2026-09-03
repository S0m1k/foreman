"""Prompt loading and vision-model construction."""

from __future__ import annotations

import logging
from pathlib import Path

from .model import OpenAICompatVisionModel, VisionModel

logger = logging.getLogger(__name__)

PROMPT_KEYS = (
    "drawing_entity_extraction",
    "specification_extraction",
    "conflict_verification",
)


def load_prompts(prompts_dir: str | Path, version: str = "v1") -> dict[str, str]:
    """Load versioned prompt files, e.g. ``drawing_entity_extraction_v1.txt``."""
    prompts: dict[str, str] = {}
    directory = Path(prompts_dir)
    for key in PROMPT_KEYS:
        path = directory / f"{key}_{version}.txt"
        if path.exists():
            prompts[key] = path.read_text(encoding="utf-8")
        else:
            logger.warning("prompt file missing: %s", path)
    return prompts


def create_vision_model(
    base_url: str | None,
    model: str | None,
    api_key: str = "not-needed",
    prompts_dir: str | Path = "prompts",
    prompt_version: str = "v1",
    timeout: float = 180.0,
) -> VisionModel | None:
    """Build the configured VLM, or ``None`` when no endpoint is configured.

    ``None`` is a legitimate mode: the pipeline then relies purely on the
    deterministic, grounded extractors and the rule-based verifier.
    """
    if not base_url or not model:
        logger.info("no VLM configured; running with deterministic extraction only")
        return None
    return OpenAICompatVisionModel(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
        prompts=load_prompts(prompts_dir, prompt_version),
        prompt_version=prompt_version,
    )
