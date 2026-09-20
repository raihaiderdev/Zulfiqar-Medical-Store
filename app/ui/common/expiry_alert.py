"""
Expiry alert subsystem (Feature 2).

Rules:
  • Alert fires once per application session (class-level flag).
  • Uses proper calendar-month arithmetic for the 7-month threshold.
  • Three severity levels: EXPIRED, EXPIRING VERY SOON (≤ 1 month),
    EXPIRING SOON (≤ 7 months).
  • Shows a non-blocking summary dialog with a scrollable table.
  • Dashboard badge count is read from ExpiryAlertManager.alert_count().
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _months_until_expiry(today: date, expiry: date) -> float:
    """
    Calendar-aware months remaining.
    Returns a negative value for already-expired dates.
    """
    months = (expiry.year - today.year) * 12 + (expiry.month - today.month)
    # adjust for day-of-month
    if expiry.day < today.day:
        months -= 1
    return months


def _classify(today: date, expiry: date) -> Optional[str]:
    """
    Returns 'EXPIRED', 'EXPIRING VERY SOON', 'EXPIRING SOON', or None.
    Threshold: 7 calendar months.
    """
    if expiry < today:
        return "EXPIRED"
    months = _months_until_expiry(today, expiry)
    if months <= 1:
        return "EXPIRING VERY SOON"
    if months <= 7:
        return "EXPIRING SOON"
    return None


def _days_remaining(today: date, expiry: date) -> int:
    return (expiry - today).days


def get_expiry_alerts() -> list[dict]:
    """
    Load all batches with expiry alerts (cached: calls medicine_service
    which uses its own session_scope).  Returns list of dicts sorted by
    expiry_date ascending.
    """
    try:
        from app.services.medicine_service import expiry_report
        # Use 7 months ≈ 214 days as the outer bound for the DB query
        # (calendar arithmetic applied afterwards for exact classification).
        report = expiry_report(warning_days=214)
    except Exception:
        return []

    today = date.today()
    alerts: list[dict] = []

    # Add expired batches
    for b in report["expired"]:
        exp = date.fromisoformat(b["expiry_date"])
        alerts.append({
            "medicine_name": b["medicine_name"],
            "medicine_id":   b.get("medicine_id", ""),
            "batch_number":  b["batch_number"],
            "expiry_date":   b["expiry_date"],
            "days_remaining": _days_remaining(today, exp),
            "quantity":      b["quantity"],
            "severity":      "EXPIRED",
            "location":      b.get("location", ""),
        })

    # Add expiring-soon batches — apply 7-month calendar filter
    for b in report["expiring_soon"]:
        exp = date.fromisoformat(b["expiry_date"])
        severity = _classify(today, exp)
        if severity in ("EXPIRING VERY SOON", "EXPIRING SOON"):
            alerts.append({
                "medicine_name": b["medicine_name"],
                "medicine_id":   b.get("medicine_id", ""),
                "batch_number":  b["batch_number"],
                "expiry_date":   b["expiry_date"],
                "days_remaining": _days_remaining(today, exp),
                "quantity":      b["quantity"],
                "severity":      severity,
                "location":      b.get("location", ""),
            })

    alerts.sort(key=lambda x: x["expiry_date"])
    return alerts


class ExpiryAlertManager:
    """Process-wide singleton tracking the session alert state."""
    _alerted_this_session: bool = False
    _cache: list[dict] = []

    @classmethod
    def reset_for_session(cls) -> None:
        cls._alerted_this_session = False
        cls._cache = []

    @classmethod
    def alert_count(cls) -> dict:
        """Returns {'expired': N, 'very_soon': N, 'soon': N, 'total': N}.
        Always reloads from DB — never serves stale cache."""
        cls._cache = get_expiry_alerts()
        expired   = sum(1 for a in cls._cache if a["severity"] == "EXPIRED")
        very_soon = sum(1 for a in cls._cache if a["severity"] == "EXPIRING VERY SOON")
        soon      = sum(1 for a in cls._cache if a["severity"] == "EXPIRING SOON")
        return {
            "expired":   expired,
            "very_soon": very_soon,
            "soon":      soon,
            "total":     expired + very_soon + soon,
        }

    @classmethod
    def maybe_show_alert(cls, parent: QWidget) -> None:
        """Show the alert dialog once per session if there are any alerts."""
        if cls._alerted_this_session:
            return
        cls._alerted_this_session = True
        cls._cache = get_expiry_alerts()
        if cls._cache:
            dlg = ExpiryAlertDialog(cls._cache, parent)
            dlg.exec()

    @classmethod
    def show_alert_forced(cls, parent: QWidget) -> None:
        """Show alert regardless of session flag (e.g., user clicks badge)."""
        cls._cache = get_expiry_alerts()
        dlg = ExpiryAlertDialog(cls._cache, parent)
        dlg.exec()


class ExpiryAlertDialog(QDialog):
    """Scrollable table showing all expiry alerts with colour-coded severity."""

    _SEVERITY_COLOURS = {
        "EXPIRED": "#c0392b",          # red
        "EXPIRING VERY SOON": "#e67e22",  # orange
        "EXPIRING SOON": "#f39c12",    # yellow-orange
    }

    def __init__(self, alerts: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("⚠  Expiry Alerts")
        self.setMinimumSize(820, 480)
        layout = QVBoxLayout(self)

        counts = {
            "EXPIRED": sum(1 for a in alerts if a["severity"] == "EXPIRED"),
            "EXPIRING VERY SOON": sum(1 for a in alerts if a["severity"] == "EXPIRING VERY SOON"),
            "EXPIRING SOON": sum(1 for a in alerts if a["severity"] == "EXPIRING SOON"),
        }

        summary_row = QHBoxLayout()
        for label, colour in self._SEVERITY_COLOURS.items():
            count = counts.get(label, 0)
            badge = QLabel(f"{label}: {count}")
            badge.setStyleSheet(
                f"background: {colour}; color: white; font-weight: 700; "
                f"padding: 4px 10px; border-radius: 4px; font-size: 12px;"
            )
            summary_row.addWidget(badge)
        summary_row.addStretch()
        layout.addLayout(summary_row)

        info = QLabel(
            "Medicines expiring within 7 months are listed below. "
            "Expired medicines cannot be sold through POS."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #555; font-size: 12px; padding: 4px 0;")
        layout.addWidget(info)

        # Table — now with 8 columns including Medicine ID for clarity
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Severity", "Medicine", "Med ID", "Batch", "Expiry Date",
            "Days Left", "Qty Available", "Location"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        for alert in alerts:
            row = self.table.rowCount()
            self.table.insertRow(row)

            severity = alert["severity"]
            colour = self._SEVERITY_COLOURS.get(severity, "#000")

            sev_item = QTableWidgetItem(severity)
            sev_item.setForeground(Qt.GlobalColor.white)
            sev_item.setBackground(
                __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(colour)
            )
            sev_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, sev_item)

            self.table.setItem(row, 1, QTableWidgetItem(alert["medicine_name"]))

            # Medicine ID — helps distinguish duplicates with same name
            med_id_item = QTableWidgetItem(str(alert.get("medicine_id", "")))
            med_id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            med_id_item.setForeground(Qt.GlobalColor.darkBlue)
            self.table.setItem(row, 2, med_id_item)

            self.table.setItem(row, 3, QTableWidgetItem(alert["batch_number"]))
            self.table.setItem(row, 4, QTableWidgetItem(alert["expiry_date"]))

            days = alert["days_remaining"]
            days_text = str(days) if days >= 0 else f"{abs(days)} days overdue"
            days_item = QTableWidgetItem(days_text)
            if days < 0:
                days_item.setForeground(Qt.GlobalColor.red)
            elif days <= 30:
                days_item.setForeground(Qt.GlobalColor.darkRed)
            self.table.setItem(row, 5, days_item)

            self.table.setItem(row, 6, QTableWidgetItem(str(alert["quantity"])))
            self.table.setItem(row, 7, QTableWidgetItem(alert.get("location", "")))

        self.table.resizeColumnsToContents()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
