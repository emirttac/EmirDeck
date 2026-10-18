"""Sıfır gecikmeli tam ekran medya — makro başına preload slot."""

from __future__ import annotations

import os
from typing import Any, Callable, Literal

from PyQt6.QtCore import QEvent, Qt, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QMovie, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import QApplication, QLabel, QStackedWidget, QVBoxLayout, QWidget

from logger import log

MediaKind = Literal["video", "audio", "image"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".jfif"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".opus"}
VIDEO_EXTS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".avi",
    ".mov",
    ".m4v",
    ".wmv",
    ".mpeg",
    ".mpg",
}

_READY = {
    QMediaPlayer.MediaStatus.LoadedMedia,
    QMediaPlayer.MediaStatus.BufferedMedia,
    QMediaPlayer.MediaStatus.BufferingMedia,
}


def _to_url(path_or_url: str) -> QUrl:
    value = path_or_url.strip()
    lower = value.lower()
    if lower.startswith(("http://", "https://", "rtsp://", "rtp://")):
        return QUrl(value)
    return QUrl.fromLocalFile(os.path.abspath(value))


def detect_media_kind(path_or_url: str) -> MediaKind:
    value = path_or_url.strip()
    lower = value.lower()
    path_part = lower.split("?", 1)[0]
    ext = os.path.splitext(path_part)[1]
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    if lower.startswith(("http://", "https://", "rtsp://", "rtp://")):
        return "video"
    return "video"


def _norm_path(path: str) -> str:
    if path.lower().startswith(("http://", "https://", "rtsp://", "rtp://")):
        return path.strip()
    return os.path.abspath(path.strip())


class _AvSlot:
    """Bir video/ses dosyası için önceden hazır player + widget."""

    def __init__(
        self,
        path: str,
        audio: QAudioOutput,
        parent: QWidget,
        on_ended: Callable[[], None],
    ) -> None:
        self.path = path
        self.kind = detect_media_kind(path)
        self.ready = False
        self._audio = audio
        self._on_ended = on_ended
        self._looping = False
        self._user_playing = False

        self.video = QVideoWidget(parent)
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video.setStyleSheet("background-color: #000000;")
        self.video.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.player = QMediaPlayer(parent)
        self.player.setVideoOutput(self.video)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)

    def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in _READY:
            self.ready = True
        if (
            self._user_playing
            and status == QMediaPlayer.MediaStatus.EndOfMedia
            and not self._looping
        ):
            self._on_ended()

    def _on_error(self, error: QMediaPlayer.Error, message: str = "") -> None:
        log(f"slot error: {self.path} {error} {message}")

    def begin_preload(self) -> None:
        self.player.setSource(_to_url(self.path))
        self._audio.setVolume(0.0)
        self.player.setAudioOutput(self._audio)
        self.player.play()

    def finish_preload(self) -> None:
        self.player.pause()
        self.player.setPosition(0)
        # Ses cihazını serbest bırak
        try:
            self.player.setAudioOutput(None)  # type: ignore[arg-type]
        except TypeError:
            pass
        self._audio.setVolume(1.0)
        self.ready = self.player.mediaStatus() in _READY
        log(f"slot preload done: ready={self.ready} {self.path}")

    def play(self, *, loop: bool) -> None:
        self._looping = loop
        self._user_playing = True
        self.player.setLoops(
            QMediaPlayer.Loops.Infinite if loop else QMediaPlayer.Loops.Once
        )
        self._audio.setVolume(1.0)
        self.player.setAudioOutput(self._audio)
        self.player.setPosition(0)
        self.player.play()
        log(
            f"slot play: ready={self.ready} status={self.player.mediaStatus()} {self.path}"
        )

    def halt(self) -> None:
        self._user_playing = False
        if self.player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self.player.pause()
            self.player.setPosition(0)
        try:
            self.player.setAudioOutput(None)  # type: ignore[arg-type]
        except TypeError:
            pass


class VideoPlayerWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._looping = False
        self._active = False
        self._kind: MediaKind = "video"
        self._movie: QMovie | None = None
        self._source_pix: QPixmap | None = None
        self._surface_ready = False
        self._slots: dict[str, _AvSlot] = {}
        self._active_slot: _AvSlot | None = None
        self._preload_list: list[str] = []
        self._preload_index = 0
        self._play_gen = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.MaximizeUsingFullscreenGeometryHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setStyleSheet("background-color: #000000;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.BlankCursor)

        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background-color: #000000;")

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #000000;")
        self.image_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.image_label.installEventFilter(self)

        self.audio_label = QLabel()
        self.audio_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_label.setStyleSheet("background-color: #000000;")
        self.audio_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.audio_label.installEventFilter(self)

        self.stack.addWidget(self.image_label)
        self.stack.addWidget(self.audio_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack)

        self.audio = QAudioOutput(QMediaDevices.defaultAudioOutput(), self)
        self.audio.setVolume(1.0)
        self.hide()

    def warmup(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())
        self.setWindowOpacity(0.0)
        self.showFullScreen()
        QApplication.processEvents()
        self.hide()
        self.setWindowOpacity(1.0)
        self._surface_ready = True
        log("warmup: surface ok")

    def preload_macros(self, macros: list[dict[str, Any]]) -> None:
        wanted: list[str] = []
        for m in macros:
            p = str(m.get("video_path") or "").strip()
            if not p:
                continue
            kind = detect_media_kind(p)
            if kind not in ("video", "audio"):
                continue
            if not p.lower().startswith(("http://", "https://")) and not os.path.isfile(
                p
            ):
                log(f"preload skip missing: {p}")
                continue
            key = _norm_path(p)
            if key not in wanted:
                wanted.append(key)

        for key in list(self._slots.keys()):
            if key not in wanted:
                slot = self._slots.pop(key)
                slot.halt()
                self.stack.removeWidget(slot.video)
                slot.video.deleteLater()
                slot.player.deleteLater()

        for key in wanted:
            if key not in self._slots:
                slot = _AvSlot(key, self.audio, self, on_ended=self.stop)
                slot.video.installEventFilter(self)
                self.stack.addWidget(slot.video)
                self._slots[key] = slot

        self._preload_list = [k for k in wanted if not self._slots[k].ready]
        self._preload_index = 0
        log(f"preload: pending={len(self._preload_list)} slots={len(self._slots)}")
        QTimer.singleShot(80, self._preload_step)

    def _preload_step(self) -> None:
        if self._active:
            QTimer.singleShot(250, self._preload_step)
            return
        if self._preload_index >= len(self._preload_list):
            log("preload: all done")
            return

        key = self._preload_list[self._preload_index]
        self._preload_index += 1
        slot = self._slots.get(key)
        if slot is None:
            QTimer.singleShot(20, self._preload_step)
            return

        log(f"preload step: {key}")
        try:
            slot.begin_preload()
        except Exception as exc:  # noqa: BLE001
            log(f"preload begin fail: {exc}")
            QTimer.singleShot(20, self._preload_step)
            return

        def _finish() -> None:
            if self._active:
                return
            try:
                slot.finish_preload()
            except Exception as exc:  # noqa: BLE001
                log(f"preload finish fail: {exc}")
            QTimer.singleShot(40, self._preload_step)

        QTimer.singleShot(550, _finish)

    def _ensure_slot(self, key: str) -> _AvSlot:
        slot = self._slots.get(key)
        if slot is not None:
            return slot
        slot = _AvSlot(key, self.audio, self, on_ended=self.stop)
        slot.video.installEventFilter(self)
        self.stack.addWidget(slot.video)
        self._slots[key] = slot
        return slot

    @pyqtSlot(dict)
    def play_macro(self, macro: dict[str, Any]) -> None:
        media_path = str(
            macro.get("video_path") or macro.get("media_path") or ""
        ).strip()
        if not media_path:
            return

        self._play_gen += 1
        gen = self._play_gen
        self._looping = bool(macro.get("loop", False))
        kind = detect_media_kind(media_path)
        self._kind = kind
        log(f"play_macro gen={gen} kind={kind} {media_path}")

        if self._active_slot is not None:
            self._active_slot.halt()
            self._active_slot = None

        if self._movie is not None:
            self._movie.stop()
            self.image_label.setMovie(None)  # type: ignore[arg-type]
            self._movie = None
        self.image_label.clear()
        self._source_pix = None

        self._active = True
        self._show_overlay()

        if kind == "image":
            self.stack.setCurrentWidget(self.image_label)
            self._show_image(media_path)
            self.image_label.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            return

        key = _norm_path(media_path)
        slot = self._ensure_slot(key)
        self._active_slot = slot

        if kind == "audio":
            self.stack.setCurrentWidget(self.audio_label)
            self.audio_label.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        else:
            self.stack.setCurrentWidget(slot.video)
            slot.video.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

        if not slot.ready and slot.player.source().isEmpty():
            slot.player.setSource(_to_url(key))

        slot.play(loop=self._looping)

        QTimer.singleShot(80, lambda: self._nudge(gen, slot, 1))
        QTimer.singleShot(250, lambda: self._nudge(gen, slot, 2))
        QTimer.singleShot(500, lambda: self._nudge(gen, slot, 3))

    def _nudge(self, gen: int, slot: _AvSlot, n: int) -> None:
        if gen != self._play_gen or not self._active or slot is not self._active_slot:
            return
        st = slot.player.playbackState()
        pos = slot.player.position()
        log(f"nudge{n}: state={st} pos={pos} ready={slot.ready}")
        if st == QMediaPlayer.PlaybackState.PlayingState and pos > 0:
            return
        slot.player.play()
        if n >= 2 and pos <= 0:
            slot.player.setPosition(0)
            slot.player.play()
            slot.video.update()

    def _show_overlay(self) -> None:
        if not self._surface_ready:
            self.showFullScreen()
            self._surface_ready = True
        else:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)
            self.show()
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()

    def _show_image(self, path: str) -> None:
        if path.lower().startswith(("http://", "https://")):
            return
        local = os.path.abspath(path)
        ext = os.path.splitext(local)[1].lower()
        if ext == ".gif":
            movie = QMovie(local)
            if movie.isValid():
                self._movie = movie
                self.image_label.setMovie(movie)
                movie.start()
                return
        pix = QPixmap(local)
        if pix.isNull():
            log(f"bad image: {local}")
            self.stop()
            return
        self._source_pix = pix
        self._fit_pixmap()

    def _fit_pixmap(self) -> None:
        if self._source_pix is None or self._source_pix.isNull():
            return
        target = self.size() if not self.size().isEmpty() else self.screen().size()
        self.image_label.setPixmap(
            self._source_pix.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    @pyqtSlot()
    def stop(self) -> None:
        if not self._active and self._active_slot is None:
            self.hide()
            return
        log("stop")
        self._active = False
        self._play_gen += 1
        if self._active_slot is not None:
            self._active_slot.halt()
            self._active_slot = None
        if self._movie is not None:
            self._movie.stop()
            self.image_label.setMovie(None)  # type: ignore[arg-type]
            self._movie = None
        self.image_label.clear()
        self._source_pix = None
        self.hide()
        if self._preload_index < len(self._preload_list):
            QTimer.singleShot(150, self._preload_step)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._active and self._kind == "image" and self._movie is None:
            self._fit_pixmap()

    def eventFilter(self, obj, event: QEvent) -> bool:  # type: ignore[override]
        watched = {self.image_label, self.audio_label}
        watched.update(s.video for s in self._slots.values())
        if obj in watched:
            if event.type() == QEvent.Type.KeyPress:
                assert isinstance(event, QKeyEvent)
                if event.key() == Qt.Key.Key_Escape:
                    self.stop()
                    return True
            if event.type() == QEvent.Type.MouseButtonPress:
                self.stop()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.stop()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.stop()
        event.accept()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.stop()
        event.ignore()
