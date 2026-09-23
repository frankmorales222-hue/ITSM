"""Generate the Northstar Endpoint Agent Windows tray icon without dependencies."""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "endpoint_agent" / "assets" / "northstar.ico"


def pixel_art(size: int) -> bytes:
    data = bytearray(size * size * 4)
    center = (size - 1) / 2
    radius = size * 0.46
    for y in range(size):
        for x in range(size):
            dx, dy = x - center, y - center
            distance = math.hypot(dx, dy)
            index = (y * size + x) * 4
            if distance <= radius:
                # Northstar navy circle with a subtle blue lower highlight.
                t = max(0.0, min(1.0, (dy / radius + 1) / 2))
                red = int(9 + 11 * t)
                green = int(67 + 44 * t)
                blue = int(122 + 58 * t)
                data[index:index + 4] = bytes((red, green, blue, 255))

    # A high-contrast four point star at the centre; deliberately oversized
    # so the mark is recognizable in the 16px Windows notification area.
    outer, inner = size * 0.31, size * 0.095
    points: list[tuple[float, float]] = []
    for point in range(8):
        angle = -math.pi / 2 + point * math.pi / 4
        length = outer if point % 2 == 0 else inner
        points.append((center + math.cos(angle) * length, center + math.sin(angle) * length))

    def inside(px: float, py: float) -> bool:
        contained = False
        previous = len(points) - 1
        for current in range(len(points)):
            xi, yi = points[current]
            xj, yj = points[previous]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                contained = not contained
            previous = current
        return contained

    for y in range(size):
        for x in range(size):
            if inside(x + 0.5, y + 0.5):
                index = (y * size + x) * 4
                data[index:index + 4] = b"\xff\xff\xff\xff"
    return bytes(data)


def png(size: int) -> bytes:
    raw = pixel_art(size)
    scanlines = b"".join(b"\x00" + raw[row * size * 4:(row + 1) * size * 4] for row in range(size))

    def chunk(kind: bytes, value: bytes) -> bytes:
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(scanlines, 9)) + chunk(b"IEND", b"")


def main() -> None:
    images = [(size, png(size)) for size in (16, 24, 32, 48, 64, 128, 256)]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + len(images) * 16
    entries, payloads = [], []
    for size, image in images:
        encoded_size = 0 if size == 256 else size
        entries.append(struct.pack("<BBBBHHII", encoded_size, encoded_size, 0, 0, 1, 32, len(image), offset))
        payloads.append(image)
        offset += len(image)
    OUT.write_bytes(header + b"".join(entries) + b"".join(payloads))
    print(f"Created valid multi-size icon: {OUT}")


if __name__ == "__main__":
    main()
