"""Settings window — native-looking, multilingual."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from branding import make_app_icon
from config_manager import save_config
from hotkeys import normalize_trigger, to_pynput_hotkey, trigger_from_key_event
from i18n import LANG_AUTO, LANG_DE, LANG_EN, LANG_TR, LANG_ZH, file_filter, set_language, t

# Mid-gray tone (not bright white)
STYLESHEET = """
QWidget#SettingsRoot {
    background: #3a3a3a;
    color: #e0e0e0;
    font-size: 13px;
}
QLabel {
    color: #e0e0e0;
}
QTableWidget {
    background: #2e2e2e;
    alternate-background-color: #333333;
    border: 1px solid #555555;
    gridline-color: #4a4a4a;
    color: #e0e0e0;
    selection-background-color: #5a5a5a;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: #484848;
    color: #e8e8e8;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #555555;
    border-bottom: 1px solid #555555;
    font-weight: 600;
}
QLineEdit, QComboBox, QPushButton#KeyCapture {
    background: #2e2e2e;
    border: 1px solid #5c5c5c;
    color: #e0e0e0;
    padding: 5px 8px;
    min-height: 22px;
}
QComboBox QAbstractItemView {
    background: #2e2e2e;
    color: #e0e0e0;
    selection-background-color: #5a5a5a;
}
QLineEdit:focus, QComboBox:focus, QPushButton#KeyCapture:focus {
    border: 1px solid #8a8a8a;
}
QPushButton {
    background: #4a4a4a;
    border: 1px solid #5c5c5c;
    color: #e0e0e0;
    padding: 5px 14px;
    min-height: 24px;
}
QPushButton:hover { background: #555555; }
QPushButton:pressed { background: #404040; }
QPushButton#KeyCapture {
    text-align: left;
}
QPushButton#KeyCapture[listening="true"] {
    border: 1px solid #b0b0b0;
    background: #454545;
}
QLabel#Footer {
    color: #9a9a9a;
    font-size: 11px;
}
"""


class KeyCaptureButton(QPushButton):
    key_captured = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("KeyCapture")
        self._listening = False
        self._value = ""
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self.start_listening)
        self.retranslate()

    @property
    def value(self) -> str:
        return self._value

    def set_value(self, trigger: str) -> None:
        self._value = normalize_trigger(trigger)
        self._listening = False
        self.setProperty("listening", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._refresh_label()

    def retranslate(self) -> None:
        self._refresh_label()

    def start_listening(self) -> None:
        self._listening = True
        self.setProperty("listening", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(t("press_key"))
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._listening:
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Escape and not (
            event.modifiers()
            & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.ShiftModifier
                | Qt.KeyboardModifier.MetaModifier
            )
        ):
            self._listening = False
            self.setProperty("listening", "false")
            self.style().unpolish(self)
            self.style().polish(self)
            self._refresh_label()
            event.accept()
            return

        trigger = trigger_from_key_event(event)
        if not trigger or to_pynput_hotkey(trigger) is None:
            event.accept()
            return

        self._value = trigger
        self._listening = False
        self.setProperty("listening", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._refresh_label()
        self.key_captured.emit(self._value)
        event.accept()

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        if self._listening:
            self._listening = False
            self.setProperty("listening", "false")
            self.style().unpolish(self)
            self.style().polish(self)
            self._refresh_label()
        super().focusOutEvent(event)

    def _refresh_label(self) -> None:
        if self._listening:
            self.setText(t("press_key"))
        else:
            self.setText(self._value if self._value else t("assign_key"))


class SettingsWindow(QWidget):
    config_saved = pyqtSignal(dict)
    language_changed = pyqtSignal(str)

    def __init__(
        self,
        config: dict[str, Any],
        on_saved: Callable[[dict[str, Any]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsRoot")
        self.setMinimumSize(560, 400)
        self.resize(640, 460)
        self.setStyleSheet(STYLESHEET)
        self.setWindowIcon(make_app_icon())

        self._config = deepcopy(config)
        self._on_saved = on_saved
        self._updating_lang = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        lang_row = QHBoxLayout()
        self.lang_label = QLabel()
        self.lang_combo = QComboBox()
        self.lang_combo.setMinimumWidth(160)
        self.lang_combo.currentIndexChanged.connect(self._on_language_combo)
        lang_row.addWidget(self.lang_label)
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch(1)
        root.addLayout(lang_row)

        self.table = QTableWidget(0, 2)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, stretch=1)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.key_label = QLabel()
        self.key_btn = KeyCaptureButton()
        form.addRow(self.key_label, self.key_btn)

        self.path_label = QLabel()
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.path_edit = QLineEdit()
        self.browse_btn = QPushButton()
        self.browse_btn.setFixedWidth(96)
        self.browse_btn.clicked.connect(self._browse_file)
        path_row.addWidget(self.path_edit, stretch=1)
        path_row.addWidget(self.browse_btn)
        form.addRow(self.path_label, path_row)
        root.addLayout(form)

        actions = QHBoxLayout()
        self.del_btn = QPushButton()
        self.del_btn.clicked.connect(self._delete_selected)
        self.save_btn = QPushButton()
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save)
        actions.addWidget(self.del_btn)
        actions.addStretch(1)
        actions.addWidget(self.save_btn)
        root.addLayout(actions)

        self.footer = QLabel(
            '<a href="https://github.com/emirttac" style="color:#9a9a9a;">github.com/emirttac</a>'
        )
        self.footer.setObjectName("Footer")
        self.footer.setOpenExternalLinks(True)
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.footer)

        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self._fill_lang_combo()
        self.retranslate()
        self._reload_table()

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = deepcopy(config)
        self._fill_lang_combo()
        self.retranslate()
        self._reload_table()

    def retranslate(self) -> None:
        self.setWindowTitle(t("app_name"))
        self.lang_label.setText(t("language"))
        self.table.setHorizontalHeaderLabels([t("col_hotkey"), t("col_file")])
        self.key_label.setText(t("hotkey"))
        self.path_label.setText(t("file_path"))
        self.path_edit.setPlaceholderText(t("path_placeholder"))
        self.browse_btn.setText(t("browse"))
        self.del_btn.setText(t("delete"))
        self.save_btn.setText(t("save"))
        self.key_btn.retranslate()
        # Refresh combo labels without changing selection
        self._updating_lang = True
        idx = self.lang_combo.currentIndex()
        for i in range(self.lang_combo.count()):
            code = self.lang_combo.itemData(i)
            self.lang_combo.setItemText(i, self._lang_label(code))
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self._updating_lang = False

    def _lang_label(self, code: str) -> str:
        return {
            LANG_AUTO: t("lang_auto"),
            LANG_EN: t("lang_en"),
            LANG_DE: t("lang_de"),
            LANG_TR: t("lang_tr"),
            LANG_ZH: t("lang_zh"),
        }.get(code, code)

    def _fill_lang_combo(self) -> None:
        self._updating_lang = True
        self.lang_combo.clear()
        for code in (LANG_AUTO, LANG_EN, LANG_DE, LANG_TR, LANG_ZH):
            self.lang_combo.addItem(self._lang_label(code), code)
        pref = str(self._config.get("language", LANG_AUTO))
        i = self.lang_combo.findData(pref)
        self.lang_combo.setCurrentIndex(i if i >= 0 else 0)
        self._updating_lang = False

    def _on_language_combo(self, _index: int) -> None:
        if self._updating_lang:
            return
        code = self.lang_combo.currentData()
        if not code:
            return
        self._config["language"] = code
        set_language(code)
        self.retranslate()
        try:
            save_config(self._config)
        except OSError:
            pass
        self.language_changed.emit(code)
        if self._on_saved:
            self._on_saved(deepcopy(self._config))

    def _reload_table(self) -> None:
        macros = self._config.get("macros", [])
        self.table.setRowCount(len(macros))
        for row, macro in enumerate(macros):
            self.table.setItem(row, 0, QTableWidgetItem(str(macro.get("trigger_key", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(str(macro.get("video_path", ""))))

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, t("select_file"), "", file_filter())
        if path:
            self.path_edit.setText(path)

    def _on_row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        macros = self._config.get("macros", [])
        if 0 <= idx < len(macros):
            m = macros[idx]
            self.key_btn.set_value(str(m.get("trigger_key", "")))
            self.path_edit.setText(str(m.get("video_path", "")))

    def _save(self) -> None:
        trigger = normalize_trigger(self.key_btn.value)
        path = self.path_edit.text().strip()

        if not trigger:
            QMessageBox.warning(self, t("missing"), t("need_hotkey"))
            return
        if not path:
            QMessageBox.warning(self, t("missing"), t("need_path"))
            return
        if to_pynput_hotkey(trigger) is None:
            QMessageBox.warning(self, t("bad_key"), t("bad_key_msg", key=trigger))
            return

        macros: list[dict[str, Any]] = self._config.setdefault("macros", [])
        updated = False
        for macro in macros:
            if macro.get("trigger_key") == trigger:
                macro["video_path"] = path
                macro.setdefault("loop", False)
                updated = True
                break
        if not updated:
            macros.append({"trigger_key": trigger, "video_path": path, "loop": False})

        self._config["language"] = self.lang_combo.currentData() or LANG_AUTO

        try:
            save_config(self._config)
        except OSError as exc:
            QMessageBox.critical(self, t("error"), t("save_failed", error=exc))
            return

        self._reload_table()
        self.config_saved.emit(deepcopy(self._config))
        if self._on_saved:
            self._on_saved(deepcopy(self._config))

        self.key_btn.set_value("")
        self.path_edit.clear()

    def _delete_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        macros = self._config.get("macros", [])
        if not (0 <= idx < len(macros)):
            return
        macros.pop(idx)
        try:
            save_config(self._config)
        except OSError as exc:
            QMessageBox.critical(self, t("error"), t("save_failed", error=exc))
            return
        self._reload_table()
        self.key_btn.set_value("")
        self.path_edit.clear()
        self.config_saved.emit(deepcopy(self._config))
        if self._on_saved:
            self._on_saved(deepcopy(self._config))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()
        self.hide()
