"""Bloqueia acessos externos durante toda a suíte, inclusive na coleta."""

from contextlib import ExitStack
from unittest.mock import patch


def pytest_configure(config):
    patches = ExitStack()
    config.add_cleanup(patches.close)
    for target in (
        "pymongo.MongoClient",
        "requests.sessions.Session.request",
        "socket.socket.connect",
        "socket.socket.connect_ex",
        "socket.getaddrinfo",
    ):
        patches.enter_context(patch(
            target,
            side_effect=AssertionError(f"Acesso externo proibido nos testes: {target}"),
        ))
