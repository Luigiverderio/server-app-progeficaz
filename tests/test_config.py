import pytest


@pytest.mark.parametrize("secret", [None, "", "   "])
def test_missing_jwt_secret_stops_startup(load_app, secret):
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        load_app(secret=secret)


def test_jwt_configuration(load_app):
    module = load_app()
    assert module.app.config["JWT_SECRET_KEY"] == "test-secret-with-at-least-32-bytes"
    assert module.app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds() == 3600
