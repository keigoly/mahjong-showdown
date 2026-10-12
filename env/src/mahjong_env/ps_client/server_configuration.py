# Derived from poke-env (https://github.com/hsahovic/poke-env, MIT License, Copyright (c) 2019 hsahovic).
# Modified for mahjong-showdown.
"""This module contains objects related to server configuration."""

from typing import NamedTuple


class ServerConfiguration(NamedTuple):
    """Server configuration object. Represented with a tuple with two entries: server url
    and authentication endpoint url."""

    websocket_url: str
    authentication_url: str


LocalhostServerConfiguration = ServerConfiguration(
    "ws://localhost:8000/showdown/websocket",
    "",
)
"""Server configuration for a local mahjong-showdown server (no authentication)."""
