"""The player reference: who is on a depth chart, and what they are worth.

Assembled from four nflverse tables and cached locally, because a run needs it
within a second or two and nflverse publishes it a few times a week.

Two numbers are carried for every player and they are not the same number.
**Depth rank** is a player's place on their team's depth chart — who is on the
field. **ECR tier** is where their expert consensus ranking falls — who is
worth starting. A team's starting kicker is depth rank 1 and a bottom ECR tier.
Collapsing the two into one field called `tier` is the defect ADR-0002 exists
to correct, so nothing here is named `tier` on its own.

`nflreadpy` hands back Polars frames. They are converted to records in
`_records` and nothing downstream of it — not the cache, not the templates, not
the prompt — sees a frame.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from math import ceil, isnan
from typing import Any, Protocol

from project_ai_ftsy_football_sum.container import Container
from project_ai_ftsy_football_sum.services.failures import error_detail

#: How long a synced reference is treated as current. Depth charts move a few
#: times a week, so twice a day is comfortably ahead of the source.
CACHE_TTL = timedelta(hours=12)

#: How many seasons back to look before giving up on finding depth charts.
SEASON_FALLBACK_DEPTH = 5

#: nflverse rolls its rosters over to the new season in the middle of March;
#: before that, "this season" still means last autumn's. Matching that date is
#: what makes the current year's depth charts findable the moment they appear.
SEASON_ROLLOVER = (3, 15)

#: The rankings page the reference reads. One row per player across every
#: fantasy position, carrying the consensus rank and the bye week. The dynasty
#: and best-ball pages rank the same players differently and are ignored.
RANKINGS_PAGE = "redraft-overall"

#: How many players make up one tier of expert consensus rank: a standard
#: league's worth, so tier 1 is who a manager spends a first-round pick on and
#: a starting kicker lands ten tiers below the running back beside him on the
#: depth chart.
#:
#: nflverse's rankings table carries the consensus rank but no tier column —
#: FantasyPros publishes tiers only on its own site — so the tier is derived
#: from the rank here. Derived the same way every time, which is what ticket
#: 08's byte-stable prompt needs. See ADR-0002.
TIER_SIZE = 12

#: The positions a fantasy manager can actually start, and so the only ones
#: worth paying for on every run. Everybody else on a depth chart is a
#: long-snapper as far as a podcast is concerned. Team defences are not
#: depth-chart rows, which is why there is no DST here; the fullback is in
#: because a handful of them are startable and the prompt has always had it.
#:
#: It sits here, beside the reference it describes a slice of, so that the
#: prompt and the page read one definition instead of a copy each.
FANTASY_POSITIONS = frozenset({"QB", "RB", "FB", "WR", "TE", "K"})

#: The two buckets every position falls in, and what the Players page calls
#: them. Two rather than three: an offence/defence/special-teams split was
#: considered and rejected, because the question a reader is asking is "can I
#: start this player", and a guard and a defensive end fall the same side of
#: it.
FANTASY_BUCKET = "fantasy"
OTHER_BUCKET = "other"
BUCKET_LABELS: Mapping[str, str] = {
    FANTASY_BUCKET: "Fantasy positions",
    OTHER_BUCKET: "Everything else",
}

#: The buckets the Players page opens on. Everybody else is one toggle away —
#: carried, rendered, and one click from being on show, but not in the way of
#: the question the page is usually opened to answer.
DEFAULT_BUCKETS = frozenset({FANTASY_BUCKET})

#: The depth-chart group a player is listed in for kick and punt duty. A wide
#: receiver who returns punts is the first-string returner and the second-
#: string receiver; the receiver line is the one that describes their week.
SPECIAL_TEAMS_GROUP = "Special Teams"

#: Depth-chart slot abbreviations that are not the position a reader knows the
#: player by. Only needed for players nflverse holds no profile for.
_SLOT_POSITIONS: Mapping[str, str] = {"PK": "K", "PR": "WR", "KR": "WR", "H": "P"}

#: Name suffixes dropped before matching a depth-chart name to a ranking; the
#: two sources disagree about them more often than they agree.
_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


def position_bucket(position: str | None) -> str:
    """Which bucket a player's position puts them in.

    Read off the position and nothing else: the depth chart's own group column
    holds formation names — "3WR 1TE", "Base 3-4", "Special Teams" — which say
    what package a player is on the field for, not whether anybody can start
    them. A kicker and a punter share that column and are on opposite sides of
    this question.
    """
    return FANTASY_BUCKET if position in FANTASY_POSITIONS else OTHER_BUCKET


class PlayerDataSource(Protocol):
    """The nflverse data, as the `nflverse` container edge supplies it.

    Every method returns a Polars frame. That is the only place in the
    application where one is allowed to exist.
    """

    def depth_charts(self, season: int) -> Any: ...

    def players(self) -> Any: ...

    def fantasy_rankings(self) -> Any: ...

    def injuries(self, season: int) -> Any: ...


class ReferenceCache(Protocol):
    """Where a synced reference is kept between runs. See `player_cache.py`."""

    def load(self) -> PlayerReference | None: ...

    def save(self, reference: PlayerReference) -> None: ...


class NflverseUnavailableError(RuntimeError):
    """nflverse could not be read, and whoever asked needs to hear about it."""


@dataclass(frozen=True)
class PlayerRow:
    """One player in the reference, as everything downstream reads them.

    `depth_rank` and `ecr_tier` are deliberately separate fields with
    deliberately separate names — see the module docstring.
    """

    player_id: str
    player_name: str
    team: str
    position: str | None = None
    depth_rank: int | None = None
    ecr_tier: int | None = None
    ecr_rank: float | None = None
    bye_week: int | None = None
    injury_status: str | None = None

    @property
    def bucket(self) -> str:
        """Which half of the page this player is in. See `position_bucket`."""
        return position_bucket(self.position)

    @property
    def shown_by_default(self) -> bool:
        """Whether this player is on show before a reader touches a control."""
        return self.bucket in DEFAULT_BUCKETS


@dataclass(frozen=True)
class PositionBucket:
    """One bucket as the Players page offers it: a toggle and its positions.

    The page's two labelled columns of position toggles, and the pair of
    toggles above them, are these same two things read twice — which is what
    keeps a position from appearing under a heading whose toggle does not
    govern it.
    """

    name: str
    label: str
    positions: tuple[str, ...]

    @property
    def shown_by_default(self) -> bool:
        """Whether the page opens with this bucket on show."""
        return self.name in DEFAULT_BUCKETS


@dataclass(frozen=True)
class PlayerReference:
    """The whole reference, the season it describes, and when it was fetched.

    The season travels with the rows because it is the thing a reader most
    needs to know about them: in the preseason nflverse still holds last
    year's depth charts, and a summary written against those is wrong in a way
    that reads perfectly.
    """

    season: int
    synced_at: datetime
    rows: tuple[PlayerRow, ...]

    @property
    def age(self) -> timedelta:
        return _now() - self.synced_at

    @property
    def is_stale(self) -> bool:
        """Whether this reference is old enough to be worth syncing again."""
        return self.age >= CACHE_TTL

    @property
    def synced_label(self) -> str:
        """How long ago this was fetched, as a reader would say it."""
        return _age_label(self.age)

    @property
    def seasons_behind(self) -> int:
        """How many seasons back this is from the one we are living in."""
        return max(calendar_season() - self.season, 0)

    @property
    def teams(self) -> tuple[str, ...]:
        """Every team the reference holds players for, for the team filter.

        Read off the rows rather than from a list of the league, so the filter
        never offers a team whose depth chart nflverse has not published.
        """
        return tuple(sorted({row.team for row in self.rows if row.team}))

    @property
    def positions(self) -> tuple[str, ...]:
        """Every position the reference holds, for the position filter."""
        return tuple(sorted({row.position for row in self.rows if row.position}))

    @property
    def buckets(self) -> tuple[PositionBucket, ...]:
        """The positions the reference holds, split into the two buckets.

        In the order `BUCKET_LABELS` names them, which puts the fantasy
        positions first because they are what the page opens on.
        """
        positions = self.positions
        return tuple(
            PositionBucket(
                name=name,
                label=label,
                positions=tuple(
                    position
                    for position in positions
                    if position_bucket(position) == name
                ),
            )
            for name, label in BUCKET_LABELS.items()
        )

    @property
    def default_shown(self) -> int:
        """How many rows are on show before a reader touches a control.

        Rendered as the "showing X of Y" count, so that the number a page
        arrives with is the number of rows it arrives showing rather than one
        the script has to correct.
        """
        return sum(1 for row in self.rows if row.shown_by_default)


@dataclass(frozen=True)
class ReferenceOutcome:
    """The reference a caller got, and whether it is the one they asked for.

    A sync that failed over a warm cache is not a failure — but it is not
    nothing either, and the caller is the only one placed to say so where the
    reader will see it. Carrying the error back rather than swallowing it is
    what makes the staleness warning possible.
    """

    reference: PlayerReference
    #: What went wrong syncing, or `None` when nothing did. Kept as the failure
    #: itself rather than as the two strings read off it, because they are one
    #: fact with two readings: a sentence for the strip, and the exception text
    #: for the toggle under it.
    sync_failure: NflverseUnavailableError | None = None

    @property
    def sync_error(self) -> str | None:
        """Why the reference is not freshly synced, in the words a reader sees."""
        return None if self.sync_failure is None else str(self.sync_failure)

    @property
    def sync_detail(self) -> str | None:
        """The same failure as the error underneath it, for the toggle."""
        return None if self.sync_failure is None else error_detail(self.sync_failure)


def calendar_season() -> int:
    """The NFL season we are currently in.

    Rolls over in the middle of March, matching nflverse: rosters for the
    coming season appear then, months before any game is played.
    """
    today = date.today()
    return today.year if (today.month, today.day) >= SEASON_ROLLOVER else today.year - 1


def ensure_reference(container: Container, cache: ReferenceCache) -> ReferenceOutcome:
    """The current reference, syncing first if the cached one has gone stale.

    A failed sync with something in the cache is not a failure: the caller goes
    ahead against the older reference, and is told why it is the older one so
    that its age can be put on show. A failed sync with nothing cached raises,
    because the alternative is a summary written against no player data at all.
    """
    cached = cache.load()
    if cached is not None and not cached.is_stale:
        return ReferenceOutcome(cached)

    try:
        return ReferenceOutcome(sync_reference(container, cache))
    except NflverseUnavailableError as error:
        if cached is None:
            raise
        return ReferenceOutcome(cached, sync_failure=error)


def sync_reference(container: Container, cache: ReferenceCache) -> PlayerReference:
    """Fetch the reference now and cache it, whatever the cache already holds.

    What **Sync now** does, and the one path that reports its own failure
    rather than falling back: a reader who presses a button and is handed the
    same strip back cannot tell a refusal from a refresh.
    """
    try:
        reference = build_reference(container.resolve("nflverse"))
    except Exception as error:  # noqa: BLE001 — unwired, unreachable, all one
        raise NflverseUnavailableError(
            "The player reference could not be fetched from nflverse."
        ) from error
    cache.save(reference)
    return reference


def build_reference(source: PlayerDataSource) -> PlayerReference:
    """Assemble the reference from nflverse, for the most recent season it has."""
    season, depth_charts = _resolve_season(source, calendar_season())
    return PlayerReference(
        season=season,
        synced_at=_now(),
        rows=_build_rows(
            depth_charts,
            profiles=_records(source.players()),
            rankings=_records(source.fantasy_rankings()),
            injuries=_optional_records(source.injuries, season),
        ),
    )


def _resolve_season(
    source: PlayerDataSource, start: int
) -> tuple[int, list[dict[str, Any]]]:
    """The most recent season nflverse actually holds depth charts for.

    In the preseason the current year has no depth charts yet, which is the
    normal case rather than an exceptional one — so the fall back to the year
    before is a supported path and the season it lands on is reported.
    """
    for season in range(start, start - SEASON_FALLBACK_DEPTH, -1):
        records = _records(source.depth_charts(season))
        if records:
            return season, records
    raise NflverseUnavailableError(
        f"nflverse holds no depth charts for {start} or the "
        f"{SEASON_FALLBACK_DEPTH - 1} seasons before it."
    )


def _records(frame: Any) -> list[dict[str, Any]]:
    """A Polars frame as plain records. The only conversion point there is."""
    return list(frame.to_dicts())


def _optional_records(
    fetch: Callable[[int], Any], season: int
) -> list[dict[str, Any]]:
    """The injury feed, or nothing — the one table allowed to be absent.

    nflverse refuses a season that has not kicked off, and in the preseason
    that is the very season whose depth charts we are reading. The alternative
    to a blank injury column would be last season's designations, which is the
    one thing a stale status must never be: it gets acted on, a blank does not.
    """
    try:
        return _records(fetch(season))
    except Exception:  # noqa: BLE001 — an absent feed is not a failed sync
        return []


@dataclass(frozen=True)
class _Rankings:
    """Expert consensus ranks, looked up the way the depth chart names players.

    The rankings carry no nflverse identifier, so the join is on the name. Name
    and team first, then the name alone — a player who has changed team since
    the rankings were scraped still matches, and two players sharing a name
    match neither, which is the right answer when guessing would put someone
    else's ranking beside their own.
    """

    by_name_and_team: dict[tuple[str, str], Mapping[str, Any]] = field(
        default_factory=dict
    )
    by_name: dict[str, Mapping[str, Any] | None] = field(default_factory=dict)
    #: Bye weeks read off the same rows: every team has a ranked player, so one
    #: pass covers the players who have none. nflverse's player table carries
    #: no bye week, which is why it is not read from there.
    team_byes: dict[str, int] = field(default_factory=dict)

    @classmethod
    def of(cls, records: Sequence[Mapping[str, Any]]) -> _Rankings:
        rankings = cls()
        for record in records:
            if record.get("page_type") != RANKINGS_PAGE:
                continue
            name, team = _name_key(record.get("player")), _team(record)
            rankings.by_name_and_team[(name, team)] = record
            # A second player of the same name makes the name useless alone.
            rankings.by_name[name] = None if name in rankings.by_name else record
            bye = _int(record.get("bye"))
            if bye is not None:
                rankings.team_byes.setdefault(team, bye)
        return rankings

    def of_player(self, name: str, team: str) -> Mapping[str, Any]:
        key = _name_key(name)
        return self.by_name_and_team.get((key, team)) or self.by_name.get(key) or {}

    def bye_for(self, team: str) -> int | None:
        return self.team_byes.get(team)


@dataclass(frozen=True)
class _Lookups:
    """Everything a depth-chart line has to be read against to become a row."""

    profiles: Mapping[str, Mapping[str, Any]]
    rankings: _Rankings
    injuries: Mapping[str, str]

    def row(self, player_id: str, record: Mapping[str, Any]) -> PlayerRow:
        gsis_id = str(record.get("gsis_id") or "")
        profile = self.profiles.get(gsis_id, {})
        name = str(
            profile.get("display_name") or record.get("player_name") or ""
        ).strip()
        team = _team(record)

        ranking = self.rankings.of_player(name, team)
        ecr_rank = _float(ranking.get("ecr"))

        return PlayerRow(
            player_id=player_id,
            player_name=name,
            team=team,
            position=_position(profile, record),
            depth_rank=_int(record.get("pos_rank")),
            ecr_tier=_ecr_tier(ecr_rank),
            ecr_rank=ecr_rank,
            bye_week=_int(ranking.get("bye")) or self.rankings.bye_for(team),
            injury_status=self.injuries.get(gsis_id),
        )


def _build_rows(
    depth_charts: Sequence[Mapping[str, Any]],
    *,
    profiles: Sequence[Mapping[str, Any]],
    rankings: Sequence[Mapping[str, Any]],
    injuries: Sequence[Mapping[str, Any]],
) -> tuple[PlayerRow, ...]:
    lookups = _Lookups(
        profiles={
            str(record["gsis_id"]): record
            for record in profiles
            if record.get("gsis_id")
        },
        rankings=_Rankings.of(rankings),
        injuries=_current_injuries(injuries),
    )
    rows = [
        lookups.row(player_id, record)
        for player_id, record in _depth_entries(_latest_snapshot(depth_charts)).items()
    ]
    # Sorted once, here, so that everything reading the reference — the page,
    # the cache, and the block handed to Claude — sees the same order.
    return tuple(sorted(rows, key=_ordering))


def _ordering(row: PlayerRow) -> tuple[str, str, int, str, str]:
    return (
        row.team,
        row.position or "",
        row.depth_rank if row.depth_rank is not None else 99,
        row.player_name,
        row.player_id,
    )


def _latest_snapshot(
    records: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Only the newest depth chart each team has published.

    nflverse keeps every scrape of the season in one table, so reading it
    whole would report a player at every rank they have ever held.
    """
    latest: dict[str, str] = {}
    for record in records:
        team, moment = _team(record), str(record.get("dt") or "")
        if moment > latest.get(team, ""):
            latest[team] = moment
    return [
        record
        for record in records
        if str(record.get("dt") or "") == latest.get(_team(record), "")
    ]


