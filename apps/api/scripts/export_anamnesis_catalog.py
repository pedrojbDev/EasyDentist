"""Export the immutable anamnesis catalog as the web contract.

The web form renders sections and questions from this generated JSON so the
pt-BR copy and stable IDs live only in the Python catalog. Run without
``--check`` to regenerate; the API test suite fails when the committed file
drifts from ``SECTIONS``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.anamnesis.templates.cfo_2026_v1 import SECTIONS, TEMPLATE_ID, TEMPLATE_LABEL

DEFAULT_PATH = (
    Path(__file__).resolve().parents[2] / "web" / "src" / "features" / "anamnesis" / "catalog.json"
)


def render_catalog() -> str:
    catalog = {
        "template_id": TEMPLATE_ID,
        "template_label": TEMPLATE_LABEL,
        "sections": [
            {
                "id": section.id,
                "title": section.title,
                "questions": [
                    {
                        "id": question.id,
                        "prompt": question.prompt,
                        "answer_type": question.answer_type.value,
                        "options": [
                            {"id": option.id, "label": option.label} for option in question.options
                        ],
                        "details_prompt": question.details_prompt,
                        "details_required": question.details_required,
                    }
                    for question in section.questions
                ],
            }
            for section in SECTIONS
        ],
    }
    return json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_catalog(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_catalog(), encoding="utf-8")


def check_catalog(path: Path) -> bool:
    if not path.exists():
        return False
    return path.read_text(encoding="utf-8") == render_catalog()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python scripts/export_anamnesis_catalog.py")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        if check_catalog(args.path):
            print("catalog.json is up to date")
            return 0
        print(
            "catalog.json is out of date; run: uv run python scripts/export_anamnesis_catalog.py",
            file=sys.stderr,
        )
        return 1

    write_catalog(args.path)
    print(f"wrote {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
