"""Vision model abstraction.

The pipeline never talks to a concrete model — it talks to
:class:`VisionModel`.  The default implementation speaks the OpenAI-compatible
chat API, which is how Qwen2.5-VL is served locally (vLLM, Ollama, LM Studio),
so swapping Qwen for InternVL or anything else is a configuration change.

When no endpoint is configured :func:`create_vision_model` returns ``None``
and the pipeline falls back to deterministic, grounded extraction only.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class VisionModelError(RuntimeError):
    pass


class VisionModel(ABC):
    """Interface required by the extraction and verification stages."""

    name: str = "abstract"
    version: str = "0"

    @abstractmethod
    def analyze_page(self, image: bytes, prompt: str) -> dict[str, Any]:
        """Free-form page analysis; must return parsed JSON."""

    @abstractmethod
    def extract_entities(self, image: bytes, context: dict[str, Any]) -> dict[str, Any]:
        """Extract entities from a page image given textual context."""

    @abstractmethod
    def verify_conflict(self, evidence: dict[str, Any]) -> dict[str, Any]:
        """Decide whether a candidate finding is a real contradiction."""


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_json_reply(raw: str) -> dict[str, Any]:
    """Parse a JSON-only model reply, tolerating markdown fences.

    Free text is *not* accepted as an internal API: anything that does not
    parse raises :class:`VisionModelError` and the caller decides what to do.
    """
    text = (raw or "").strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise VisionModelError(f"model reply is not JSON: {text[:200]!r}")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise VisionModelError(f"model reply is invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise VisionModelError("model reply is not a JSON object")
    return parsed


class OpenAICompatVisionModel(VisionModel):
    """Any VLM served behind an OpenAI-compatible ``/v1/chat/completions``."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: float = 180.0,
        temperature: float = 0.0,
        prompts: dict[str, str] | None = None,
        prompt_version: str = "v1",
        max_tokens: int = 4096,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.name = model
        self.version = model
        self.prompt_version = prompt_version
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._extra_body = extra_body or {}
        self._prompts = prompts or {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._model = model

    # -- plumbing ----------------------------------------------------------

    def _chat(self, prompt: str, images: list[bytes]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            encoded = base64.b64encode(image).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
            )
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                "messages": [{"role": "user", "content": content}],
                **self._extra_body,
            },
        )
        if response.status_code != 200:
            raise VisionModelError(f"VLM HTTP {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
            choice = payload["choices"][0]
            reply = choice["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise VisionModelError(f"unexpected VLM response shape: {exc}") from exc
        if not (reply or "").strip():
            # Thinking-mode models can burn the whole budget on reasoning.
            raise VisionModelError(
                f"VLM returned empty content (finish_reason="
                f"{choice.get('finish_reason')!r}); raise max_tokens or disable thinking"
            )
        return parse_json_reply(reply)

    def _prompt(self, key: str) -> str:
        try:
            return self._prompts[key]
        except KeyError as exc:
            raise VisionModelError(f"prompt {key!r} not loaded") from exc

    # -- VisionModel -------------------------------------------------------

    def analyze_page(self, image: bytes, prompt: str) -> dict[str, Any]:
        return self._chat(prompt, [image])

    def extract_entities(self, image: bytes, context: dict[str, Any]) -> dict[str, Any]:
        key = (
            "specification_extraction"
            if context.get("document_type") == "SPECIFICATION"
            else "drawing_entity_extraction"
        )
        prompt = self._prompt(key).format(
            page_number=context.get("page_number", "?"),
            page_text=context.get("page_text", "")[:8000],
        )
        return self._chat(prompt, [image])

    def verify_conflict(self, evidence: dict[str, Any]) -> dict[str, Any]:
        prompt = self._prompt("conflict_verification").format(
            evidence_json=json.dumps(evidence.get("summary", {}), ensure_ascii=False, indent=2)
        )
        images = [img for img in (evidence.get("drawing_crop"), evidence.get("spec_crop")) if img]
        return self._chat(prompt, images)
