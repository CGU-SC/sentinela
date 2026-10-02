"""Update-service tests use real Ed25519 signatures and temporary files, never network."""

import base64
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.exceptions import InvalidSignature

from api.services import system_update as updates


def _manifest(*, latest="2.1.0", minimum="1.0.0", blocked=False):
    return {
        "schema_version": 1,
        "product": "sentinela",
        "channel": "stable",
        "latest_version": latest,
        "minimum_supported_version": minimum,
        "published_at": "2026-09-01T10:00:00Z",
        "download_url": "https://example.test/Sentinela.exe",
        "release_notes_url": "https://example.test/release",
        "execution_policy": {
            "blocked_execution": blocked,
            "block_title": "Execução suspensa",
            "block_message": "Atualize antes de prosseguir.",
            "blocked_since": "2026-09-01T10:00:00Z" if blocked else None,
        },
    }


def _signed(private_key, data=None):
    raw = json.dumps(data or _manifest(), separators=(",", ":")).encode("utf-8")
    signature = base64.b64encode(private_key.sign(raw))
    return raw, signature


@pytest.fixture
def update_environment(monkeypatch, tmp_path):
    cache_dir = tmp_path / "updates"
    cache_dir.mkdir()
    key = Ed25519PrivateKey.generate()
    public_key_path = tmp_path / "update_manifest_public_key.pem"
    public_key_path.write_bytes(key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    version_path = tmp_path / "version.json"
    version_path.write_text('{"version": "2.0.0"}', encoding="utf-8")
    monkeypatch.setattr(updates, "_cache_dir", lambda: cache_dir)
    monkeypatch.setattr(updates, "_public_key_path", lambda: public_key_path)
    monkeypatch.setattr(updates, "_version_json_path", lambda: version_path)
    monkeypatch.setattr(updates, "_cached_status", None)
    updates._download_state.update("idle")
    return SimpleNamespace(
        root=tmp_path,
        cache=cache_dir,
        key=key,
        public_key=public_key_path,
        version=version_path,
    )


def test_version_paths_and_current_executable_require_desktop_mode(monkeypatch, update_environment):
    env = update_environment
    assert updates.get_current_version() == "2.0.0"
    assert updates._public_key_path() == env.public_key
    assert updates._version_json_path() == env.version

    env.version.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError, match="version.json"):
        updates.get_current_version()
    env.version.write_text('{"version": "2.0.0"}', encoding="utf-8")

    monkeypatch.setattr(updates.sys, "frozen", False, raising=False)
    with pytest.raises(RuntimeError, match="não é suportado fora do modo Desktop"):
        updates._current_exe_path()
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.sys, "executable", str(env.root / "Sentinela.exe"))
    assert updates._current_exe_path() == env.root / "Sentinela.exe"


def test_path_helpers_select_meipass_and_create_local_update_directory(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    assert updates._public_key_path() == Path(updates.__file__).parent.parent.parent / "data" / "update_manifest_public_key.pem"
    assert updates._version_json_path() == Path(updates.__file__).parent.parent.parent.parent / "version.json"
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.sys, "_MEIPASS", str(bundle), raising=False)
    assert updates._public_key_path() == bundle / "backend" / "data" / "update_manifest_public_key.pem"
    assert updates._version_json_path() == bundle / "version.json"

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    cache = updates._cache_dir()
    download_dir = updates._updates_tmp_dir()
    assert cache == tmp_path / "appdata" / "Sentinela" / "updates"
    assert download_dir == cache
    assert cache.is_dir()


def test_manifest_validation_enforces_schema_product_channel_and_versions():
    raw, _ = _signed(Ed25519PrivateKey.generate())
    parsed = updates._validate_manifest(raw)
    assert parsed.product == "sentinela"
    assert parsed.latest_version == "2.1.0"
    assert str(parsed.download_url) == "https://example.test/Sentinela.exe"

    invalid_json = b"not json"
    with pytest.raises(ValueError, match="JSON válido"):
        updates._validate_manifest(invalid_json)
    for field, value, message in [
        ("schema_version", 2, "schema_version inesperado"),
        ("product", "other", "product inesperado"),
        ("channel", "beta", "channel inesperado"),
        ("latest_version", "", "Campo obrigatório ausente"),
        ("minimum_supported_version", "latest", "não é SemVer válido"),
    ]:
        data = _manifest()
        data[field] = value
        with pytest.raises(ValueError, match=message):
            updates._validate_manifest(json.dumps(data).encode())


