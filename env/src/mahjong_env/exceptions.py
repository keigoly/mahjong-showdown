# Derived from poke-env (https://github.com/hsahovic/poke-env, MIT License, Copyright (c) 2019 hsahovic).
# Modified for mahjong-showdown.
"""This module contains exceptions."""


class ShowdownException(Exception):
    """
    This exception is raised when a non-managed message
    is received from the server.
    """

    pass
