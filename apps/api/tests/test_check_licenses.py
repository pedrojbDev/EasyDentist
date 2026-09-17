from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import distribution

import pytest

from scripts.check_licenses import audit_distributions, normalize_license


@dataclass
class FakeDistribution:
    name: str
    version: str
    license_expression: str = ""
    license_value: str = ""
    classifiers: tuple[str, ...] = ()

    @property
    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "Name": self.name,
            "License-Expression": self.license_expression,
            "License": self.license_value,
        }
        if self.classifiers:
            metadata["Classifier"] = list(self.classifiers)
        return metadata


def test_audit_allows_a_recognized_permissive_license() -> None:
    failures = audit_distributions([FakeDistribution("permissive", "1.0", "MIT")], set())

    assert failures == []


def test_normalizes_the_locked_pip_api_apache_license_text() -> None:
    assert normalize_license(distribution("pip-api")) == "Apache-2.0"


def test_audit_allows_a_known_dual_permissive_license_expression() -> None:
    failures = audit_distributions(
        [FakeDistribution("dual-permissive", "1.0", "Apache-2.0 OR BSD-2-Clause")], set()
    )

    assert failures == []


def test_audit_allows_the_exact_asyncpg_apache_license_variant() -> None:
    failures = audit_distributions(
        [FakeDistribution("apache-variant", "1.0", "Apache License, Version 2.0")], set()
    )

    assert failures == []


def test_audit_preserves_terms_added_to_the_asyncpg_apache_license_variant() -> None:
    failures = audit_distributions(
        [FakeDistribution("apache-variant", "1.0", "Apache License, Version 2.0 AND GPL-3.0-only")],
        set(),
    )

    assert failures == [
        "apache-variant: blocked license (Apache License, Version 2.0 AND GPL-3.0-only)"
    ]


@pytest.mark.parametrize(
    ("license_expression", "expected_failure"),
    [
        ("BSD-3-Clause AND GPL-3.0-only", "blocked license (BSD-3-Clause AND GPL-3.0-only)"),
        ("BSD-2-Clause AND AGPL-3.0-only", "blocked license (BSD-2-Clause AND AGPL-3.0-only)"),
        ("BSD-3-Clause AND SSPL-1.0", "blocked license (BSD-3-Clause AND SSPL-1.0)"),
        (
            "BSD-3-Clause AND Custom-License",
            "manual license review required (BSD-3-Clause AND Custom-License)",
        ),
        ("Apache-2.0 AND GPL-3.0-only", "blocked license (Apache-2.0 AND GPL-3.0-only)"),
        (
            "Apache License Version 2.0 AND GPL-3.0-only",
            "blocked license (Apache License Version 2.0 AND GPL-3.0-only)",
        ),
    ],
)
def test_audit_preserves_every_term_in_a_composite_expression(
    license_expression: str, expected_failure: str
) -> None:
    failures = audit_distributions(
        [FakeDistribution("composite-license", "1.0", license_expression)], set()
    )

    assert failures == [f"composite-license: {expected_failure}"]


@pytest.mark.parametrize(
    ("license_expression", "expected_failure"),
    [
        ("BSD-3-Clause / GPL-3.0-only", "blocked license (BSD-3-Clause / GPL-3.0-only)"),
        ("BSD-2-Clause, AGPL-3.0-only", "blocked license (BSD-2-Clause, AGPL-3.0-only)"),
        ("BSD-3-Clause; SSPL-1.0", "blocked license (BSD-3-Clause; SSPL-1.0)"),
        (
            "BSD-3-Clause / Custom-License",
            "manual license review required (BSD-3-Clause / Custom-License)",
        ),
        ("BSD-3-Clause-Clear", "manual license review required (BSD-3-Clause-Clear)"),
    ],
)
def test_audit_does_not_infer_bsd_from_a_partial_license_value(
    license_expression: str, expected_failure: str
) -> None:
    failures = audit_distributions(
        [FakeDistribution("partial-bsd", "1.0", license_expression)], set()
    )

    assert failures == [f"partial-bsd: {expected_failure}"]


def test_audit_blocks_a_gpl_license() -> None:
    failures = audit_distributions([FakeDistribution("copyleft", "1.0", "GPL-3.0-only")], set())

    assert failures == ["copyleft: blocked license (GPL-3.0-only)"]


def test_audit_requires_review_for_an_unknown_license() -> None:
    failures = audit_distributions([FakeDistribution("unknown", "1.0", "Custom-License")], set())

    assert failures == ["unknown: manual license review required (Custom-License)"]


def test_audit_accepts_an_exactly_matching_exception() -> None:
    failures = audit_distributions(
        [FakeDistribution("reviewed", "1.0", "PSF-2.0")],
        {("reviewed", "1.0", "PSF-2.0")},
    )

    assert failures == []


def test_audit_rejects_an_exception_with_a_different_version() -> None:
    failures = audit_distributions(
        [FakeDistribution("reviewed", "2.0", "PSF-2.0")],
        {("reviewed", "1.0", "PSF-2.0")},
    )

    assert failures == ["reviewed: manual license review required (PSF-2.0)"]


def test_audit_includes_a_development_distribution() -> None:
    failures = audit_distributions(
        [
            FakeDistribution("runtime-package", "1.0", "MIT"),
            FakeDistribution("development-tool", "1.0", "Unknown-Dev-License"),
        ],
        set(),
    )

    assert failures == ["development-tool: manual license review required (Unknown-Dev-License)"]
