"""Tests for env-var config loading."""

import pytest

from coolify_cf_tunnel_sync.config import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TARGET_SERVICE,
    ConfigError,
    load_config,
)

REQUIRED_ENV = {
    "COOLIFY_URL": "https://coolify.example.com/",
    "COOLIFY_TOKEN": "coolify-token",
    "CF_API_TOKEN": "cf-token",
    "CF_ACCOUNT_ID": "account-id",
    "CF_TUNNEL_ID": "tunnel-id",
}


def test_defaults():
    cfg = load_config(REQUIRED_ENV)
    assert cfg.coolify_url == "https://coolify.example.com"  # slash stripped
    assert cfg.target_service == DEFAULT_TARGET_SERVICE
    assert cfg.poll_interval == DEFAULT_POLL_INTERVAL
    assert cfg.sync_dns is False
    assert cfg.dry_run is False
    assert cfg.cf_zone_id is None
    assert cfg.exclude_hostnames == frozenset()


@pytest.mark.parametrize("missing", list(REQUIRED_ENV))
def test_missing_required_var_raises(missing):
    env = {k: v for k, v in REQUIRED_ENV.items() if k != missing}
    with pytest.raises(ConfigError, match=missing):
        load_config(env)


def test_empty_required_var_raises():
    env = {**REQUIRED_ENV, "COOLIFY_TOKEN": "  "}
    with pytest.raises(ConfigError, match="COOLIFY_TOKEN"):
        load_config(env)


def test_bool_parsing():
    env = {**REQUIRED_ENV, "DRY_RUN": "true", "SYNC_DNS": "1",
           "CF_ZONE_ID": "zone"}
    cfg = load_config(env)
    assert cfg.dry_run is True
    assert cfg.sync_dns is True
    env = {**REQUIRED_ENV, "DRY_RUN": "no", "SYNC_DNS": "0"}
    assert load_config(env).dry_run is False


def test_bool_rejects_unrecognized_values():
    env = {**REQUIRED_ENV, "DRY_RUN": "ture"}
    with pytest.raises(ConfigError, match="DRY_RUN"):
        load_config(env)


def test_coolify_url_must_have_a_scheme():
    env = {**REQUIRED_ENV, "COOLIFY_URL": "coolify.example.com"}
    with pytest.raises(ConfigError, match="COOLIFY_URL"):
        load_config(env)


def test_sync_dns_requires_zone_id():
    env = {**REQUIRED_ENV, "SYNC_DNS": "true"}
    with pytest.raises(ConfigError, match="CF_ZONE_ID"):
        load_config(env)


def test_poll_interval_must_be_a_positive_number():
    with pytest.raises(ConfigError, match="POLL_INTERVAL"):
        load_config({**REQUIRED_ENV, "POLL_INTERVAL": "abc"})
    with pytest.raises(ConfigError, match="POLL_INTERVAL"):
        load_config({**REQUIRED_ENV, "POLL_INTERVAL": "0"})
    cfg = load_config({**REQUIRED_ENV, "POLL_INTERVAL": "30"})
    assert cfg.poll_interval == 30


def test_exclude_hostnames_parsing():
    env = {**REQUIRED_ENV,
           "EXCLUDE_HOSTNAMES": " A.example.com ,b.example.com,,"}
    cfg = load_config(env)
    assert cfg.exclude_hostnames == frozenset({"a.example.com", "b.example.com"})
