"""
Geotagging from a GPS track: which photos get which position.

Why this file exists:
    File > Geotag from GPS Track shows every photo in the Photo List next to
    a track and where each one would be placed, then writes the positions
    of the photos the user keeps checked. Working that out (the moment each
    photo was taken, the track's position then, why a photo has none, the
    hints that explain it) is plain Python, kept here without Qt so the
    window only draws it and the web version can reuse it later.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from core.gpx_track import AFTER_TRACK, BEFORE_TRACK, IN_GAP, MAX_GAP, Match, NoMatch, TrackPoint, locate, track_span
from core.models import PhotoInfo
from core.photo_dates import format_display_datetime
from core.time_zones import describe_offset
from services.date_time_service import photo_instant

# A row's status.
ON_TRACK = "on"
BEFORE = BEFORE_TRACK
AFTER = AFTER_TRACK
GAP = IN_GAP
NO_DATE = "no_date"
# The photo's date and thumbnail are still being read.
READING = "reading"

# The chip on a row that has no position.
CHIP_TEXTS = {
    BEFORE: "Before the Track",
    AFTER: "After the Track",
    GAP: "In a Gap",
    NO_DATE: "No Date",
    READING: "Reading…",
}

DATE_TIP = (
    "If the camera's clock or time zone was wrong, fix it first on the Date & Time tab "
    "(Shift Date and Time, or Change Time Zone)."
)

# (latitude, longitude, altitude in metres or None): what a geotag writes.
type GpsValue = tuple[float, float, float | None]


@dataclass
class GeotagRow:
    path: Path
    name: str
    status: str
    # The photo's clock time as the list shows it ("10/03/2026 9:14:02am MDT").
    time_text: str = ""
    # When it was taken, naive UTC (None without a date).
    instant: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    # The photo's own coordinates when it already has some.
    has_gps: bool = False
    current: tuple[float, float] | None = None
    # Why there is no position, or where it will be placed (the hover hint).
    hint: str = ""
    # Checked in the list: will be written. Only rows on the track.
    included: bool = False

    @property
    def on_track(self) -> bool:
        return self.status == ON_TRACK

    @property
    def chip(self) -> str:
        if self.on_track:
            return "Has GPS" if self.has_gps else ""
        return CHIP_TEXTS[self.status]


@dataclass
class GeotagPlan:
    rows: list[GeotagRow] = field(default_factory=list)
    track_start: datetime | None = None
    track_end: datetime | None = None
    # The earliest and latest photo instants (dated photos only).
    photo_start: datetime | None = None
    photo_end: datetime | None = None
    # The computer's offset from UTC, used for photos without a time zone.
    computer_offset: timedelta = timedelta(0)
    # Altitudes in the hints: feet (the default) or metres.
    feet: bool = True

    @property
    def matched(self) -> list[GeotagRow]:
        return [row for row in self.rows if row.on_track]

    @property
    def included(self) -> list[GeotagRow]:
        return [row for row in self.rows if row.included]

    def set_included(self, path: Path, included: bool) -> None:
        for row in self.rows:
            if row.path == path and row.on_track:
                row.included = included
                row.hint = _match_hint(row, self.computer_offset, feet=self.feet)

    def summary(self) -> str:
        """'9 of 15 photos on the track'."""
        count = len(self.rows)
        return f"{len(self.matched)} of {count} photo{'' if count == 1 else 's'} on the track"

    def track_span_text(self) -> str:
        """The track's first and last time in the computer's zone: '10/03/2026 9:12:00am – 4:40:19pm MDT'."""
        if self.track_start is None or self.track_end is None:
            return ""
        return _span_text(self.track_start, self.track_end, self.computer_offset)


def build_geotag_plan(
    paths: list[Path],
    infos: Mapping[Path, PhotoInfo],
    track: list[TrackPoint],
    computer_offset: timedelta,
    *,
    previous: GeotagPlan | None = None,
    max_gap: timedelta = MAX_GAP,
    feet: bool = True,
) -> GeotagPlan:
    """
    A row for every photo in the Photo List (paths), oldest first, undated
    photos and photos still being read last. A photo without a time zone is
    taken as the computer's zone, the zone most cameras are set to. Rows on
    the track start checked, except photos that already have GPS (checking
    one replaces its coordinates); the checks of a previous plan (the window
    refreshing after more photos were added) are kept.
    """
    plan = GeotagPlan(computer_offset=computer_offset, feet=feet)
    if track:
        plan.track_start, plan.track_end = track_span(track)
    checks = {row.path: row.included for row in previous.rows if row.on_track} if previous else {}
    for path in paths:
        info = infos.get(path)
        if info is None:
            plan.rows.append(GeotagRow(path, path.name, READING, hint="Still reading this photo's date and thumbnail."))
            continue
        row = GeotagRow(path, path.name, NO_DATE)
        if info.current_latitude is not None and info.current_longitude is not None:
            row.has_gps = True
            row.current = (info.current_latitude, info.current_longitude)
        if info.date_taken is None:
            row.hint = "This photo has no date, so it can't be matched to the track."
            plan.rows.append(row)
            continue
        offset = info.time_offset if info.time_offset is not None else computer_offset
        # photo_instant with the photo's own zone; the computer's offset stands in without one.
        row.instant = photo_instant(info) if info.time_offset is not None else info.date_taken - offset
        row.time_text = f"{format_display_datetime(info.date_taken)} {describe_offset(offset, info.date_taken)}".rstrip()
        result = locate(track, row.instant, max_gap) if track else NoMatch(BEFORE_TRACK, timedelta(0))
        if isinstance(result, Match):
            row.status = ON_TRACK
            row.latitude, row.longitude, row.altitude = result.latitude, result.longitude, result.elevation
            row.included = checks.get(path, not row.has_gps)
            row.hint = _match_hint(row, computer_offset, result, offset, feet=feet)
        else:
            row.status = result.reason
            row.hint = _no_match_hint(result, plan, info, offset, computer_offset)
        plan.rows.append(row)
    dated = [row.instant for row in plan.rows if row.instant is not None]
    if dated:
        plan.photo_start, plan.photo_end = min(dated), max(dated)
    plan.rows.sort(key=_row_order)
    return plan


def geotag_values(plan: GeotagPlan) -> dict[Path, GpsValue]:
    """What Apply writes: the checked rows' positions."""
    return {row.path: (row.latitude, row.longitude, row.altitude) for row in plan.included}


