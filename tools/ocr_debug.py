from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ocr.geo import sorted_by_position  # noqa: E402
from app.ocr.passport import extract_passport  # noqa: E402
from app.ocr.providers import OcrProvider  # noqa: E402
from app.ocr.pts import extract_pts_front, extract_pts_back  # noqa: E402
from app.ocr.rdocs import RdocsProvider  # noqa: E402


def _rdocs_mode(path: Path, role: str) -> None:
    provider = RdocsProvider()
    print("rdocs available:", provider.available())
    res = provider.recognize(path.read_bytes())
    if res is None:
        print("rdocs: N/A (не установлено или недоступно)")
        return
    print(f"--- rdocs doctype={res.doctype} DocConf={res.docconf:.3f} timings={res.timings}")
    print(json.dumps(res.ocr, ensure_ascii=False, indent=2, default=str))
    mapped = provider.passport(path.read_bytes(), role) or {}
    print(f"--- rdocs {role}_*")
    print(json.dumps(mapped, ensure_ascii=False, indent=2))


def main() -> None:
    args = [a for a in sys.argv[1:] if a]
    rdocs = "--rdocs" in args
    args = [a for a in args if a != "--rdocs"]
    if not args:
        print("usage: python tools/ocr_debug.py /path/to/photo.jpg [role] [--rdocs]")
        sys.exit(2)
    path = Path(args[0])
    role = args[1] if len(args) > 1 else "seller"
    if rdocs:
        _rdocs_mode(path, role)
        return
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