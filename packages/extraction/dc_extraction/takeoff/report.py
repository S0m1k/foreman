"""CSV export for Russian-locale spreadsheet software.

Windows' Russian regional settings use `;` as the list separator and `,` as
the decimal separator. A file that mixes the two - `;`-delimited fields with
`.`-decimal numbers, which is what a naive `csv.writer` produces - opens in
Excel with every numeric column silently imported as text: no right
alignment, no `SUM()`, and every review of it looks broken at a glance even
though the underlying figures are correct.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _cell(value: Any, decimals: int) -> str:
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, float):
        return f"{value:.{decimals}f}".replace(".", ",")
    return str(value)


def write_ru_csv(path: str | Path, header: list[str], rows: list[list[Any]],
                 decimals: int = 1) -> Path:
    """Write a `;`-delimited CSV with `,` decimals, ready for RU-locale Excel."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(header)
        for row in rows:
            writer.writerow([_cell(v, decimals) for v in row])
    return path
