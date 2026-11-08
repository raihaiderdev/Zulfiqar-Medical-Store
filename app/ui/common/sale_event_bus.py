"""
SaleEventBus — process-wide signal bus for completed sales.

Any UI component can connect to `sale_bus.sale_completed` to receive
a notification (with the sale_id) immediately after a sale is recorded.
This allows the Dashboard's "Last Order" panel to refresh automatically
without the dashboard polling the DB on every navigation click.

Usage:
    from app.ui.common.sale_event_bus import sale_bus
    sale_bus.sale_completed.connect(my_slot)   # connect in your widget
    sale_bus.sale_completed.emit(sale_id)       # emit after a sale
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class _SaleEventBus(QObject):
    """Singleton Qt signal carrier.  Use the module-level `sale_bus` instance."""
    sale_completed = Signal(int)   # emits sale_id after every successful sale


# Single process-wide instance — import and use this directly.
sale_bus = _SaleEventBus()