def _depth_entries(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    """One depth-chart line per player: the one describing their week."""
    best: dict[str, Mapping[str, Any]] = {}
    for record in records:
        key = _player_id(record)
        if key is None:
            continue
        if key not in best or _line_priority(record) < _line_priority(best[key]):
            best[key] = record
    return best


def _line_priority(record: Mapping[str, Any]) -> tuple[bool, int, str]:
    """Their own unit before special teams, then the highest rank they hold."""
    return (
        record.get("pos_grp") == SPECIAL_TEAMS_GROUP,
        _int(record.get("pos_rank")) or 99,
        str(record.get("pos_abb") or ""),
    )


def _ecr_tier(ecr_rank: float | None) -> int | None:
    """Which league's-worth of consensus rank a player falls into."""
    if ecr_rank is None or ecr_rank <= 0:
        return None
    return ceil(ecr_rank / TIER_SIZE)


def _position(profile: Mapping[str, Any], record: Mapping[str, Any]) -> str | None:
    """The position a reader knows the player by.

    nflverse's player table is the authority; the depth-chart slot stands in
    for the handful of players it holds no profile for.
    """
    listed = profile.get("position")
    if listed:
        return str(listed)
    slot = str(record.get("pos_abb") or "").upper()
    return _SLOT_POSITIONS.get(slot, slot) or None


def _name_key(name: Any) -> str:
    """A player's name as both sources would agree to write it."""
    cleaned = "".join(
        character if character.isalnum() or character.isspace() else " "
        for character in str(name or "").lower()
    )
    parts = [part for part in cleaned.split() if part not in _NAME_SUFFIXES]
    return " ".join(parts)


def _current_injuries(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Report status for the most recent week the feed covers, and no other.

    A designation from three weeks ago is worse than a blank one, because a
    blank is read as "no news" and a stale "questionable" is acted on.
    """
    weeks = [week for week in map(_week, records) if week is not None]
    if not weeks:
        return {}
    current = max(weeks)

    statuses: dict[str, str] = {}
    for record in records:
        status = str(record.get("report_status") or "").strip()
        gsis_id = str(record.get("gsis_id") or "")
        if status and gsis_id and _week(record) == current:
            statuses[gsis_id] = status
    return statuses


def _week(record: Mapping[str, Any]) -> int | None:
    return _int(record.get("week"))


def _player_id(record: Mapping[str, Any]) -> str | None:
    """What identifies a player. nflverse leaves a few without an identifier."""
    gsis_id = str(record.get("gsis_id") or "").strip()
    if gsis_id:
        return gsis_id
    name = str(record.get("player_name") or "").strip()
    return f"{_team(record)}:{name}" if name else None


def _team(record: Mapping[str, Any]) -> str:
    return str(record.get("team") or "").strip().upper()


def _int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if isnan(number) else number


def _now() -> datetime:
    return datetime.now(UTC)


#: The thresholds a sync age is read against, longest first.
_AGE_UNITS: tuple[tuple[str, Callable[[timedelta], int]], ...] = (
    ("day", lambda age: age.days),
    ("hour", lambda age: int(age.total_seconds() // 3600)),
    ("minute", lambda age: int(age.total_seconds() // 60)),
)


def _age_label(age: timedelta) -> str:
    """How long ago something happened, in the largest unit that says it."""
    for unit, count_in in _AGE_UNITS:
        count = count_in(age)
        if count >= 1:
            return f"{count} {plural(unit, count)} ago"
    return "just now"


def plural(word: str, count: int) -> str:
    """`word`, pluralised when there is not exactly one of it."""
    return word if count == 1 else f"{word}s"
