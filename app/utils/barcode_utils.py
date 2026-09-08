"""
Barcode/QR support (Phase 1 §25). Generation only — *reading* a barcode
is handled for free by any USB keyboard-wedge scanner, which just types
the barcode digits followed by Enter into whatever text field has focus
(the POS search box or the barcode field on the medicine form). No
special driver integration is needed for that half.
"""
from __future__ import annotations

from pathlib import Path

import barcode
from barcode.writer import ImageWriter


def generate_barcode_image(value: str, destination: Path, symbology: str = "code128") -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    barcode_class = barcode.get_barcode_class(symbology)
    instance = barcode_class(value, writer=ImageWriter())
    # python-barcode appends its own extension; save without one and
    # rename the result to match the caller's requested destination.
    saved_path = Path(instance.save(str(destination.with_suffix(""))))
    if saved_path != destination:
        saved_path.replace(destination)
    return destination


def generate_qr_code_image(value: str, destination: Path) -> Path:
    import qrcode

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(value)
    img.save(str(destination))
    return destination
