from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.application import create_app

DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "web"
    / "src"
    / "lib"
    / "api"
    / "generated"
    / "openapi.json"
)


def render_spec() -> str:
    spec = create_app().openapi()
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_spec(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_spec(), encoding="utf-8")


def check_spec(path: Path) -> bool:
    if not path.exists():
        return False
    return path.read_text(encoding="utf-8") == render_spec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python scripts/export_openapi.py")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        if check_spec(args.path):
            print("openapi.json is up to date")
            return 0
        print(
            "openapi.json is out of date; run: uv run python scripts/export_openapi.py",
            file=sys.stderr,
        )
        return 1

    write_spec(args.path)
    print(f"wrote {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
