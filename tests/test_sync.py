"""Tests for the reconciler logic and one full sync cycle."""

import json

import httpx
import pytest
import respx

from coolify_cf_tunnel_sync.cloudflare import (
    API_BASE,
    CloudflareClient,
    CloudflareError,
)
from coolify_cf_tunnel_sync.config import Config
from coolify_cf_tunnel_sync.coolify import CoolifyClient
from coolify_cf_tunnel_sync.sync import (
    build_rule,
    insert_before_catch_all,
    is_covered_by_wildcard,
    run_sync,
)

COOLIFY_URL = "https://coolify.example.com"
ACCOUNT = "acc-1"
TUNNEL = "tun-1"
ZONE = "zone-1"
APPS_URL = f"{COOLIFY_URL}/api/v1/applications"
CONFIG_URL = (
    f"{API_BASE}/client/v4/accounts/{ACCOUNT}"
    f"/cfd_tunnel/{TUNNEL}/configurations"
)
DNS_URL = f"{API_BASE}/client/v4/zones/{ZONE}/dns_records"

CATCH_ALL = {"service": "http_status:404"}


# --- wildcard coverage -------------------------------------------------


def test_wildcard_covers_one_extra_label():
    assert is_covered_by_wildcard("app.example.com", "*.example.com") is True


def test_wildcard_does_not_cover_deeper_names():
    assert (
        is_covered_by_wildcard("deep.app.example.com", "*.example.com") is False
    )


def test_wildcard_does_not_cover_apex():
    assert is_covered_by_wildcard("example.com", "*.example.com") is False


def test_wildcard_does_not_cover_other_domains():
    assert is_covered_by_wildcard("app.other.com", "*.example.com") is False


def test_non_wildcard_pattern_covers_nothing():
    assert is_covered_by_wildcard("app.example.com", "app.example.com") is False


# --- rule shape and ordering -------------------------------------------


def test_build_rule_shape_has_no_connect_timeout():
    rule = build_rule("app.example.com", "http://localhost:8180")
    assert rule == {
        "hostname": "app.example.com",
        "service": "http://localhost:8180",
        "originRequest": {
            "noTLSVerify": True,
            "disableChunkedEncoding": True,
        },
    }
    assert "connectTimeout" not in rule["originRequest"]


def test_insert_before_catch_all():
    existing = [{"hostname": "old.example.com", "service": "http://x"}, CATCH_ALL]
    new_rules = [{"hostname": "new.example.com", "service": "http://y"}]
    merged = insert_before_catch_all(existing, new_rules)
    assert merged[-1] == CATCH_ALL
    assert merged == [
        {"hostname": "old.example.com", "service": "http://x"},
        {"hostname": "new.example.com", "service": "http://y"},
        CATCH_ALL,
    ]
    # The input list is not changed in place.
    assert len(existing) == 2


def test_insert_appends_when_no_catch_all():
    existing = [{"hostname": "old.example.com", "service": "http://x"}]
    new_rules = [{"hostname": "new.example.com", "service": "http://y"}]
    merged = insert_before_catch_all(existing, new_rules)
    assert merged == existing + new_rules


# --- full sync cycle ----------------------------------------------------


def make_config(**overrides) -> Config:
    base = {
        "coolify_url": COOLIFY_URL,
        "coolify_token": "ct",
        "cf_api_token": "cf",
        "cf_account_id": ACCOUNT,
        "cf_tunnel_id": TUNNEL,
    }
    return Config(**{**base, **overrides})


def mock_apps(domains_fqdn: str):
    respx.get(APPS_URL).mock(
        return_value=httpx.Response(200, json=[{"fqdn": domains_fqdn}])
    )


def mock_config(ingress):
    respx.get(CONFIG_URL).mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"config": {"ingress": ingress}}}
        )
    )