def nothing_matches_hint(plan: GeotagPlan) -> str:
    """
    Why no photo is on the track, for the bottom of the window: the photos
    were taken before or after it (the time zone or the camera clock is
    probably wrong), or every one falls in a gap.
    """
    if plan.matched or plan.track_start is None:
        return ""
    if plan.photo_start is None:
        return "None of these photos has a date, so none can be matched to the track."
    spans = (
        f"(photos {_span_text(plan.photo_start, plan.photo_end, plan.computer_offset)}; "
        f"track {plan.track_span_text()}, in this computer's time zone)"
    )
    if plan.photo_end < plan.track_start:
        when = f"about {describe_duration(plan.track_start - plan.photo_end)} before"
    elif plan.photo_start > plan.track_end:
        when = f"about {describe_duration(plan.photo_start - plan.track_end)} after"
    else:
        return (
            f"None of these photos was taken within {describe_duration(MAX_GAP)} of a track point "
            f"{spans}. Check the time zone or the camera clock on the Date & Time tab, then load the track again."
        )
    return (
        f"Your photos were taken {when} this track {spans}. Check the time zone or the camera "
        "clock on the Date & Time tab, then load the track again."
    )


def describe_duration(value: timedelta) -> str:
    """A length of time for the hints: '35 min', '2 h 10 min', '3 days 2 h', '20 s'."""
    seconds = int(abs(value).total_seconds())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days} day{'' if days == 1 else 's'}" + (f" {hours} h" if hours else "")
    if hours:
        return f"{hours} h" + (f" {minutes} min" if minutes else "")
    if minutes:
        return f"{minutes} min"
    return f"{seconds} s"


