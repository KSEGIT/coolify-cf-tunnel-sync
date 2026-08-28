"""Tests for the Cloudflare API client."""

import httpx
import pytest
import respx

from coolify_cf_tunnel_sync.cloudflare import (
    API_BASE,
    CloudflareClient,
    CloudflareError,
)

ACCOUNT = "acc-1"
TUNNEL = "tun-1"
ZONE = "zone-1"
CONFIG_URL = (
    f"{API_BASE}/client/v4/accounts/{ACCOUNT}"
    f"/cfd_tunnel/{TUNNEL}/configurations"
)
DNS_URL = f"{API_BASE}/client/v4/zones/{ZONE}/dns_records"


def make_client() -> CloudflareClient:
    return CloudflareClient("cf-token", ACCOUNT, TUNNEL, zone_id=ZONE)


@respx.mock
def test_get_tunnel_config_returns_config_dict():
    config = {"ingress": [{"service": "http_status:404"}]}
    respx.get(CONFIG_URL).mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"config": config}}
        )
    )
    with make_client() as client:
        assert client.get_tunnel_config() == config


@respx.mock
def test_raises_when_success_is_false():
    respx.get(CONFIG_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": False,
                "errors": [{"code": 1000, "message": "bad request"}],
            },
        )
    )
    with make_client() as client:
        with pytest.raises(CloudflareError, match="bad request"):
            client.get_tunnel_config()


@respx.mock
def test_raises_on_http_error():
    respx.get(CONFIG_URL).mock(
        return_value=httpx.Response(403, json={"success": False, "errors": []})
    )
    with make_client() as client:
        with pytest.raises(CloudflareError, match="403"):
            client.get_tunnel_config()


@respx.mock
def test_put_tunnel_config_sends_whole_config():
    route = respx.put(CONFIG_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )
    config = {"ingress": [{"service": "http_status:404"}]}
    with make_client() as client:
        client.put_tunnel_config(config)
    import json

    body = json.loads(route.calls[0].request.content)
    assert body == {"config": config}


@respx.mock
def test_ensure_cname_creates_when_missing():
    respx.get(DNS_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    post = respx.post(DNS_URL).mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"id": "rec-1"}}
        )
    )
    with make_client() as client:
        assert client.ensure_cname("app.example.com") is True
    import json

    body = json.loads(post.calls[0].request.content)
    assert body["type"] == "CNAME"
    assert body["name"] == "app.example.com"
    assert body["content"] == f"{TUNNEL}.cfargotunnel.com"
    assert body["proxied"] is True


@respx.mock
def test_ensure_cname_skips_when_present():
    respx.get(DNS_URL).mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": [{"id": "rec-1"}]}
        )
    )
    post = respx.post(DNS_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )
    with make_client() as client:
        assert client.ensure_cname("app.example.com") is False
    assert not post.called


def test_dns_without_zone_id_raises():
    client = CloudflareClient("cf-token", ACCOUNT, TUNNEL)
    with pytest.raises(CloudflareError, match="CF_ZONE_ID"):
        client.cname_exists("app.example.com")