@respx.mock
def test_run_sync_adds_missing_routes_before_catch_all():
    existing = [
        {
            "hostname": "old.example.com",
            "service": "http://192.168.1.1:9000",
            "originRequest": {"connectTimeout": "30s"},
        },
        CATCH_ALL,
    ]
    old_rule_before = json.dumps(existing[0], sort_keys=True)

    mock_apps("https://new.example.com, https://old.example.com")
    mock_config(existing)
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        result = run_sync(make_config(), coolify, cloudflare)

    assert result.added == ["new.example.com"]
    assert result.present == ["old.example.com"]

    sent = json.loads(put.calls[0].request.content)["config"]["ingress"]
    # Catch-all is still last.
    assert sent[-1] == CATCH_ALL
    assert sent[1]["hostname"] == "new.example.com"
    # The pre-existing rule went out byte-identical (additive only).
    assert json.dumps(sent[0], sort_keys=True) == old_rule_before
    # No new rule ever carries connectTimeout.
    for rule in sent[1:-1]:
        assert "connectTimeout" not in rule.get("originRequest", {})


@respx.mock
def test_run_sync_skips_wildcard_covered_hostnames():
    mock_apps("https://app.example.com, https://deep.app.example.com")
    mock_config([{"hostname": "*.example.com", "service": "http://x"}, CATCH_ALL])
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        result = run_sync(make_config(), coolify, cloudflare)

    # app.example.com is covered; deep.app.example.com is not.
    assert result.covered_by_wildcard == ["app.example.com"]
    assert result.added == ["deep.app.example.com"]
    sent = json.loads(put.calls[0].request.content)["config"]["ingress"]
    assert [r.get("hostname") for r in sent] == [
        "*.example.com",
        "deep.app.example.com",
        None,
    ]


@respx.mock
def test_run_sync_honors_exclude_list():
    mock_apps("https://skip.example.com, https://keep.example.com")
    mock_config([CATCH_ALL])
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        result = run_sync(
            make_config(exclude_hostnames=frozenset({"skip.example.com"})),
            coolify,
            cloudflare,
        )

    assert result.excluded == ["skip.example.com"]
    assert result.added == ["keep.example.com"]
    sent = json.loads(put.calls[0].request.content)["config"]["ingress"]
    assert [r.get("hostname") for r in sent] == ["keep.example.com", None]


@respx.mock
def test_dry_run_makes_no_put():
    mock_apps("https://new.example.com")
    mock_config([CATCH_ALL])
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        result = run_sync(make_config(dry_run=True), coolify, cloudflare)

    assert result.dry_run is True
    assert result.added == ["new.example.com"]
    assert not put.called


@respx.mock
def test_nothing_to_do_makes_no_put():
    mock_apps("https://old.example.com")
    mock_config([{"hostname": "old.example.com", "service": "http://x"}, CATCH_ALL])
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        result = run_sync(make_config(), coolify, cloudflare)

    assert result.added == []
    assert not put.called


@respx.mock
def test_dns_sync_creates_cnames_for_new_routes():
    mock_apps("https://new.example.com")
    mock_config([CATCH_ALL])
    respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )
    respx.get(DNS_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    post = respx.post(DNS_URL).mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"id": "r1"}}
        )
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL, zone_id=ZONE) as cloudflare,
    ):
        result = run_sync(
            make_config(sync_dns=True, cf_zone_id=ZONE), coolify, cloudflare
        )

    assert result.dns_created == ["new.example.com"]
    assert post.called


@respx.mock
def test_dns_sync_off_makes_no_dns_calls():
    mock_apps("https://new.example.com")
    mock_config([CATCH_ALL])
    respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )
    dns_get = respx.get(DNS_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    dns_post = respx.post(DNS_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        result = run_sync(make_config(sync_dns=False), coolify, cloudflare)

    assert result.dns_created == []
    assert not dns_get.called
    assert not dns_post.called


@respx.mock
def test_dry_run_with_dns_makes_no_writes_at_all():
    mock_apps("https://new.example.com")
    mock_config([CATCH_ALL])
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )
    dns_post = respx.post(DNS_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL, zone_id=ZONE) as cloudflare,
    ):
        result = run_sync(
            make_config(dry_run=True, sync_dns=True, cf_zone_id=ZONE),
            coolify,
            cloudflare,
        )

    assert result.added == ["new.example.com"]
    assert not put.called
    assert not dns_post.called


