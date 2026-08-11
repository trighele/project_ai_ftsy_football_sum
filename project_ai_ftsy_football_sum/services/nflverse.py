"""The real nflverse edge: four tables from nflreadpy.

This is the implementation the container resolves for the `nflverse` edge, and
the only place in the application that imports `nflreadpy` or sees a Polars
frame on its way out. Every decision about what the four tables mean lives in
`players.py`, which needs no network to be tested; only the calls are here.

`nflreadpy` is imported at module scope, which costs nothing until an edge is
resolved: the container imports this module inside its factory, so nothing that
does not do a sync ever pays for Polars.
"""

from __future__ import annotations

from typing import Any

import nflreadpy


class NflverseSource:
    """Everything the app asks nflverse for, in one place.

    Four tables, each answering one question about a player: where they are on
    the depth chart, who they are, what the experts think they are worth, and
    whether they are hurt.
    """

    def depth_charts(self, season: int) -> Any:
        """Every depth chart published during a season. Depth rank lives here."""
        return nflreadpy.load_depth_charts(season)

    def players(self) -> Any:
        """Identity: the name, position, and team nflverse knows a player by."""
        return nflreadpy.load_players()

    def fantasy_rankings(self) -> Any:
        """Expert consensus rankings. ECR rank and the bye week live here."""
        return nflreadpy.load_ff_rankings("draft")

    def injuries(self, season: int) -> Any:
        """Weekly injury reports, and the one call that refuses a season.

        nflverse rejects a season that has not kicked off yet, which in the
        preseason is the season whose depth charts we are reading — see
        `players._optional_records` for what is done about it.
        """
        return nflreadpy.load_injuries(season)
