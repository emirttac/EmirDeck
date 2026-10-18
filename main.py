"""
EmirDeck — Ultra hafif Stream Deck / makro video oynatıcı.

Sistem tepsisinde sessizce çalışır; global kısayola basılınca
önceden hazırlanmış PyQt6 oynatıcıyı anında tam ekran açar.
"""

from __future__ import annotations

# QtMultimedia import edilmeden ÖNCE backend + log kuralları
from ffmpeg_silence import apply_env, silence_libav

apply_env()

import sys
import traceback
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from branding import make_app_icon
from config_manager import ensure_config, find_macro_by_key, load_config
from hotkeys import normalize_trigger
from i18n import set_language, t
from player import VideoPlayerWindow
from settings_gui import SettingsWindow

try:
    from hotkey_listener import HotkeyListener
except ImportError:  # pragma: no cover
    HotkeyListener = None  # type: ignore[misc, assignment]

# Windows taskbar groups by AppUserModelID + .exe icon (not just setWindowIcon)
_APP_USER_MODEL_ID = "emirttac.EmirDeck"


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_USER_MODEL_ID)
    except Exception:  # noqa: BLE001
        pass


def _resolve_app_icon() -> QIcon:
    """Prefer on-disk .ico (taskbar), fall back to painted mark."""
    bases: list[Path] = []
    if getattr(sys, "frozen", False):
        bases.append(Path(sys.executable).resolve().parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bases.append(Path(meipass))
    else:
        bases.append(Path(__file__).resolve().parent)

    for base in bases:
        for rel in ("emirdeck.ico", "assets/emirdeck.ico"):
            ico = base / rel
            if ico.is_file():
                icon = QIcon(str(ico))
                if not icon.isNull():
                    return icon
    return make_app_icon()


class HotkeyBridge(QObject):
    """pynput thread → Qt ana thread köprüsü."""

    triggered = pyqtSignal(str)  # canonical trigger_key


class EmirDeckApp(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.config = ensure_config()
        set_language(str(self.config.get("language", "auto")))

        self.player = VideoPlayerWindow()
        self.bridge = HotkeyBridge()
        self.bridge.triggered.connect(self._on_hotkey)

        self.settings: SettingsWindow | None = None
        self._hotkey_listener: Any = None

        self._icon = _resolve_app_icon()
        app.setWindowIcon(self._icon)

        self.tray = QSystemTrayIcon(self._icon, app)
        self.tray.setToolTip(t("app_name"))
        self._build_tray_menu()
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        QTimer.singleShot(0, self._boot_player)

        if HotkeyListener is None:
            QMessageBox.critical(None, t("missing_dep"), t("missing_pynput"))
        else:
            self.reload_hotkeys()

        self.tray.showMessage(
            t("app_name"),
            t("tray_running"),
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )

    def _build_tray_menu(self) -> None:
        menu = QMenu()

        self._act_settings = QAction(t("settings"), menu)
        self._act_settings.triggered.connect(self.open_settings)
        menu.addAction(self._act_settings)

        self._act_stop = QAction(t("stop_media"), menu)
        self._act_stop.triggered.connect(self.player.stop)
        menu.addAction(self._act_stop)

        menu.addSeparator()

        self._act_quit = QAction(t("quit"), menu)
        self._act_quit.triggered.connect(self.shutdown)
        menu.addAction(self._act_quit)

        self.tray.setContextMenu(menu)

    def _retranslate_tray(self) -> None:
        self.tray.setToolTip(t("app_name"))
        if hasattr(self, "_act_settings"):
            self._act_settings.setText(t("settings"))
            self._act_stop.setText(t("stop_media"))
            self._act_quit.setText(t("quit"))

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.open_settings()

    def open_settings(self) -> None:
        self.config = load_config()
        set_language(str(self.config.get("language", "auto")))
        if self.settings is None:
            self.settings = SettingsWindow(self.config, on_saved=self._on_config_saved)
            self.settings.setWindowIcon(self._icon)
            self.settings.language_changed.connect(self._on_language_changed)
        else:
            self.settings.set_config(self.config)
            self.settings.setWindowIcon(self._icon)
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def _on_language_changed(self, _code: str) -> None:
        self._retranslate_tray()

    def _boot_player(self) -> None:
        from logger import log

        log("boot: warmup + preload")
        self.player.warmup()
        self.player.preload_macros(self.config.get("macros", []))

    def _on_config_saved(self, config: dict[str, Any]) -> None:
        self.config = config
        set_language(str(config.get("language", "auto")))
        self._retranslate_tray()
        self.reload_hotkeys()
        self.player.preload_macros(config.get("macros", []))

    def reload_hotkeys(self) -> None:
        """Mevcut listener'ı durdurup config'teki kısayolları yeniden bağlar."""
        if HotkeyListener is None:
            return

        self._stop_listener()

        mapping: dict[str, Any] = {}
        for macro in self.config.get("macros", []):
            trigger = normalize_trigger(str(macro.get("trigger_key", "")))
            if not trigger:
                continue

            def _make_cb(key: str):
                def _cb() -> None:
                    self.bridge.triggered.emit(key)

                return _cb

            mapping[trigger] = _make_cb(trigger)

        if not mapping:
            return

        try:
            listener = HotkeyListener(mapping)
            listener.start()
            self._hotkey_listener = listener
        except Exception as exc:  # noqa: BLE001
            self.tray.showMessage(
                t("app_name"),
                t("hotkeys_failed", error=exc),
                QSystemTrayIcon.MessageIcon.Warning,
                4000,
            )

    def _stop_listener(self) -> None:
        listener = self._hotkey_listener
        self._hotkey_listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # noqa: BLE001
                pass

    @pyqtSlot(str)
    def _on_hotkey(self, trigger_key: str) -> None:
        macro = find_macro_by_key(self.config, trigger_key)
        if macro is None:
            # Config diskten değişmiş olabilir
            self.config = load_config()
            macro = find_macro_by_key(self.config, trigger_key)
        if macro is None:
            return
        self.player.play_macro(macro)

    def shutdown(self) -> None:
        self._stop_listener()
        self.player.stop()
        if self.settings is not None:
            self.settings.hide()
        self.tray.hide()
        self.app.quit()


def main() -> int:
    # MUST run before QApplication — otherwise taskbar keeps python/old .exe icon
    _set_windows_app_id()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("EmirDeck")
    app.setApplicationDisplayName("EmirDeck")
    app.setOrganizationName("emirttac")
    app.setWindowIcon(_resolve_app_icon())
    try:
        app.setStyle("windowsvista")
    except Exception:  # noqa: BLE001
        pass

    silence_libav()

    cfg = load_config()
    set_language(str(cfg.get("language", "auto")))

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, t("app_name"), t("tray_unavailable"))
        return 1

    # Tek örnek: ikinci açılışı engellemek hafif bir mutex ile
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    server_name = "EmirDeckSingleton"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(200):
        # Zaten çalışıyor — mevcut örneğe sinyal yok; sessizce çık
        socket.close()
        return 0

    local_server = QLocalServer()
    QLocalServer.removeServer(server_name)
    local_server.listen(server_name)

    deck = EmirDeckApp(app)
    # GC'den korunması için referans tut
    app._emirdeck = deck  # type: ignore[attr-defined]
    app._emirdeck_server = local_server  # type: ignore[attr-defined]

    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # pragma: no cover
        traceback.print_exc()
        raise
