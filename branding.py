"""Shared EmirDeck mark — same glyph for tray, windows, and .ico export."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF


def paint_logo(size: int = 64) -> QPixmap:
    """Gray rounded square + light play triangle (system tray mark)."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pad = max(1, size // 10)
    radius = max(2, size // 8)
    painter.setBrush(QColor("#2b2b2b"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(pad, pad, size - pad * 2, size - pad * 2, radius, radius)
    painter.setBrush(QColor("#f0f0f0"))
    poly = QPolygonF(
        [
            QPointF(size * 0.40, size * 0.30),
            QPointF(size * 0.40, size * 0.70),
            QPointF(size * 0.72, size * 0.50),
        ]
    )
    painter.drawPolygon(poly)
    painter.end()
    return px


def make_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(paint_logo(size))
    return icon


def export_ico(path: str | Path) -> Path:
    """Write a multi-resolution .ico for Windows exe / Inno Setup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # QPixmap.save needs an application instance on some platforms
    from PyQt6.QtGui import QGuiApplication
    import sys

    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication(sys.argv[:1])

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow required to export .ico (pip install pillow)") from exc

    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "logo.png"
        if not paint_logo(256).save(str(png), "PNG"):
            raise RuntimeError("Failed to save logo PNG")
        img = Image.open(png).convert("RGBA")
        img.save(
            path,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    return path


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "assets" / "emirdeck.ico"
    export_ico(out)
    print(out)