def test_signature_verification_accepts_ed25519_and_rejects_invalid_input(monkeypatch, update_environment):
    env = update_environment
    raw, signature = _signed(env.key)
    updates._verify_signature(raw, signature)

    with pytest.raises(InvalidSignature):
        updates._verify_signature(raw + b"tampered", signature)
    with pytest.raises(ValueError, match="Base64 inválida"):
        updates._verify_signature(raw, b"x")

    rsa_path = env.root / "rsa.pem"
    rsa_key = generate_private_key(public_exponent=65537, key_size=2048)
    rsa_path.write_bytes(rsa_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    monkeypatch.setattr(updates, "_public_key_path", lambda: rsa_path)
    with pytest.raises(ValueError, match="não é do tipo Ed25519"):
        updates._load_public_key()


def test_cache_reads_empty_and_corrupt_state_and_writes_signed_values_atomically(update_environment):
    env = update_environment
    assert updates._read_cache() == (None, None)
    assert updates._read_cache_state() == {}
    (env.cache / "state.json").write_text("{broken", encoding="utf-8")
    assert updates._read_cache_state() == {}

    raw, signature = _signed(env.key)
    updates._write_cache_atomic(raw, signature)
    assert updates._read_cache() == (raw, signature)
    state = updates._read_cache_state()
    assert state["source_url"] == updates.MANIFEST_URL
    assert datetime.fromisoformat(state["checked_at"]).tzinfo is not None
    assert not list(env.cache.glob("*.tmp"))


def test_atomic_cache_write_preserves_previous_cache_and_cleans_temp_files(monkeypatch, update_environment):
    env = update_environment
    original, signature = _signed(env.key)
    updates._write_cache_atomic(original, signature)
    monkeypatch.setattr(updates, "_verify_signature", Mock(side_effect=InvalidSignature("bad signature")))

    with pytest.raises(InvalidSignature):
        updates._write_cache_atomic(b"replacement", b"invalid")

    assert updates._read_cache() == (original, signature)
    assert not list(env.cache.glob("*.tmp"))


@pytest.mark.parametrize(
    ("current", "latest", "minimum", "expected"),
    [("1.0.0", "2.0.0", "1.5.0", "update_required"),
     ("1.5.0", "2.0.0", "1.5.0", "update_available"),
     ("2.0.0", "2.0.0", "1.0.0", "current")],
)
def test_semver_status_comparison(current, latest, minimum, expected):
    assert updates._compare_versions(current, latest, minimum) == expected


def test_manifest_status_prioritizes_signed_block_and_formats_user_messages():
    current = updates._validate_manifest(json.dumps(_manifest()).encode())
    blocked = updates._validate_manifest(json.dumps(_manifest(blocked=True)).encode())
    assert updates._manifest_status("2.0.0", current) == "update_available"
    assert updates._manifest_status("2.0.0", blocked) == "execution_blocked"
    assert updates._manifest_message("execution_blocked", blocked) == "Atualize antes de prosseguir."
    assert updates._manifest_message("current", current) == "Sistema atualizado."
    assert updates._manifest_message("update_available", current) == "Nova versão disponível: 2.1.0."
    assert "Versão mínima exigida: 1.0.0" in updates._manifest_message("update_required", current)
    assert "verificação offline" in updates._manifest_message("update_required", current, offline=True)
    assert updates._manifest_message("offline_cached", current) == "Verificação offline. Usando último manifesto validado."
    assert "Continuando sem verificação" in updates._manifest_message("verification_unavailable", current)


class _FakeResponse:
    def __init__(self, content: bytes, error=None):
        self.content = content
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error


def test_fetch_remote_uses_expected_urls_and_rejects_oversized_or_failed_responses(monkeypatch):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))
            self.responses = [_FakeResponse(b"manifest"), _FakeResponse(b"signature")]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url):
            calls.append(("get", url))
            return self.responses.pop(0)

    monkeypatch.setattr(updates.httpx, "Client", Client)
    assert updates._fetch_remote() == (b"manifest", b"signature")
    assert calls[0][1] == {"timeout": updates.REQUEST_TIMEOUT, "follow_redirects": True}
    assert [item[1] for item in calls if item[0] == "get"] == [updates.MANIFEST_URL, updates.SIGNATURE_URL]

    monkeypatch.setattr(updates.httpx, "Client", lambda **_kwargs: _FakeHttpClient([_FakeResponse(b"x" * (updates.MAX_MANIFEST_BYTES + 1))]))
    with pytest.raises(ValueError, match="Manifesto remoto excede"):
        updates._fetch_remote()
    monkeypatch.setattr(updates.httpx, "Client", lambda **_kwargs: _FakeHttpClient([_FakeResponse(b"ok"), _FakeResponse(b"x" * (updates.MAX_SIG_BYTES + 1))]))
    with pytest.raises(ValueError, match="Assinatura remota excede"):
        updates._fetch_remote()
    monkeypatch.setattr(updates.httpx, "Client", lambda **_kwargs: _FakeHttpClient([_FakeResponse(b"", httpx.HTTPStatusError("404", request=Mock(), response=Mock()))]))
    with pytest.raises(httpx.HTTPStatusError):
        updates._fetch_remote()