# --- case-insensitive matching against the tunnel config -----------------


@respx.mock
def test_mixed_case_existing_hostname_is_not_duplicated():
    mock_apps("https://app.example.com")
    mock_config(
        [{"hostname": "APP.Example.com", "service": "http://x"}, CATCH_ALL]
    )
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        result = run_sync(make_config(), coolify, cloudflare)

    assert result.added == []
    assert result.present == ["app.example.com"]
    assert not put.called


@respx.mock
def test_mixed_case_wildcard_still_covers():
    mock_apps("https://app.example.com")
    mock_config([{"hostname": "*.Example.com", "service": "http://x"}, CATCH_ALL])
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        result = run_sync(make_config(), coolify, cloudflare)

    assert result.added == []
    assert result.covered_by_wildcard == ["app.example.com"]
    assert not put.called


# --- multi-cycle behaviour -------------------------------------------------


@respx.mock
def test_second_cycle_with_same_data_makes_no_put():
    """Idempotent: syncing the same state twice issues exactly one PUT."""
    mock_apps("https://new.example.com")
    added_rule = build_rule("new.example.com", "http://localhost:8180")
    respx.get(CONFIG_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {"config": {"ingress": [CATCH_ALL]}},
                },
            ),
            httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "config": {"ingress": [added_rule, CATCH_ALL]}
                    },
                },
            ),
        ]
    )
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL) as cloudflare,
    ):
        first = run_sync(make_config(), coolify, cloudflare)
        second = run_sync(make_config(), coolify, cloudflare)

    assert first.added == ["new.example.com"]
    assert second.added == []
    assert second.present == ["new.example.com"]
    assert len(put.calls) == 1


@respx.mock
def test_dns_cname_is_retried_after_partial_failure():
    """Cycle 1: route PUT ok, CNAME POST fails. Cycle 2: route already in
    the tunnel, so no PUT happens — but the missing CNAME must be retried."""
    mock_apps("https://new.example.com")
    added_rule = build_rule("new.example.com", "http://localhost:8180")
    respx.get(CONFIG_URL).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {"config": {"ingress": [CATCH_ALL]}},
                },
            ),
            httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "config": {"ingress": [added_rule, CATCH_ALL]}
                    },
                },
            ),
        ]
    )
    put = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )
    respx.get(DNS_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    dns_post = respx.post(DNS_URL).mock(
        side_effect=[
            httpx.Response(
                400,
                json={
                    "success": False,
                    "errors": [{"code": 81053, "message": "record exists"}],
                },
            ),
            httpx.Response(
                200, json={"success": True, "result": {"id": "r1"}}
            ),
        ]
    )

    with (
        CoolifyClient(COOLIFY_URL, "ct") as coolify,
        CloudflareClient("cf", ACCOUNT, TUNNEL, zone_id=ZONE) as cloudflare,
    ):
        with pytest.raises(CloudflareError):
            run_sync(
                make_config(sync_dns=True, cf_zone_id=ZONE),
                coolify,
                cloudflare,
            )
        second = run_sync(
            make_config(sync_dns=True, cf_zone_id=ZONE), coolify, cloudflare
        )

    # The route was written once, never again.
    assert len(put.calls) == 1
    # The CNAME POST failed once, then was retried and succeeded.
    assert len(dns_post.calls) == 2
    assert second.added == []
    assert second.present == ["new.example.com"]
    assert second.dns_created == ["new.example.com"]
