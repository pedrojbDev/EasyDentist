from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from importlib.metadata import Distribution, distributions
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name

ALLOWED_LICENSES = frozenset({"Apache-2.0", "BSD", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT"})
EXCEPTIONS_PATH = Path(__file__).with_name("license-exceptions.json")
_BLOCKED_PATTERN = re.compile(r"(?<![A-Z])(AGPL|GPL|SSPL)(?![A-Z])")
_OPERATORS_PATTERN = re.compile(r"\b(?:AND|OR|WITH)\b", re.IGNORECASE)
_FULL_TEXT_LICENSE_HASHES = {
    # Canonical Apache-2.0 text embedded in pip-api 0.0.35 metadata.
    "0e7a64e3ff18df112dedf585be24ab5386bb6cb5c1b357882f239b1b55ef573e": "Apache-2.0",
}
_LICENSE_ALIASES = {
    "MIT": "MIT",
    "MIT LICENSE": "MIT",
    "LICENSE :: OSI APPROVED :: MIT LICENSE": "MIT",
    "ISC": "ISC",
    "ISC LICENSE": "ISC",
    "LICENSE :: OSI APPROVED :: ISC LICENSE": "ISC",
    "APACHE-2.0": "Apache-2.0",
    "APACHE 2.0": "Apache-2.0",
    "APACHE LICENSE 2.0": "Apache-2.0",
    "APACHE LICENSE, VERSION 2.0": "Apache-2.0",
    "LICENSE :: OSI APPROVED :: APACHE SOFTWARE LICENSE": "Apache-2.0",
    "BSD": "BSD",
    "BSD LICENSE": "BSD",
    "LICENSE :: OSI APPROVED :: BSD LICENSE": "BSD",
    "BSD-2-CLAUSE": "BSD-2-Clause",
    "BSD 2-CLAUSE": "BSD-2-Clause",
    "BSD 2 CLAUSE": "BSD-2-Clause",
    "BSD-3-CLAUSE": "BSD-3-Clause",
    "BSD 3-CLAUSE": "BSD-3-Clause",
    "BSD 3 CLAUSE": "BSD-3-Clause",
    "PSF-2.0": "PSF-2.0",
    "PSF LICENSE": "PSF-2.0",
    "PSFL": "PSF-2.0",
    "LICENSE :: OSI APPROVED :: PYTHON SOFTWARE FOUNDATION LICENSE": "PSF-2.0",
}


def discover_distributions() -> list[Distribution]:
    """Return every installed distribution, including development dependencies."""
    return list(distributions())


def normalize_license(distribution: Distribution) -> str:
    """Resolve package metadata to one policy value, or a review-required value."""
    metadata = distribution.metadata
    expression = metadata.get("License-Expression", "")
    if expression and expression.strip():
        return _normalize_value(expression)

    license_value = metadata.get("License", "")
    if license_value and license_value.strip():
        return _normalize_value(license_value)

    raw_values = _classifiers(metadata)

    values = {_normalize_value(value) for value in raw_values if value and value.strip()}
    values.discard("")
    if not values:
        return "unknown"
    if len(values) == 1:
        return values.pop()
    return f"ambiguous: {' | '.join(sorted(values))}"


def _classifiers(metadata: Any) -> list[str]:
    get_all = getattr(metadata, "get_all", None)
    if get_all is not None:
        return [value for value in get_all("Classifier", []) if value.startswith("License ::")]
    if isinstance(metadata, Mapping):
        classifiers = metadata.get("Classifier", [])
        if isinstance(classifiers, str):
            classifiers = [classifiers]
        return [
            value
            for value in classifiers
            if isinstance(value, str) and value.startswith("License ::")
        ]
    return []


def _normalize_value(value: str) -> str:
    compact = " ".join(value.split())
    upper = compact.upper()
    if _BLOCKED_PATTERN.search(upper):
        return compact
    full_text_license = _FULL_TEXT_LICENSE_HASHES.get(
        hashlib.sha256(compact.encode("utf-8")).hexdigest()
    )
    if full_text_license is not None:
        return full_text_license
    if _OPERATORS_PATTERN.search(upper):
        return compact
    return _LICENSE_ALIASES.get(upper, compact)


def load_exceptions(path: Path = EXCEPTIONS_PATH) -> set[tuple[str, str, str]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    return {
        (canonicalize_name(entry["package"]), entry["version"], _normalize_value(entry["license"]))
        for entry in entries
    }


def audit_distributions(
    installed_distributions: Iterable[Distribution], exceptions: set[tuple[str, str, str]]
) -> list[str]:
    """Apply the fail-closed license policy to all supplied distributions."""
    failures: list[str] = []
    for distribution in sorted(
        installed_distributions, key=lambda item: canonicalize_name(item.metadata["Name"])
    ):
        name = canonicalize_name(distribution.metadata["Name"])
        license_value = normalize_license(distribution)
        exception_key = (name, distribution.version, license_value)
        display_name = distribution.metadata["Name"]
        if _BLOCKED_PATTERN.search(license_value.upper()):
            failures.append(f"{display_name}: blocked license ({license_value})")
        elif _is_allowed_license(license_value) or exception_key in exceptions:
            continue
        else:
            failures.append(f"{display_name}: manual license review required ({license_value})")
    return failures


def _is_allowed_license(license_value: str) -> bool:
    components = [component.strip() for component in _OPERATORS_PATTERN.split(license_value)]
    return bool(components) and all(component in ALLOWED_LICENSES for component in components)


def main() -> None:
    failures = audit_distributions(discover_distributions(), load_exceptions())
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
