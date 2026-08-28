"""Tests for fqdn parsing and the Coolify API client."""

import httpx
import pytest
import respx

from coolify_cf_tunnel_sync.coolify import (
    CoolifyClient,
    CoolifyError,
    parse_fqdn,
)

BASE_URL = "https://coolify.example.com"


def test_parse_fqdn_string_with_commas_and_schemes():
    fqdn = "https://app.example.com, http://blog.example.com/some/path"
    assert parse_fqdn(fqdn) == {"app.example.com", "blog.example.com"}


def test_parse_fqdn_list_shape():
    fqdn = ["https://a.example.com", "b.example.com"]
    assert parse_fqdn(fqdn) == {"a.example.com", "b.example.com"}


def test_parse_fqdn_list_items_may_contain_commas():
    fqdn = ["https://a.example.com,https://b.example.com", "c.example.com"]
    assert parse_fqdn(fqdn) == {
        "a.example.com",
        "b.example.com",
        "c.example.com",
    }


def test_parse_fqdn_strips_port_and_userinfo():
    assert parse_fqdn("https://user@app.example.com:8443/x") == {
        "app.example.com"
    }


def test_parse_fqdn_handles_junk():
    assert parse_fqdn(None) == set()
    assert parse_fqdn("") == set()
    assert parse_fqdn("  , ,") == set()
    assert parse_fqdn(42) == set()
    assert parse_fqdn([]) == set()


def test_parse_fqdn_normalizes_case_and_trailing_dot():
    assert parse_fqdn("HTTPS://APP.Example.COM./") == {"app.example.com"}


@respx.mock
def test_get_domains_collects_all_apps():
    respx.get(f"{BASE_URL}/api/v1/applications").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"fqdn": "https://a.example.com, b.example.com"},
                {"fqdn": ["c.example.com/path"]},
                {"fqdn": None},
                "not-a-dict",
            ],
        )
    )
    with CoolifyClient(BASE_URL, "token") as client:
        assert client.get_domains() == {
            "a.example.com",
            "b.example.com",
            "c.example.com",
        }


@respx.mock
def test_get_domains_sends_bearer_token():
    route = respx.get(f"{BASE_URL}/api/v1/applications").mock(
        return_value=httpx.Response(200, json=[])
    )
    with CoolifyClient(BASE_URL, "secret-token") as client:
        client.get_domains()
    assert route.calls[0].request.headers["Authorization"] == (
        "Bearer secret-token"
    )


@respx.mock
def test_get_applications_raises_on_http_error():
    respx.get(f"{BASE_URL}/api/v1/applications").mock(
        return_value=httpx.Response(401, json={"message": "unauthorized"})
    )
    with CoolifyClient(BASE_URL, "bad-token") as client:
        with pytest.raises(CoolifyError, match="401"):
            client.get_applications()