FEET_PER_METRE = 3.280839895


def format_altitude(metres: float, feet: bool = True) -> str:
    """An altitude for display: '6,726 ft' (the default) or '2,050 m'."""
    if feet:
        return f"{metres * FEET_PER_METRE:,.0f} ft"
    return f"{metres:,.0f} m"


def format_coordinates(latitude: float, longitude: float, altitude: float | None = None, feet: bool = True) -> str:
    """'40.605000, -111.595000' plus ' · 6,726 ft' (or ' · 2,050 m') when there is an altitude."""
    text = f"{latitude:.6f}, {longitude:.6f}"
    if altitude is not None:
        text += f" · {format_altitude(altitude, feet)}"
    return text


def _match_hint(
    row: GeotagRow, computer_offset: timedelta, result: Match | None = None, offset: timedelta | None = None, *, feet: bool = True
) -> str:
    if offset is None:
        offset = computer_offset
    where = format_coordinates(row.latitude, row.longitude, row.altitude, feet)
    if row.has_gps and row.current is not None:
        current = format_coordinates(*row.current)
        if row.included:
            return (
                f"This photo already has GPS coordinates ({current}), the blue dot on the map. "
                f"Geotag will ask before replacing them with {where}."
            )
        return (
            f"This photo already has GPS coordinates ({current}), the blue dot on the map. "
            f"Check the box to replace them with {where}."
        )
    if result is not None and result.before is not result.after:
        between = (
            f", between the track's points at {_clock_text(result.before.time, offset)} "
            f"and {_clock_text(result.after.time, offset)}"
        )
    elif result is not None:
        between = f", the track's point at {_clock_text(result.before.time, offset)}"
    else:
        between = ""
    text = f"Will be placed at {where}{between}."
    if not row.included:
        text += " Left out: check the box to geotag it."
    return text


def _no_match_hint(result: NoMatch, plan: GeotagPlan, info: PhotoInfo, offset: timedelta, computer_offset: timedelta) -> str:
    if result.reason == IN_GAP:
        text = (
            f"Taken between two track points more than {describe_duration(MAX_GAP)} apart "
            f"(the track paused), {describe_duration(result.distance)} from the nearest one, so there is no position for it."
        )
    elif result.reason == BEFORE_TRACK:
        text = f"Taken {describe_duration(result.distance)} before the track starts ({_clock_text(plan.track_start, offset)})."
    else:
        text = f"Taken {describe_duration(result.distance)} after the track ends ({_clock_text(plan.track_end, offset)})."
    text += " " + DATE_TIP
    if info.time_offset is None:
        zone = describe_offset(computer_offset, info.date_taken) or "UTC"
        text += f" This photo has no time zone, so its clock time is taken as this computer's zone ({zone})."
    return text


def _clock_text(instant: datetime | None, offset: timedelta) -> str:
    """A UTC instant as a clock time in the given offset: '9:12:00am'."""
    if instant is None:
        return ""
    return format_display_datetime(instant + offset).split(" ", 1)[1]


def _span_text(start: datetime, end: datetime, offset: timedelta) -> str:
    first = start + offset
    last = end + offset
    zone = describe_offset(offset, first) or "UTC"
    if first.date() == last.date():
        return f"{format_display_datetime(first)} – {_clock_text(end, offset)} {zone}"
    return f"{format_display_datetime(first)} – {format_display_datetime(last)} {zone}"


def _row_order(row: GeotagRow):
    if row.instant is not None:
        return (0, row.instant, row.name.casefold())
    return (1 if row.status == NO_DATE else 2, datetime.min, row.name.casefold())
