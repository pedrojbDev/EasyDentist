from __future__ import annotations

from app.clinics.feature_flags import FeatureKey


def test_feature_key_registry_starts_empty() -> None:
    assert list(FeatureKey) == []
