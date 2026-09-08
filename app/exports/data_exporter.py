"""
Export service (Phase 1 §32). Takes plain list-of-dict data (as produced
by the report/service functions elsewhere) and writes it to CSV or Excel.
Kept generic and dependency-light — PDF export for documents that need a
fixed layout (invoices, formatted reports) lives in app/printing instead.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def export_to_csv(rows: list[dict], destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(destination, index=False)
    return destination


def export_to_excel(rows: list[dict], destination: Path, sheet_name: str = "Sheet1") -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(destination, index=False, sheet_name=sheet_name)
    return destination
