"""Phase 9 production hardening: config guards, S3 storage, telemetry.

These are pure unit tests: no database, no network, no object store, and no
OpenTelemetry collector. The S3 provider is exercised through an injected fake
client so the tests never touch a real bucket or require boto3.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import Settings  # noqa: E402
from backend.app.storage.base import (  # noqa: E402
    StorageError,
    StorageFileNotFoundError,
)
from backend.app.storage.s3 import S3StorageProvider  # noqa: E402
from backend.app.telemetry import (  # noqa: E402
    ALLOWED_SPAN_ATTRIBUTES,
    scrub_url,
)

SECURE_KW = {
    "secret_key": "a" * 48,
    "cookie_secure": True,
    "cors_origins": "https://remedy.example",
    "log_level": "INFO",
}


# --------------------------------------------------------------------- #
# Production configuration guard
# --------------------------------------------------------------------- #
class TestProductionGuard:
    def test_healthy_production_config_is_accepted(self):
        Settings(app_env="production", storage_backend="local", **SECURE_KW).validate_production()

    @pytest.mark.parametrize(
        ("overrides", "expected_fragment"),
        [
            ({"secret_key": ""}, "SECRET_KEY"),
            ({"secret_key": "short"}, "32 characters"),
            ({"cookie_secure": False}, "COOKIE_SECURE"),
            ({"cors_origins": "*"}, "CORS_ORIGINS"),
            ({"cors_origins": ""}, "CORS_ORIGINS"),
            ({"log_level": "DEBUG"}, "LOG_LEVEL"),
        ],
    )
    def test_insecure_settings_are_refused(self, overrides, expected_fragment):
        kwargs = {**SECURE_KW, **overrides}
        with pytest.raises(RuntimeError) as exc:
            Settings(app_env="production", storage_backend="local", **kwargs).validate_production()
        assert expected_fragment in str(exc.value)

    def test_excessive_session_ttl_is_refused(self):
        # The field validator already caps this at 7 days, so the 24h
        # production rule is a second, independent barrier. It is exercised
        # here on a valid instance to prove the guard itself works.
        settings = Settings(app_env="production", storage_backend="local", **SECURE_KW)
        settings.session_ttl_seconds = 60 * 60 * 24 * 8
        with pytest.raises(RuntimeError, match="SESSION_TTL_SECONDS"):
            settings.validate_production()

    def test_s3_backend_requires_a_bucket(self):
        with pytest.raises(RuntimeError, match="S3_BUCKET"):
            Settings(app_env="production", storage_backend="s3", s3_bucket="", **SECURE_KW).validate_production()

    def test_guard_is_inert_outside_production(self):
        # Development must keep working with the permissive defaults.
        Settings(app_env="development", cookie_secure=False, cors_origins="*").validate_production()

    def test_unknown_storage_backend_is_rejected(self):
        with pytest.raises(ValueError, match="STORAGE_BACKEND"):
            Settings(storage_backend="gcs")

    def test_storage_backend_is_case_normalised(self):
        assert Settings(storage_backend=" S3 ").storage_backend == "s3"

    def test_runtime_warnings_never_contain_secret_values(self):
        warnings = Settings(
            app_env="production",
            storage_backend="local",
            **SECURE_KW,
        ).validate_runtime_services()
        joined = " ".join(warnings)
        assert joined  # something is reported
        assert "aaaa" not in joined  # the secret value itself
        assert "SECRET_KEY" not in joined


# --------------------------------------------------------------------- #
# S3 storage provider (fake client — no network, no boto3)
# --------------------------------------------------------------------- #
class FakeS3Client:
    """Minimal stand-in for boto3's S3 client."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[dict] = []

    def put_object(self, Bucket, Key, Body, **kwargs):  # noqa: N803
        self.objects[Key] = Body
        self.put_calls.append({"Bucket": Bucket, "Key": Key, **kwargs})

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise _client_error("NoSuchKey")
        return {"Body": _Body(self.objects[Key])}

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise _client_error("404")

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop(Key, None)

    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803
        return f"https://s3.test/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"


class _Body:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


def _client_error(code: str) -> Exception:
    exc = Exception(code)
    exc.response = {"Error": {"Code": code}}  # type: ignore[attr-defined]
    return exc


@pytest.fixture
def s3_provider():
    # A fake client and an explicit bucket are injected, so no boto3 import,
    # no credentials, and no network access are involved.
    return S3StorageProvider(client=FakeS3Client(), bucket="test-reports")


class TestS3Provider:
    def test_round_trip(self, s3_provider):
        s3_provider.save("u1/report.pdf", b"data")
        assert s3_provider.get("u1/report.pdf") == b"data"
        assert s3_provider.exists("u1/report.pdf") is True
        assert s3_provider.delete("u1/report.pdf") is True
        assert s3_provider.exists("u1/report.pdf") is False

    def test_save_returns_an_s3_uri(self, s3_provider):
        assert s3_provider.save("u1/a.pdf", b"x").startswith("s3://")

    def test_missing_key_raises_not_found(self, s3_provider):
        with pytest.raises(StorageFileNotFoundError):
            s3_provider.get("u1/nope.pdf")

    def test_delete_missing_key_is_false(self, s3_provider):
        assert s3_provider.delete("u1/nope.pdf") is False

    @pytest.mark.parametrize("key", ["../escape.pdf", "u1/../../escape.pdf", "", "/"])
    def test_traversal_and_empty_keys_are_rejected(self, s3_provider, key):
        with pytest.raises(StorageError):
            s3_provider.save(key, b"x")

    def test_leading_slash_is_normalised_not_treated_as_absolute(self, s3_provider):
        s3_provider.save("/u1/a.pdf", b"x")
        assert s3_provider.exists("u1/a.pdf") is True

    def test_backslashes_are_normalised(self, s3_provider):
        s3_provider.save("u1\\win.pdf", b"x")
        assert s3_provider.exists("u1/win.pdf") is True

    def test_client_errors_are_wrapped_without_leaking_details(self, s3_provider):
        def boom(**_kwargs):
            raise RuntimeError("connection to internal-host:9000 refused")

        s3_provider._client.put_object = boom
        with pytest.raises(StorageError) as exc:
            s3_provider.save("u1/a.pdf", b"x")
        # The message is generic; the underlying error is chained, not inlined.
        assert "internal-host" not in str(exc.value)

    def test_presigned_url_is_time_limited(self, s3_provider):
        url = s3_provider.presigned_url("u1/a.pdf")
        assert "expires=" in url


# --------------------------------------------------------------------- #
# Telemetry privacy
# --------------------------------------------------------------------- #
class TestTelemetryPrivacy:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("https://api.example.com/api/v1/reports", "/api/v1/reports"),
            ("/api/v1/reports?token=SECRET", "/api/v1/reports"),
            ("http://host:8000/health?api_key=abc", "/health"),
        ],
    )
    def test_scrub_url_drops_host_and_query(self, raw, expected):
        assert scrub_url(raw) == expected

    def test_allowlist_excludes_every_sensitive_attribute(self):
        for forbidden in ("http.request.header", "db.statement", "enduser.id", "url.query"):
            assert forbidden not in ALLOWED_SPAN_ATTRIBUTES

    def test_allowlist_only_holds_operational_attributes(self):
        assert ALLOWED_SPAN_ATTRIBUTES == {
            "http.request.method",
            "http.response.status_code",
            "http.route",
            "url.path",
            "server.address",
            "error",
            "error.type",
        }

