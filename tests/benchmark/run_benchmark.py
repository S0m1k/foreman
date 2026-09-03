"""Benchmark harness: precision / recall / false-positive rate.

Two data sources:

1. Synthetic corpus (default) — generated projects with exact ground truth.
   Run:  python tests/benchmark/run_benchmark.py --projects 20
2. Real PDFs — drop project folders under tests/benchmark/data/<name>/ with
   drawing.pdf, specification.pdf and ground_truth.json:
       {"expected": [{"type": "QUANTITY_MISMATCH", "entity": "R-01"}, ...]}

A predicted finding counts as a true positive when (type, normalised entity)
matches an expected one.  The headline MVP metric is precision.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from pdfgen import DrawingCallout, SpecRow, make_drawing_pdf, make_spec_pdf  # noqa: E402

from dc_comparison import compare, verify_findings  # noqa: E402
from dc_extraction import extract_page_entities  # noqa: E402
from dc_matching import match_entities, normalize_tag  # noqa: E402
from dc_pdf import parse_pdf  # noqa: E402
from dc_schemas import DocumentType, FindingStatus  # noqa: E402

PREFIXES = ["AHU", "V", "R", "N", "F", "P", "K", "П", "В", "ВК"]
NAMES = {
    "AHU": "Приточная установка", "V": "Клапан", "R": "Радиатор", "N": "Насос",
    "F": "Фильтр", "P": "Панель", "K": "Конвектор", "П": "Приточная система",
    "В": "Вытяжная система", "ВК": "Стояк водоснабжения",
}


@dataclass
class GroundTruth:
    expected: list[tuple[str, str]] = field(default_factory=list)  # (type, tag)


def _tagset(rng: random.Random, count: int) -> list[str]:
    tags = set()
    while len(tags) < count:
        tags.add(f"{rng.choice(PREFIXES)}-{rng.randint(1, 40):02d}")
    return sorted(tags)


def generate_project(root: Path, index: int, rng: random.Random) -> GroundTruth:
    """One synthetic project: 5 correct, and up to 2 of each mismatch kind."""
    truth = GroundTruth()
    tags = _tagset(rng, 11)
    callouts: list[DrawingCallout] = []
    rows: list[SpecRow] = []

    def flow() -> int:
        return rng.randrange(1000, 20000, 500)

    pool = list(tags)
    # 5 consistent objects
    for _ in range(5):
        tag = pool.pop()
        qty, airflow = rng.randint(1, 9), flow()
        callouts.append(DrawingCallout(tag, [f"{airflow} м3/ч", f"{qty} шт."]))
        rows.append(SpecRow(tag, NAMES.get(tag.split("-")[0], "Оборудование"),
                            str(qty), characteristic=f"{airflow} м3/ч"))
    # 2 parameter mismatches
    for _ in range(2):
        tag = pool.pop()
        airflow = flow()
        callouts.append(DrawingCallout(tag, [f"{airflow} м3/ч"]))
        rows.append(SpecRow(tag, "Оборудование", "1", characteristic=f"{airflow + 2000} м3/ч"))
        truth.expected.append(("PARAMETER_MISMATCH", tag))
    # 2 quantity mismatches
    for _ in range(2):
        tag = pool.pop()
        qty = rng.randint(2, 8)
        callouts.append(DrawingCallout(tag, [f"{qty} шт."]))
        rows.append(SpecRow(tag, "Оборудование", str(qty + rng.choice([-1, 1, 2]))))
        truth.expected.append(("QUANTITY_MISMATCH", tag))
    # 1 missing in specification
    tag = pool.pop()
    callouts.append(DrawingCallout(tag, [f"{flow()} м3/ч"]))
    truth.expected.append(("MISSING_IN_SPECIFICATION", tag))
    # 1 missing on drawing
    tag = pool.pop()
    rows.append(SpecRow(tag, "Оборудование", "1", characteristic="2 кВт"))
    truth.expected.append(("MISSING_ON_DRAWING", tag))

    rng.shuffle(callouts)
    rng.shuffle(rows)
    project_dir = root / f"project_{index:02d}"
    project_dir.mkdir(parents=True, exist_ok=True)
    make_drawing_pdf(project_dir / "drawing.pdf", callouts)
    make_spec_pdf(project_dir / "specification.pdf", rows)
    (project_dir / "ground_truth.json").write_text(
        json.dumps({"expected": [{"type": t, "entity": e} for t, e in truth.expected]}),
        encoding="utf-8",
    )
    return truth


def run_project(project_dir: Path) -> list:
    drawing_pdf = project_dir / "drawing.pdf"
    spec_pdf = project_dir / "specification.pdf"
    drawing_entities, spec_entities = [], []
    for page in parse_pdf(drawing_pdf):
        drawing_entities += extract_page_entities(
            str(drawing_pdf), page, "drawing", DocumentType.DRAWING
        )
    for page in parse_pdf(spec_pdf):
        spec_entities += extract_page_entities(
            str(spec_pdf), page, "spec", DocumentType.SPECIFICATION
        )
    return verify_findings(compare(match_entities(drawing_entities, spec_entities)))


def evaluate(projects: list[Path], include_review: bool = False) -> dict:
    tp = fp = fn = 0
    per_type: dict[str, dict[str, int]] = {}
    for project_dir in projects:
        truth = json.loads((project_dir / "ground_truth.json").read_text(encoding="utf-8"))
        expected = {(e["type"], normalize_tag(e["entity"])) for e in truth["expected"]}
        findings = run_project(project_dir)
        if not include_review:
            findings = [f for f in findings if f.status != FindingStatus.NEEDS_REVIEW]
        predicted = {(f.type.value, normalize_tag(f.entity_key)) for f in findings}

        for kind, _tag in expected | predicted:
            bucket = per_type.setdefault(kind, {"tp": 0, "fp": 0, "fn": 0})
        for item in predicted & expected:
            tp += 1
            per_type[item[0]]["tp"] += 1
        for item in predicted - expected:
            fp += 1
            per_type[item[0]]["fp"] += 1
        for item in expected - predicted:
            fn += 1
            per_type[item[0]]["fn"] += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "projects": len(projects),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "false_positive_rate": round(fp / (tp + fp), 3) if tp + fp else 0.0,
        "per_type": per_type,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="run on real project folders instead of synthetic")
    args = parser.parse_args()

    if args.data_dir:
        projects = sorted(p for p in args.data_dir.iterdir()
                          if (p / "ground_truth.json").exists())
    else:
        rng = random.Random(args.seed)
        root = Path(__file__).parent / "_generated"
        for i in range(args.projects):
            generate_project(root, i, rng)
        projects = sorted(root.iterdir())

    report = evaluate(projects)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
