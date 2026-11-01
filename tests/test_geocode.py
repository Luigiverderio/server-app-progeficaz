from unittest.mock import Mock

import pytest
import requests


def test_geocode_returns_coordinates(load_app, monkeypatch):
    module = load_app()
    get = Mock(return_value=Mock(
        status_code=200, json=Mock(return_value=[{"lat": "-23.5614", "lon": "-46.6559"}])
    ))
    monkeypatch.setattr(module.requests, "get", get)

    assert module.geocode("Av. Paulista, 1578, São Paulo") == (-23.5614, -46.6559)
    kwargs = get.call_args.kwargs
    assert kwargs["params"] == {
        "q": "Av. Paulista, 1578, São Paulo", "format": "json", "limit": 1
    }
    assert kwargs["timeout"] == 5
    assert "server-app-progeficaz" in kwargs["headers"]["User-Agent"]


def test_geocode_unknown_address(load_app, monkeypatch):
    module = load_app()
    monkeypatch.setattr(module.requests, "get", Mock(return_value=Mock(
        status_code=200, json=Mock(return_value=[])
    )))
    assert module.geocode("Rua Inventada Xyzq987, 999999, Cidade Inexistente") is None


@pytest.mark.parametrize("error", [
    requests.exceptions.ConnectionError("sem internet"),
    requests.exceptions.Timeout("tempo esgotado"),
])
def test_geocode_network_failure_keeps_server_running(load_app, monkeypatch, error):
    module = load_app()
    monkeypatch.setattr(module.requests, "get", Mock(side_effect=error))

    with pytest.raises(RuntimeError, match="Falha no serviço de geocodificação"):
        module.geocode("Av. Paulista, 1578, São Paulo")
    assert module.app.test_client().get("/health").status_code == 503
    assert module._geocode_cache == {}


@pytest.mark.parametrize("status", [403, 429, 500, 503])
def test_geocode_http_failure(load_app, monkeypatch, status):
    module = load_app()
    monkeypatch.setattr(module.requests, "get", Mock(return_value=Mock(status_code=status)))
    with pytest.raises(RuntimeError, match="Falha no serviço de geocodificação"):
        module.geocode("Av. Paulista, 1578, São Paulo")


@pytest.mark.parametrize("payload", [
    {}, None, [{}], [None], [{"lat": "inválido", "lon": "0"}],
    [{"lat": "91", "lon": "0"}], [{"lat": "0", "lon": "181"}],
    [{"lat": "NaN", "lon": "0"}],
])
def test_geocode_invalid_response(load_app, monkeypatch, payload):
    module = load_app()
    monkeypatch.setattr(module.requests, "get", Mock(return_value=Mock(
        status_code=200, json=Mock(return_value=payload)
    )))
    with pytest.raises(RuntimeError, match="Falha no serviço de geocodificação"):
        module.geocode("Av. Paulista, 1578, São Paulo")


def test_geocode_invalid_json(load_app, monkeypatch):
    module = load_app()
    monkeypatch.setattr(module.requests, "get", Mock(return_value=Mock(
        status_code=200, json=Mock(side_effect=ValueError("JSON inválido"))
    )))
    with pytest.raises(RuntimeError, match="Falha no serviço de geocodificação"):
        module.geocode("Av. Paulista, 1578, São Paulo")


@pytest.mark.parametrize("address", [None, "", "   ", 123])
def test_geocode_empty_address_does_not_query(load_app, monkeypatch, address):
    module = load_app()
    get = Mock()
    monkeypatch.setattr(module.requests, "get", get)
    assert module.geocode(address) is None
    get.assert_not_called()


def test_geocode_cache_and_request_interval(load_app, monkeypatch):
    module = load_app()
    get = Mock(return_value=Mock(
        status_code=200, json=Mock(return_value=[{"lat": "-23.56", "lon": "-46.65"}])
    ))
    sleep = Mock()
    monkeypatch.setattr(module.requests, "get", get)
    monkeypatch.setattr(module.time, "monotonic", Mock(side_effect=[10, 10.25, 11]))
    monkeypatch.setattr(module.time, "sleep", sleep)

    assert module.geocode("Paulista") == (-23.56, -46.65)
    assert module.geocode(" Paulista ") == (-23.56, -46.65)
    assert module.geocode("Sé") == (-23.56, -46.65)
    assert get.call_count == 2
    sleep.assert_called_once_with(0.75)
