"""Load Drip-Bench cases from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from drip.eval.schema import Case


def cases_dir() -> Path:
    """Return the path to ``benchmarks/cases/`` relative to repo root."""
    return Path(__file__).resolve().parents[3] / "benchmarks" / "cases"


def load_case(path: Path) -> Case:
    data = yaml.safe_load(path.read_text())
    return Case.model_validate(data)


def load_all(directory: Path | None = None) -> list[Case]:
    directory = directory or cases_dir()
    if not directory.exists():
        raise FileNotFoundError(f"cases directory not found: {directory}")
    cases: list[Case] = []
    for path in sorted(directory.glob("*.yaml")):
        cases.append(load_case(path))
    return cases


def load_one(case_id: int, directory: Path | None = None) -> Case:
    for case in load_all(directory):
        if case.id == case_id:
            return case
    raise KeyError(f"case id {case_id} not found")
