"""DWG -> DXF conversion via the ODA File Converter.

The ODA File Converter is free but cannot be redistributed, so it is an
external prerequisite: https://www.opendesign.com/guestfiles/oda_file_converter
Its path is taken from the ``ODA_CONVERTER_PATH`` setting/env or guessed from
the usual install locations.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class CadConversionError(RuntimeError):
    pass


_WINDOWS_INSTALL_ROOTS = [
    Path("C:/Program Files/ODA"),
    Path("C:/Program Files (x86)/ODA"),
]
_UNIX_CANDIDATES = [
    "/usr/bin/ODAFileConverter",
    "/opt/ODAFileConverter/ODAFileConverter",
]


def find_oda_converter(configured: str | None = None) -> str | None:
    """Locate the ODA File Converter binary, or ``None`` if not installed."""
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    env = os.environ.get("ODA_CONVERTER_PATH")
    if env:
        candidates.append(env)
    for root in _WINDOWS_INSTALL_ROOTS:
        if root.exists():
            # newest install version first
            candidates += [str(p) for p in sorted(root.glob("*/ODAFileConverter.exe"), reverse=True)]
    candidates += _UNIX_CANDIDATES
    which = shutil.which("ODAFileConverter")
    if which:
        candidates.append(which)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def convert_dwg_to_dxf(
    dwg_path: str | Path, converter_path: str | None = None
) -> Path:
    """Convert one DWG file to DXF; returns the path of the produced DXF.

    Raises :class:`CadConversionError` with an actionable message when the
    converter is missing or fails.
    """
    dwg_path = Path(dwg_path)
    converter = find_oda_converter(converter_path)
    if converter is None:
        raise CadConversionError(
            "DWG support requires the free ODA File Converter. Install it from "
            "https://www.opendesign.com/guestfiles/oda_file_converter and set "
            "ODA_CONVERTER_PATH to the executable, or upload DXF/PDF instead."
        )

    # ODA converts folders, not files: stage the DWG in its own temp dirs.
    with tempfile.TemporaryDirectory(prefix="oda_in_") as in_dir, tempfile.TemporaryDirectory(
        prefix="oda_out_"
    ) as out_dir:
        staged = Path(in_dir) / dwg_path.name
        shutil.copyfile(dwg_path, staged)
        # args: input_dir output_dir out_version out_type recurse audit [filter]
        command = [converter, in_dir, out_dir, "ACAD2018", "DXF", "0", "1"]
        # The Qt runtime resolves its platform plugin relative to the process
        # working directory on some installs; point both at the exe location.
        converter_dir = str(Path(converter).parent)
        env = os.environ.copy()
        plugin_dir = Path(converter_dir) / "platforms"
        if plugin_dir.exists():
            env.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(plugin_dir))
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=300,
                cwd=converter_dir, env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CadConversionError(f"ODA File Converter failed to run: {exc}") from exc
        produced = Path(out_dir) / (dwg_path.stem + ".dxf")
        if not produced.exists():
            raise CadConversionError(
                "ODA File Converter did not produce a DXF "
                f"(exit {result.returncode}): {result.stderr or result.stdout or 'no output'}"
            )
        final = Path(tempfile.mkdtemp(prefix="foreman_dxf_")) / produced.name
        shutil.copyfile(produced, final)
        logger.info("converted %s -> %s", dwg_path.name, final)
        return final