class _FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, _url):
        return self.responses.pop(0)


def test_check_for_updates_accepts_remote_signed_manifest_and_updates_cache(monkeypatch, update_environment):
    env = update_environment
    raw, signature = _signed(env.key, _manifest(latest="2.3.0", minimum="1.5.0"))
    monkeypatch.setattr(updates, "_fetch_remote", lambda: (raw, signature))

    result = updates.check_for_updates()

    assert result.status == "update_available"
    assert result.source == "remote"
    assert result.latest_version == "2.3.0"
    assert result.checked_at is not None
    assert updates.get_cached_status() == result
    assert updates._read_cache() == (raw, signature)


@pytest.mark.parametrize(
    ("version", "manifest_data", "expected_status"),
    [
        ("2.0.0", _manifest(latest="2.1.0", minimum="1.0.0"), "offline_cached"),
        ("1.0.0", _manifest(latest="2.1.0", minimum="1.5.0"), "update_required"),
        ("2.0.0", _manifest(latest="2.1.0", minimum="1.0.0", blocked=True), "execution_blocked"),
    ],
)
def test_check_for_updates_uses_verified_cache_when_remote_fails(
    monkeypatch, update_environment, version, manifest_data, expected_status
):
    env = update_environment
    env.version.write_text(json.dumps({"version": version}), encoding="utf-8")
    raw, signature = _signed(env.key, manifest_data)
    updates._write_cache_atomic(raw, signature)
    monkeypatch.setattr(updates, "_fetch_remote", Mock(side_effect=OSError("network unavailable")))

    result = updates.check_for_updates()

    assert result.status == expected_status
    assert result.source == "cache"
    assert result.latest_version == manifest_data["latest_version"]
    if expected_status == "update_required":
        assert "verificação offline" in result.message
    if expected_status == "execution_blocked":
        assert result.message == manifest_data["execution_policy"]["block_message"]


def test_check_for_updates_rejects_invalid_cache_and_reports_unavailable(monkeypatch, update_environment):
    env = update_environment
    raw, signature = _signed(env.key)
    updates._cache_manifest_path().write_bytes(raw)
    updates._cache_sig_path().write_bytes(base64.b64encode(b"wrong signature"))
    monkeypatch.setattr(updates, "_fetch_remote", Mock(side_effect=OSError("offline")))

    result = updates.check_for_updates()

    assert result.status == "verification_unavailable"
    assert result.source == "none"
    assert result.latest_version is None
    assert result.message.endswith("Continuando sem verificação.")
    assert updates.get_cached_status() == result


def test_check_for_updates_ignores_invalid_cached_timestamp(monkeypatch, update_environment):
    env = update_environment
    (env.cache / "state.json").write_text('{"checked_at":"not-a-timestamp"}', encoding="utf-8")
    monkeypatch.setattr(updates, "_fetch_remote", Mock(side_effect=OSError("offline")))

    result = updates.check_for_updates()

    assert result.status == "verification_unavailable"
    assert result.checked_at is None


def test_initialize_update_check_sets_pending_or_cached_status(update_environment):
    env = update_environment
    updates.initialize_update_check()
    pending = updates.get_cached_status()
    assert pending.status == "verification_unavailable"
    assert pending.message == "Verificação de atualização pendente."

    raw, signature = _signed(env.key, _manifest(latest="2.4.0", minimum="1.0.0"))
    updates._write_cache_atomic(raw, signature)
    updates.initialize_update_check()
    cached = updates.get_cached_status()
    assert cached.status == "update_available"
    assert cached.source == "cache"
    assert cached.latest_version == "2.4.0"


