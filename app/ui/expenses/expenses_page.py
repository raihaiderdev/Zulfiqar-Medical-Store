"""
Expenses page — full CRUD: Add Category, Add Expense, Edit, Delete, date filter.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services import expense_service
from app.utils.exceptions import ApplicationError


# ---------------------------------------------------------------------------
# Add Expense dialog
# ---------------------------------------------------------------------------
class AddExpenseDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Expense")
        layout = QFormLayout(self)

        self.category_combo = QComboBox()
        self._reload_categories()

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("e.g. 1500.00")
        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDate(date.today())
        self.description_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        layout.addRow("Category *", self.category_combo)
        layout.addRow("Amount (Rs) *", self.amount_edit)
        layout.addRow("Date *", self.date_edit)
        layout.addRow("Description", self.description_edit)
        layout.addRow("Notes", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _reload_categories(self) -> None:
        self.category_combo.clear()
        try:
            cats = expense_service.list_categories()
            for c in cats:
                self.category_combo.addItem(c.name, c.id)
        except ApplicationError:
            pass

    def _save(self) -> None:
        category_id = self.category_combo.currentData()
        if category_id is None:
            QMessageBox.warning(self, "Missing field", "Please add at least one category first.")
            return
        try:
            amount = float(self.amount_edit.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Amount must be a number.")
            return

        qd = self.date_edit.date()
        expense_date = date(qd.year(), qd.month(), qd.day())

        try:
            expense_service.add_expense(
                category_id=category_id,
                amount=amount,
                expense_date=expense_date,
                description=self.description_edit.text().strip() or None,
                notes=self.notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not add expense", str(exc))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Edit Expense dialog
# ---------------------------------------------------------------------------
class EditExpenseDialog(QDialog):
    def __init__(self, expense: dict, parent=None) -> None:
        super().__init__(parent)
        self._expense_id = expense["expense_id"]
        self.setWindowTitle("Edit Expense")
        layout = QFormLayout(self)

        self.category_combo = QComboBox()
        try:
            cats = expense_service.list_categories()
            for c in cats:
                self.category_combo.addItem(c.name, c.id)
            idx = self.category_combo.findData(expense["category_id"])
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
        except ApplicationError:
            pass

        self.amount_edit = QLineEdit(str(expense["amount"]))
        self.date_edit = QDateEdit(calendarPopup=True)
        parts = expense["date"].split("-")
        self.date_edit.setDate(
            date(int(parts[0]), int(parts[1]), int(parts[2]))
        )
        self.description_edit = QLineEdit(expense["description"])
        self.notes_edit = QLineEdit(expense["notes"])

        layout.addRow("Category *", self.category_combo)
        layout.addRow("Amount (Rs) *", self.amount_edit)
        layout.addRow("Date *", self.date_edit)
        layout.addRow("Description", self.description_edit)
        layout.addRow("Notes", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self) -> None:
        try:
            amount = float(self.amount_edit.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Amount must be a number.")
            return

        qd = self.date_edit.date()
        expense_date = date(qd.year(), qd.month(), qd.day())

        try:
            expense_service.edit_expense(
                self._expense_id,
                category_id=self.category_combo.currentData(),
                amount=amount,
                expense_date=expense_date,
                description=self.description_edit.text().strip() or None,
                notes=self.notes_edit.text().strip() or None,
            )
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not save changes", str(exc))
            return
        self.accept()


# ---------------------------------------------------------------------------
# Expenses page
# ---------------------------------------------------------------------------
class ExpensesPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # Header row
        header_row = QHBoxLayout()
        header = QLabel("Expenses")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch()

        add_cat_btn = QPushButton("＋ Add Category")
        add_cat_btn.setStyleSheet("padding: 6px 12px;")
        add_cat_btn.clicked.connect(self._add_category)
        header_row.addWidget(add_cat_btn)

        add_btn = QPushButton("＋ Add Expense")
        add_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 6px 14px; font-weight: 600;")
        add_btn.clicked.connect(self._add_expense)
        header_row.addWidget(add_btn)
        root.addLayout(header_row)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(calendarPopup=True)
        self.from_date.setDate(date.today().replace(day=1))
        filter_row.addWidget(self.from_date)
        filter_row.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(calendarPopup=True)
        self.to_date.setDate(date.today())
        filter_row.addWidget(self.to_date)

        filter_row.addWidget(QLabel("Category:"))
        self.category_filter = QComboBox()
        self.category_filter.addItem("All Categories", None)
        filter_row.addWidget(self.category_filter)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.refresh)
        filter_row.addWidget(search_btn)
        filter_row.addStretch()

        self.total_label = QLabel("Total: Rs 0.00")
        self.total_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #c0392b;")
        filter_row.addWidget(self.total_label)
        root.addLayout(filter_row)

        # Table: Date, Category, Description, Amount, Notes, Actions
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Date", "Category", "Description", "Amount (Rs)", "Notes", "Actions"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self.table)

        self._reload_category_filter()
        self.refresh()

    def _reload_category_filter(self) -> None:
        current_id = self.category_filter.currentData()
        self.category_filter.clear()
        self.category_filter.addItem("All Categories", None)
        try:
            cats = expense_service.list_categories()
            for c in cats:
                self.category_filter.addItem(c.name, c.id)
        except ApplicationError:
            pass
        # Restore selection
        if current_id is not None:
            idx = self.category_filter.findData(current_id)
            if idx >= 0:
                self.category_filter.setCurrentIndex(idx)

    def _add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if not ok or not name.strip():
            return
        try:
            expense_service.add_category(name.strip())
        except ApplicationError as exc:
            QMessageBox.critical(self, "Could not add category", str(exc))
            return
        self._reload_category_filter()
        QMessageBox.information(self, "Category added", f"'{name.strip()}' has been added.")

    def _add_expense(self) -> None:
        dialog = AddExpenseDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_expense(self, expense: dict) -> None:
        dialog = EditExpenseDialog(expense, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _delete_expense(self, expense_id: int) -> None:
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            "Are you sure you want to delete this expense? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            expense_service.delete_expense(expense_id)
        except ApplicationError as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
            return
        self.refresh()

    def refresh(self) -> None:
        fd = self.from_date.date()
        td = self.to_date.date()
        date_from = date(fd.year(), fd.month(), fd.day())
        date_to = date(td.year(), td.month(), td.day())
        cat_id = self.category_filter.currentData()

        try:
            expenses = expense_service.list_expenses(
                date_from=date_from,
                date_to=date_to,
                category_id=cat_id,
            )
        except ApplicationError as exc:
            QMessageBox.warning(self, "Cannot load expenses", str(exc))
            return

        self.table.setRowCount(0)
        grand_total = 0.0

        for exp in expenses:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(exp["date"]))
            self.table.setItem(row, 1, QTableWidgetItem(exp["category"]))
            self.table.setItem(row, 2, QTableWidgetItem(exp["description"]))
            amt_item = QTableWidgetItem(f"{exp['amount']:.2f}")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, amt_item)
            self.table.setItem(row, 4, QTableWidgetItem(exp["notes"]))

            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(2, 2, 2, 2)
            al.setSpacing(4)

            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet("padding: 3px 8px;")
            edit_btn.clicked.connect(lambda _, e=exp: self._edit_expense(e))

            del_btn = QPushButton("Delete")
            del_btn.setStyleSheet("padding: 3px 8px; background-color: #e74c3c; color: white;")
            del_btn.clicked.connect(lambda _, eid=exp["expense_id"]: self._delete_expense(eid))

            al.addWidget(edit_btn)
            al.addWidget(del_btn)
            self.table.setCellWidget(row, 5, actions)

            grand_total += exp["amount"]

        self.total_label.setText(f"Total: Rs {grand_total:,.2f}")
        self.table.resizeColumnsToContents()
