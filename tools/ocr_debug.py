from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ocr.geo import sorted_by_position  # noqa: E402
from app.ocr.passport import extract_passport  # noqa: E402
from app.ocr.providers import OcrProvider  # noqa: E402
from app.ocr.pts import extract_pts_front, extract_pts_back  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python tools/ocr_debug.py /path/to/photo.jpg [role]")
        sys.exit(2)
    path = Path(sys.argv[1])
    role = sys.argv[2] if len(sys.argv) > 2 else "seller"
    provider = OcrProvider()
    lines = provider.ocr(path.read_bytes())
    print(f"--- lines ({len(lines)})")
    for l in lines:
        print(f"  ({l.x0:.0f},{l.y0:.0f})-({l.x1:.0f},{l.y1:.0f}) score={l.score:.2f}  {l.text!r}")
    print("--- rolled up")
    for l in sorted_by_position(lines):
        print(f"  ({l.x0:.0f},{l.y0:.0f})-({l.x1:.0f},{l.y1:.0f}) score={l.score:.2f}  {l.text!r}")
    print("--- passap")
    print(json.dumps(extract_passport(lines, role), ensure_ascii=False, indent=2))
    print("--- pts front")
    print(json.dumps(extract_pts_front(lines), ensure_ascii=False, indent=2))
    print("--- pts back")
    print(json.dumps(extract_pts_back(lines), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()