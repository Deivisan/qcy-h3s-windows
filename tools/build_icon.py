"""Render the app SVG mark to a PNG-backed Windows ICO using Qt's SVG renderer."""
from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "assets" / "qcy-h3-control.svg"
OUTPUT = ROOT / "assets" / "qcy-h3-control.ico"


def main() -> None:
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        raise SystemExit(f"Invalid SVG: {SVG}")

    pngs: list[tuple[int, bytes]] = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        pngs.append((size, bytes(data)))

    header = struct.pack("<HHH", 0, 1, len(pngs))
    entries = bytearray()
    payload = bytearray()
    offset = 6 + len(pngs) * 16
    for size, png in pngs:
        dim = 0 if size == 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        payload += png
        offset += len(png)
    OUTPUT.write_bytes(header + entries + payload)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
