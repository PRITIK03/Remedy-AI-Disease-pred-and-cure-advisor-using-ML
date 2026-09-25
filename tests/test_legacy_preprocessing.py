"""Tests for the legacy preprocessing/validation helpers in app.py."""

from __future__ import annotations

import pytest

from app import FEATURE_ORDER, parse_features


def _form(**overrides) -> dict[str, str]:
    base = {
        "age": "45", "sex": "1", "cp": "0", "trestbps": "120", "chol": "180",
        "fbs": "0", "restecg": "0", "thalach": "170", "exang": "0",
        "oldpeak": "0.5", "slope": "1", "ca": "0", "thal": "2",
    }
    base.update(overrides)
    return base


class TestParseFeaturesValid:
    def test_valid_form_parses_all_13_features(self):
        values = parse_features(_form())
        assert set(values.keys()) == set(FEATURE_ORDER)
        assert values["age"] == 45
        assert values["oldpeak"] == 0.5  # float cast
        assert isinstance(values["age"], int)

    def test_whitespace_is_stripped(self):
        values = parse_features(_form(age="  52 "))
        assert values["age"] == 52


class TestParseFeaturesInvalid:
    def test_missing_field_raises(self):
        form = _form()
        del form["chol"]
        with pytest.raises(ValueError, match="chol"):
            parse_features(form)

    def test_empty_field_raises(self):
        with pytest.raises(ValueError, match="required"):
            parse_features(_form(age=""))

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError, match="not a valid"):
            parse_features(_form(chol="abc"))

    def test_float_for_int_field_rejected(self):
        with pytest.raises(ValueError):
            parse_features(_form(age="45.5"))

    def test_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="between"):
            parse_features(_form(trestbps="999"))

    def test_negative_oldpeak_rejected(self):
        with pytest.raises(ValueError, match="between"):
            parse_features(_form(oldpeak="-0.1"))

    def test_multiple_errors_aggregated(self):
        with pytest.raises(ValueError) as excinfo:
            parse_features(_form(sex="5", ca="9"))
        assert "sex" in str(excinfo.value)
        assert "ca" in str(excinfo.value)

    def test_ca_allows_dataset_range_0_to_4(self):
        """HTML restricts ca to 0-3, but the model was trained on 0-4.

        Backend validation deliberately follows the model schema, not the
        legacy HTML limits (see docs/legacy-ml-baseline.md §3).
        """
        values = parse_features(_form(ca="4"))
        assert values["ca"] == 4

    def test_thal_allows_0(self):
        """Legacy HTML blocked thal=0; dataset encoding includes 0."""
        values = parse_features(_form(thal="0"))
        assert values["thal"] == 0
