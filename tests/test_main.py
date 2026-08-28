"""Tests for the __main__ loop: resilience and the health marker file."""

import types

import pytest

from coolify_cf_tunnel_sync import __main__ as main_mod
from coolify_cf_tunnel_sync.sync import SyncResult

REQUIRED_ENV = {
    "COOLIFY_URL": "https://coolify.example.com",
    "COOLIFY_TOKEN": "coolify-token",
    "CF_API_TOKEN": "cf-token",
    "CF_ACCOUNT_ID": "account-id",
    "CF_TUNNEL_ID": "tunnel-id",
    "POLL_INTERVAL": "1",
}


def test_loop_survives_failure_and_touches_marker_only_after_success(
    monkeypatch, tmp_path
):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    marker = tmp_path / "last_sync_ok"
    monkeypatch.setattr(main_mod, "LAST_SYNC_OK", marker)
    # Do not really sleep; patch only this module's reference to time.
    monkeypatch.setattr(
        main_mod, "time", types.SimpleNamespace(sleep=lambda s: None)
    )

    calls = 0

    def fake_run_sync(config, coolify, cloudflare):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")  # the loop must survive this
        if calls == 2:
            # The failed first cycle must not have touched the marker.
            assert not marker.exists()
            return SyncResult()
        # The successful second cycle must have touched it.
        assert marker.exists()
        raise KeyboardInterrupt  # break the infinite loop

    monkeypatch.setattr(main_mod, "run_sync", fake_run_sync)

    with pytest.raises(KeyboardInterrupt):
        main_mod.main()

    assert calls == 3
    assert marker.exists()