def test_initialize_update_check_ignores_corrupt_cache_and_bad_timestamp(update_environment):
    env = update_environment
    env.cache.joinpath("manifest.json").write_bytes(b"invalid")
    env.cache.joinpath("manifest.sig").write_bytes(b"invalid")
    env.cache.joinpath("state.json").write_text('{"checked_at":"invalid"}', encoding="utf-8")

    updates.initialize_update_check()

    result = updates.get_cached_status()
    assert result.status == "verification_unavailable"
    assert result.source == "none"
    assert result.checked_at is None


def test_download_state_rounds_progress_and_clears_error():
    state = updates._DownloadState()
    state.update("error", progress=0.123456, error="timeout")
    assert state.snapshot() == {"status": "error", "progress": 0.1235, "error": "timeout"}
    state.update("idle")
    assert state.snapshot() == {"status": "idle", "progress": 0.0, "error": None}
    updates._download_state.update("applying", progress=0.25)
    assert updates.get_download_state() == {"status": "applying", "progress": 0.25, "error": None}


def test_download_url_resolution_and_ps1_generation(update_environment):
    env = update_environment
    assert updates._resolve_github_download_url("https://github.com/cgu-sc/sentinela/releases/tag/v2.1.0/") == (
        "https://github.com/cgu-sc/sentinela/releases/download/v2.1.0/Sentinela.exe"
    )
    direct = "https://mirror.example/Sentinela.exe"
    assert updates._resolve_github_download_url(direct) == direct

    exe_path = env.root / "Sentinela.exe"
    tmp_path = env.root / "sentinela_update.exe.tmp"
    ps1 = updates._write_update_ps1(exe_path, tmp_path)
    content = ps1.read_text(encoding="utf-8-sig")
    assert ps1.name == "sentinela_update.ps1"
    assert "$proc_name = 'Sentinela'" in content
    assert str(tmp_path) in content
    assert "Copy-Item" in content


def test_download_worker_tracks_chunks_and_cleans_partial_file_on_error(monkeypatch, update_environment):
    env = update_environment
    exe_path = env.root / "Sentinela.exe"
    monkeypatch.setattr(updates, "_current_exe_path", lambda: exe_path)

    class StreamResponse:
        headers = {"content-length": "4"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size):
            assert chunk_size == updates.DOWNLOAD_CHUNK_SIZE
            yield b"ab"
            yield b"cd"

    class StreamingClient:
        def __init__(self, **kwargs):
            assert kwargs == {"timeout": updates.DOWNLOAD_TIMEOUT, "follow_redirects": True}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def stream(self, method, url):
            assert method == "GET"
            assert url.endswith("/download/v2.1.0/Sentinela.exe")
            return StreamResponse()

    monkeypatch.setattr(updates.httpx, "Client", StreamingClient)
    updates._do_download_and_apply("https://github.com/cgu-sc/sentinela/releases/tag/v2.1.0")
    downloaded = env.root / "sentinela_update.exe.tmp"
    assert downloaded.read_bytes() == b"abcd"
    assert updates.get_download_state() == {"status": "done", "progress": 1.0, "error": None}

    class FailedStream(StreamResponse):
        def raise_for_status(self):
            raise OSError("stream broken")

    class FailedClient(StreamingClient):
        def stream(self, *_args):
            return FailedStream()

    monkeypatch.setattr(updates.httpx, "Client", FailedClient)
    updates._do_download_and_apply("https://example.test/Sentinela.exe")
    assert not downloaded.exists()
    assert updates.get_download_state() == {"status": "error", "progress": 0.0, "error": "stream broken"}


def test_download_start_requires_frozen_mode_and_rejects_in_progress(monkeypatch, update_environment):
    monkeypatch.setattr(updates.sys, "frozen", False, raising=False)
    with pytest.raises(RuntimeError, match="não é suportado fora do modo Desktop"):
        updates.download_and_apply_update("https://example.test/app.exe")

    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    updates._download_state.update("downloading", progress=0.4)
    with pytest.raises(RuntimeError, match="Download já em andamento"):
        updates.download_and_apply_update("https://example.test/app.exe")

    started = []

    class ThreadStub:
        def __init__(self, **kwargs):
            started.append(kwargs)

        def start(self):
            started[-1]["started"] = True

    monkeypatch.setattr(updates, "threading", SimpleNamespace(Thread=ThreadStub))
    updates._download_state.update("error", error="previous failure")
    updates.download_and_apply_update("https://example.test/app.exe")
    assert started == [{
        "target": updates._do_download_and_apply,
        "args": ("https://example.test/app.exe",),
        "daemon": True,
        "name": "sentinela-auto-update",
        "started": True,
    }]
    assert updates.get_download_state() == {"status": "idle", "progress": 0.0, "error": None}


