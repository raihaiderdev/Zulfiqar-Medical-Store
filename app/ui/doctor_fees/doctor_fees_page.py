"""
Doctor Fees page — record, review, correct/void, and daily summary.

Two tabs:
  Tab 1 "Fee Records"   — list/filter/record/correct/void entries
  Tab 2 "Daily Summary" — date-picker summary for end-of-day reconciliation
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import settings
from app.security.session_context import current_session
from app.utils.exceptions import ApplicationError


# ── Record / Correct dialog ───────────────────────────────────────────────

class _RecordFeeDialog(QDialog):
    """Dialog to record a new standalone doctor fee."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Record Doctor Fee")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._date_edit = QDateEdit(calendarPopup=True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Date *:", self._date_edit)

        self._doctor_edit = QLineEdit()
        self._doctor_edit.setPlaceholderText("e.g. Dr. Ahmed")
        form.addRow("Doctor Name *:", self._doctor_edit)

        self._amount_edit = QLineEdit()
        self._amount_edit.setPlaceholderText("0.00")
        form.addRow(f"Amount ({settings.currency}) *:", self._amount_edit)

        self._method_edit = QLineEdit()
        self._method_edit.setPlaceholderText("CASH / CARD / ONLINE (optional)")
        form.addRow("Payment Method:", self._method_edit)

        self._ref_edit = QLineEdit()
        self._ref_edit.setPlaceholderText("Token / initials (optional)")
        form.addRow("Patient Ref:", self._ref_edit)

        self._notes_edit = QLineEdit()
        self._notes_edit.setPlaceholderText("Optional notes")
        form.addRow("Notes:", self._notes_edit)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setText("Record Fee")
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self) -> None:
        doctor = self._doctor_edit.text().strip()
        if not doctor:
            QMessageBox.warning(self, "Missing field", "Doctor name is required.")
            return
        try:
            amount = float(self._amount_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Invalid amount", "Amount must be a number.")
            return
        if amount <= 0:
            QMessageBox.warning(self, "Invalid amount", "Amount must be greater than zero.")
            return

        qt_d = self._date_edit.date()
        fee_date = date(qt_d.year(), qt_d.month(), qt_d.day())
        if fee_date > date.today():
            QMessageBox.warning(self, "Invalid date", "Fee date cannot be in the future.")
            return

        try:
            from app.services.doctor_fee_service import record_doctor_fee
            record_doctor_fee(
                fee_date=fee_date,
                doctor_name=doctor,
                amount=amount,
                payment_method=self._method_edit.text().strip() or None,
                patient_reference=self._ref_edit.text().strip() or None,
                notes=self._notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        QMessageBox.information(self, "Recorded", "Doctor fee recorded successfully.")
        self.accept()


class _CorrectFeeDialog(QDialog):
    """Dialog to correct or void an existing fee."""

    def __init__(self, fee: dict, parent=None) -> None:
        super().__init__(parent)
        self._fee = fee
        self.setWindowTitle(f"Correct Fee — {fee['doctor_name']} — {settings.currency} {fee['amount']:.2f}")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        info = QLabel(
            f"<b>Date:</b> {fee['fee_date']}  |  "
            f"<b>Doctor:</b> {fee['doctor_name']}  |  "
            f"<b>Amount:</b> {settings.currency} {fee['amount']:.2f}"
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setStyleSheet("padding:6px;background:#eaf4fb;border-radius:4px;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._amount_edit = QLineEdit(str(fee['amount']))
        form.addRow(f"New Amount ({settings.currency}):", self._amount_edit)

        self._method_edit = QLineEdit(fee.get('payment_method', ''))
        form.addRow("Payment Method:", self._method_edit)

        self._notes_edit = QLineEdit(fee.get('notes', ''))
        form.addRow("Notes:", self._notes_edit)

        self._reason_edit = QLineEdit()
        self._reason_edit.setPlaceholderText("Required — explain the correction")
        form.addRow("Reason *:", self._reason_edit)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        correct_btn = QPushButton("✔ Save Correction")
        correct_btn.setStyleSheet("background:#27ae60;color:white;padding:6px 14px;border-radius:4px;")
        correct_btn.clicked.connect(self._correct)
        void_btn = QPushButton("✕ Void Entry")
        void_btn.setStyleSheet("background:#e74c3c;color:white;padding:6px 14px;border-radius:4px;")
        void_btn.clicked.connect(self._void)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(correct_btn)
        btn_row.addWidget(void_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _correct(self) -> None:
        reason = self._reason_edit.text().strip()
        if not reason:
            QMessageBox.warning(self, "Reason required", "Please enter a reason for the correction.")
            return
        try:
            amount = float(self._amount_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Invalid amount", "Amount must be a number.")
            return
        try:
            from app.services.doctor_fee_service import correct_doctor_fee
            correct_doctor_fee(
                fee_id=self._fee['fee_id'],
                new_amount=amount,
                new_payment_method=self._method_edit.text().strip() or None,
                new_notes=self._notes_edit.text().strip() or None,
                reason=reason,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        QMessageBox.information(self, "Corrected", "Fee entry corrected.")
        self.accept()

    def _void(self) -> None:
        reason = self._reason_edit.text().strip()
        if not reason:
            QMessageBox.warning(self, "Reason required", "Please enter a reason to void.")
            return
        if QMessageBox.question(self, "Confirm Void", "Void this fee entry? It will be excluded from totals.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        try:
            from app.services.doctor_fee_service import void_doctor_fee
            void_doctor_fee(fee_id=self._fee['fee_id'], reason=reason)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        QMessageBox.information(self, "Voided", "Fee entry voided.")
        self.accept()


# ── Tab 1: Fee Records ────────────────────────────────────────────────────

class _FeeRecordsTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fees: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        self._from_edit = QDateEdit(calendarPopup=True)
        self._from_edit.setDate(QDate.currentDate().addDays(-30))
        self._from_edit.setDisplayFormat("yyyy-MM-dd")
        filter_row.addWidget(self._from_edit)

        filter_row.addWidget(QLabel("To:"))
        self._to_edit = QDateEdit(calendarPopup=True)
        self._to_edit.setDate(QDate.currentDate())
        self._to_edit.setDisplayFormat("yyyy-MM-dd")
        filter_row.addWidget(self._to_edit)

        filter_row.addWidget(QLabel("Doctor:"))
        self._doctor_filter = QLineEdit()
        self._doctor_filter.setPlaceholderText("Filter by doctor name…")
        self._doctor_filter.setFixedWidth(180)
        filter_row.addWidget(self._doctor_filter)

        search_btn = QPushButton("🔍 Search")
        search_btn.clicked.connect(self.refresh)
        filter_row.addWidget(search_btn)

        filter_row.addStretch()

        if current_session.has_permission("doctor_fees.record"):
            record_btn = QPushButton("＋ Record Fee")
            record_btn.setStyleSheet(
                "background:#154c89;color:white;font-weight:600;"
                "padding:6px 14px;border-radius:4px;"
            )
            record_btn.clicked.connect(self._record_fee)
            filter_row.addWidget(record_btn)
        layout.addLayout(filter_row)

        # Table
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels([
            "Date", "Doctor", f"Amount ({settings.currency})",
            "Payment", "Reference", "Invoice", "Status", "Actions"
        ])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [0, 2, 3, 4, 5, 6, 7]:
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table, 1)

        # Totals strip
        totals_frame = QFrame()
        totals_frame.setStyleSheet(
            "QFrame{background:#eaf4fb;border-radius:4px;border:1px solid #aed6f1;padding:4px;}"
        )
        totals_layout = QHBoxLayout(totals_frame)
        totals_layout.setContentsMargins(10, 4, 10, 4)
        self._count_lbl = QLabel("0 entries")
        self._count_lbl.setStyleSheet("color:#555;font-size:12px;")
        totals_layout.addWidget(self._count_lbl)
        totals_layout.addStretch()
        self._total_lbl = QLabel(f"Total: {settings.currency} 0.00")
        self._total_lbl.setStyleSheet("font-size:14px;font-weight:700;color:#154c89;")
        totals_layout.addWidget(self._total_lbl)
        layout.addWidget(totals_frame)

        self.refresh()

    def refresh(self) -> None:
        qt_from = self._from_edit.date()
        qt_to   = self._to_edit.date()
        d_from  = date(qt_from.year(), qt_from.month(), qt_from.day())
        d_to    = date(qt_to.year(), qt_to.month(), qt_to.day())
        doctor  = self._doctor_filter.text().strip() or None

        try:
            from app.services.doctor_fee_service import list_doctor_fees
            self._fees = list_doctor_fees(date_from=d_from, date_to=d_to, doctor_name=doctor)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return

        self._table.setRowCount(0)
        STATUS_COLOURS = {
            "ACTIVE":    Qt.GlobalColor.darkGreen,
            "CORRECTED": Qt.GlobalColor.darkYellow,
            "VOIDED":    Qt.GlobalColor.red,
        }

        active_total = 0.0
        active_count = 0

        for fee in self._fees:
            row = self._table.rowCount()
            self._table.insertRow(row)

            self._table.setItem(row, 0, QTableWidgetItem(fee['fee_date']))
            self._table.setItem(row, 1, QTableWidgetItem(fee['doctor_name']))

            amt_item = QTableWidgetItem(f"{fee['amount']:.2f}")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, amt_item)

            self._table.setItem(row, 3, QTableWidgetItem(fee.get('payment_method', '')))
            self._table.setItem(row, 4, QTableWidgetItem(fee.get('patient_reference', '')))
            self._table.setItem(row, 5, QTableWidgetItem(fee.get('sale_reference', '')))

            st_item = QTableWidgetItem(fee['status'])
            st_item.setForeground(STATUS_COLOURS.get(fee['status'], Qt.GlobalColor.black))
            self._table.setItem(row, 6, st_item)

            # Actions cell
            if current_session.has_permission("doctor_fees.correct") and fee['status'] != "VOIDED":
                btn = QPushButton("Correct / Void")
                btn.setStyleSheet("padding:2px 8px;")
                btn.clicked.connect(lambda _, f=fee: self._open_correct(f))
                cell = QWidget()
                cl = QHBoxLayout(cell)
                cl.setContentsMargins(2, 1, 2, 1)
                cl.addWidget(btn)
                self._table.setCellWidget(row, 7, cell)

            if fee['status'] == 'ACTIVE':
                active_total += fee['amount']
                active_count += 1

        self._count_lbl.setText(
            f"{len(self._fees)} entries  ({active_count} active)"
        )
        self._total_lbl.setText(
            f"Total (active): {settings.currency} {active_total:.2f}"
        )

    def _record_fee(self) -> None:
        dlg = _RecordFeeDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _open_correct(self, fee: dict) -> None:
        dlg = _CorrectFeeDialog(fee, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()


# ── Tab 2: Daily Summary ──────────────────────────────────────────────────

class _DailySummaryTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Date picker row
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("Date:"))
        self._date_edit = QDateEdit(calendarPopup=True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        ctrl_row.addWidget(self._date_edit)

        today_btn = QPushButton("Today")
        today_btn.clicked.connect(self._go_today)
        ctrl_row.addWidget(today_btn)

        show_btn = QPushButton("Show")
        show_btn.setStyleSheet(
            "background:#154c89;color:white;font-weight:600;"
            "padding:5px 16px;border-radius:4px;"
        )
        show_btn.clicked.connect(self.refresh)
        ctrl_row.addWidget(show_btn)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Summary cards
        self._summary_frame = QFrame()
        self._summary_frame.setStyleSheet(
            "QFrame{background:#fef9e7;border-radius:5px;border:1px solid #f0c040;padding:6px;}"
        )
        self._summary_layout = QVBoxLayout(self._summary_frame)
        self._summary_layout.setContentsMargins(10, 6, 10, 6)
        self._summary_lbl = QLabel("Select a date and click Show.")
        self._summary_lbl.setStyleSheet("font-size:13px;color:#7d6608;font-weight:600;")
        self._summary_layout.addWidget(self._summary_lbl)
        layout.addWidget(self._summary_frame)

        # Per-doctor breakdown
        breakdown_lbl = QLabel("Per-Doctor Breakdown:")
        breakdown_lbl.setStyleSheet("font-weight:600;margin-top:4px;")
        layout.addWidget(breakdown_lbl)

        self._breakdown_table = QTableWidget(0, 3)
        self._breakdown_table.setHorizontalHeaderLabels(["Doctor", "Entries", f"Total ({settings.currency})"])
        hh = self._breakdown_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._breakdown_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._breakdown_table.setAlternatingRowColors(True)
        self._breakdown_table.setMaximumHeight(180)
        layout.addWidget(self._breakdown_table)

        # Full entry list for the day
        entries_lbl = QLabel("All Entries for Selected Day:")
        entries_lbl.setStyleSheet("font-weight:600;margin-top:4px;")
        layout.addWidget(entries_lbl)

        self._entries_table = QTableWidget(0, 6)
        self._entries_table.setHorizontalHeaderLabels([
            "Time", "Doctor", f"Amount ({settings.currency})", "Payment", "Invoice", "Status"
        ])
        hh2 = self._entries_table.horizontalHeader()
        hh2.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in [0, 2, 3, 4, 5]:
            hh2.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._entries_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._entries_table.setAlternatingRowColors(True)
        layout.addWidget(self._entries_table, 1)

        # Grand total
        gt_frame = QFrame()
        gt_frame.setStyleSheet(
            "QFrame{background:#eaf4fb;border-radius:4px;border:1px solid #aed6f1;padding:4px;}"
        )
        gt_layout = QHBoxLayout(gt_frame)
        gt_layout.setContentsMargins(10, 4, 10, 4)
        gt_layout.addStretch()
        self._grand_total_lbl = QLabel(f"Grand Total (ACTIVE): {settings.currency} 0.00")
        self._grand_total_lbl.setStyleSheet("font-size:14px;font-weight:700;color:#154c89;")
        gt_layout.addWidget(self._grand_total_lbl)
        layout.addWidget(gt_frame)

        # Load today by default
        self.refresh()

    def _go_today(self) -> None:
        self._date_edit.setDate(QDate.currentDate())
        self.refresh()

    def refresh(self) -> None:
        qt_d = self._date_edit.date()
        fee_date = date(qt_d.year(), qt_d.month(), qt_d.day())

        try:
            from app.services.doctor_fee_service import get_daily_fee_collection
            data = get_daily_fee_collection(fee_date=fee_date)
        except ApplicationError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return

        # Summary card
        self._summary_lbl.setText(
            f"📅  {data['fee_date']}  |  "
            f"Entries: {data['fee_count']}  |  "
            f"Total Collected: {settings.currency} {data['total_collected']:.2f}"
        )

        # Per-doctor breakdown
        self._breakdown_table.setRowCount(0)
        for doc in data['by_doctor']:
            row = self._breakdown_table.rowCount()
            self._breakdown_table.insertRow(row)
            self._breakdown_table.setItem(row, 0, QTableWidgetItem(doc['doctor_name']))
            cnt_item = QTableWidgetItem(str(doc['count']))
            cnt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._breakdown_table.setItem(row, 1, cnt_item)
            tot_item = QTableWidgetItem(f"{doc['total']:.2f}")
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._breakdown_table.setItem(row, 2, tot_item)

        # Entry list
        STATUS_COLOURS = {
            "ACTIVE":    Qt.GlobalColor.darkGreen,
            "CORRECTED": Qt.GlobalColor.darkYellow,
            "VOIDED":    Qt.GlobalColor.red,
        }
        self._entries_table.setRowCount(0)
        for entry in data['entries']:
            row = self._entries_table.rowCount()
            self._entries_table.insertRow(row)
            # Time from created_at not available in dict; use fee_date
            self._entries_table.setItem(row, 0, QTableWidgetItem(entry['fee_date']))
            self._entries_table.setItem(row, 1, QTableWidgetItem(entry['doctor_name']))
            amt = QTableWidgetItem(f"{entry['amount']:.2f}")
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._entries_table.setItem(row, 2, amt)
            self._entries_table.setItem(row, 3, QTableWidgetItem(entry.get('payment_method', '')))
            self._entries_table.setItem(row, 4, QTableWidgetItem(entry.get('sale_reference', '')))
            st = QTableWidgetItem(entry['status'])
            st.setForeground(STATUS_COLOURS.get(entry['status'], Qt.GlobalColor.black))
            if entry['status'] == 'VOIDED':
                for c in range(6):
                    item = self._entries_table.item(row, c)
                    if item:
                        from PySide6.QtGui import QColor
                        item.setForeground(QColor("#bbb"))
            self._entries_table.setItem(row, 5, st)

        self._grand_total_lbl.setText(
            f"Grand Total (ACTIVE): {settings.currency} {data['total_collected']:.2f}"
        )


# ── Main Doctor Fees page ─────────────────────────────────────────────────

class DoctorFeesPage(QWidget):
    """Main Doctor Fees page with two tabs: Fee Records and Daily Summary."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # Header
        hdr_row = QHBoxLayout()
        hdr = QLabel("Doctor Fees")
        hdr.setStyleSheet("font-size:18px;font-weight:600;")
        hdr_row.addWidget(hdr)
        hdr_row.addStretch()
        root.addLayout(hdr_row)

        # Info banner
        info = QLabel(
            "ℹ  Doctor consultation fees are recorded separately from medicine sales. "
            "Use 'Daily Summary' to reconcile end-of-day collections per doctor."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background:#eaf4fb;padding:8px;border-radius:4px;"
            "border:1px solid #aed6f1;font-size:12px;"
        )
        root.addWidget(info)

        # Tabs
        self._tabs = QTabWidget()
        self._records_tab = _FeeRecordsTab()
        self._daily_tab   = _DailySummaryTab()
        self._tabs.addTab(self._records_tab, "📋  Fee Records")
        self._tabs.addTab(self._daily_tab,   "📅  Daily Summary")
        root.addWidget(self._tabs, 1)

    def showEvent(self, event) -> None:
        """Refresh active tab when the page becomes visible."""
        super().showEvent(event)
        if self._tabs.currentIndex() == 0:
            self._records_tab.refresh()
        else:
            self._daily_tab.refresh()