def test_updater_discovery_uses_bundle_then_install_then_development_paths(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    app_dir = tmp_path / "app"
    bundle.mkdir()
    app_dir.mkdir()
    bundled = bundle / "SentinelaUpdater.exe"
    installed = app_dir / "SentinelaUpdater.exe"
    bundled.write_bytes(b"bundle")
    installed.write_bytes(b"installed")
    exe = app_dir / "Sentinela.exe"
    monkeypatch.setattr(updates.sys, "_MEIPASS", str(bundle), raising=False)
    assert updates._find_updater_exe(exe) == bundled
    bundled.unlink()
    assert updates._find_updater_exe(exe) == installed
    installed.unlink()
    dev = tmp_path / "dist" / "SentinelaUpdater.exe"
    dev.parent.mkdir()
    dev.write_bytes(b"dev")
    monkeypatch.chdir(tmp_path)
    assert updates._find_updater_exe(exe).resolve() == dev
    dev.unlink()
    assert updates._find_updater_exe(exe) is None


def test_apply_update_launches_bundled_updater_and_exits(monkeypatch, update_environment):
    env = update_environment
    exe_path = env.root / "Sentinela.exe"
    tmp_path = env.root / "sentinela_update.exe.tmp"
    updater_source = env.root / "bundle" / "SentinelaUpdater.exe"
    updater_source.parent.mkdir()
    updater_source.write_bytes(b"updater")
    tmp_path.write_bytes(b"new executable")
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.sys, "executable", str(exe_path))
    monkeypatch.setattr(updates.sys, "_MEIPASS", str(updater_source.parent), raising=False)
    popen = Mock()
    monkeypatch.setattr(updates.subprocess, "Popen", popen)
    monkeypatch.setattr(updates.time, "sleep", Mock())
    monkeypatch.setattr(updates.sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))

    with pytest.raises(SystemExit) as exited:
        updates.apply_update()

    assert exited.value.code == 0
    updater_copy = env.root / "SentinelaUpdater.exe"
    assert updater_copy.read_bytes() == b"updater"
    args, kwargs = popen.call_args
    assert args[0] == [str(updater_copy), "--exe", str(exe_path), "--tmp", str(tmp_path)]
    assert kwargs["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
    assert kwargs["close_fds"] is True


def test_apply_update_rejects_missing_download_and_uses_powershell_fallback(monkeypatch, update_environment):
    env = update_environment
    exe_path = env.root / "Sentinela.exe"
    tmp_path = env.root / "sentinela_update.exe.tmp"
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.sys, "executable", str(exe_path))
    with pytest.raises(RuntimeError, match="Arquivo de atualização não encontrado"):
        updates.apply_update()

    tmp_path.write_bytes(b"new executable")
    monkeypatch.setattr(updates, "_find_updater_exe", lambda _exe: None)
    popen = Mock()
    monkeypatch.setattr(updates.subprocess, "Popen", popen)
    monkeypatch.setattr(updates.time, "sleep", Mock())
    monkeypatch.setattr(updates.sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    with pytest.raises(SystemExit):
        updates.apply_update()
    ps1 = env.root / "sentinela_update.ps1"
    assert ps1.exists()
    args, kwargs = popen.call_args
    assert args[0][:5] == ["powershell.exe", "-WindowStyle", "Normal", "-ExecutionPolicy", "Bypass"]
    assert args[0][-2:] == ["-File", str(ps1)]
    assert kwargs["creationflags"] == subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
    assert kwargs["close_fds"] is True


def test_cancel_update_removes_pending_files_and_resets_state(monkeypatch, update_environment):
    env = update_environment
    exe_path = env.root / "Sentinela.exe"
    (env.root / "sentinela_update.exe.tmp").write_bytes(b"pending")
    (env.root / "sentinela_update.ps1").write_text("pending", encoding="utf-8")
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.sys, "executable", str(exe_path))
    updates._download_state.update("done", progress=1.0)

    updates.cancel_update()

    assert not (env.root / "sentinela_update.exe.tmp").exists()
    assert not (env.root / "sentinela_update.ps1").exists()
    assert updates.get_download_state() == {"status": "idle", "progress": 0.0, "error": None}
