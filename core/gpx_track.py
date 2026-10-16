"""
GPS tracks (GPX files) and where a photo was taken along one.

Why this file exists:
    A phone, watch, or GPS logger records a track: positions with the time
    (in UTC) each was recorded. A photo taken while the track was recorded
    was taken at the position the track holds for that moment, between the
    two track points around it. Reading GPX and finding that position is
    plain text and arithmetic, kept here without Qt so the desktop app and
    the web version can share it (File > Geotag from GPS Track in the
    desktop app).

GPX is XML: <trk> holds <trkseg>s of <trkpt lat lon> with <ele> and <time>.
Waypoints (<wpt>) and routes (<rte>) are not positions-over-time, so they
are ignored.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

# A photo further than this from the nearest track point has no position:
# the track paused (phone in a tunnel, battery died, recording stopped for
# lunch). ExifTool's geotagging uses the same limit.
MAX_GAP = timedelta(minutes=30)

# Why a photo has no position on the track (NoMatch.reason).
BEFORE_TRACK = "before"
AFTER_TRACK = "after"
IN_GAP = "gap"


class GpxError(ValueError):
    """A file that is not a usable GPX track (what is wrong, for the user)."""


@dataclass(frozen=True, order=True)
class TrackPoint:
    # Naive UTC, like the rest of the app's instants (photo_instant).
    time: datetime
    latitude: float
    longitude: float
    elevation: float | None = None


@dataclass(frozen=True)
class Match:
    latitude: float
    longitude: float
    # Metres above sea level, when the track points around the photo have it.
    elevation: float | None
    # The track points the position came from (one point when the photo is
    # just before the first or after the last).
    before: TrackPoint
    after: TrackPoint


@dataclass(frozen=True)
class NoMatch:
    reason: str
    # How far the photo is from the nearest track point in time.
    distance: timedelta


def parse_gpx(data: str | bytes, name: str = "the file") -> list[TrackPoint]:
    """
    The timed track points of a GPX file, oldest first. Points without a
    time are skipped (they can't be matched to a photo). GpxError when the
    file isn't XML or holds no timed track points.
    """
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise GpxError(f"{name} is not a GPX file ({error}).") from error
    points: list[TrackPoint] = []
    for element in root.iter():
        if _local_name(element.tag) != "trkpt":
            continue
        time_text = elevation_text = None
        for child in element:
            child_name = _local_name(child.tag)
            if child_name == "time":
                time_text = child.text
            elif child_name == "ele":
                elevation_text = child.text
        time = _parse_time(time_text)
        if time is None:
            continue
        try:
            latitude = float(element.get("lat", ""))
            longitude = float(element.get("lon", ""))
        except ValueError:
            continue
        elevation = None
        if elevation_text:
            try:
                elevation = float(elevation_text)
            except ValueError:
                elevation = None
        points.append(TrackPoint(time, latitude, longitude, elevation))
    if not points:
        raise GpxError(f"{name} has no track points with times, so photos can't be matched to it.")
    points.sort()
    return points


def read_gpx_files(paths: list[Path]) -> list[TrackPoint]:
    """Every file's points merged into one timeline (a day per file, say)."""
    tracks = []
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError as error:
            raise GpxError(f"{path.name} could not be read ({error.strerror or error}).") from error
        tracks.append(parse_gpx(data, path.name))
    return merge_tracks(tracks)


def merge_tracks(tracks: list[list[TrackPoint]]) -> list[TrackPoint]:
    return sorted(point for track in tracks for point in track)


def track_span(track: list[TrackPoint]) -> tuple[datetime, datetime]:
    """The first and last time on the track (naive UTC)."""
    return track[0].time, track[-1].time


def locate(track: list[TrackPoint], instant: datetime, max_gap: timedelta = MAX_GAP) -> Match | NoMatch:
    """
    Where the track was at instant (naive UTC): the position interpolated
    between the two points around it when they are at most max_gap apart;
    the first or last point itself when the instant is within max_gap
    before or after the track; otherwise NoMatch with the reason.
    """
    times = [point.time for point in track]
    index = bisect.bisect_left(times, instant)
    if index < len(track) and track[index].time == instant:
        point = track[index]
        return Match(point.latitude, point.longitude, point.elevation, point, point)
    if index == 0:
        first = track[0]
        distance = first.time - instant
        if distance <= max_gap:
            return Match(first.latitude, first.longitude, first.elevation, first, first)
        return NoMatch(BEFORE_TRACK, distance)
    if index == len(track):
        last = track[-1]
        distance = instant - last.time
        if distance <= max_gap:
            return Match(last.latitude, last.longitude, last.elevation, last, last)
        return NoMatch(AFTER_TRACK, distance)
    before, after = track[index - 1], track[index]
    gap = after.time - before.time
    if gap > max_gap:
        return NoMatch(IN_GAP, min(instant - before.time, after.time - instant))
    fraction = (instant - before.time) / gap if gap else 0.0
    elevation = None
    if before.elevation is not None and after.elevation is not None:
        elevation = before.elevation + (after.elevation - before.elevation) * fraction
    return Match(
        before.latitude + (after.latitude - before.latitude) * fraction,
        before.longitude + (after.longitude - before.longitude) * fraction,
        elevation,
        before,
        after,
    )


def _local_name(tag: str) -> str:
    """'{http://www.topografix.com/GPX/1/1}trkpt' -> 'trkpt'."""
    return tag.rsplit("}", 1)[-1]


def _parse_time(text: str | None) -> datetime | None:
    """
    A GPX <time> ("2026-10-03T15:12:00Z", or with fractional seconds or an
    offset) as naive UTC. Times without a zone are taken as UTC, which is
    what GPX requires.
    """
    if not text:
        return None
    value = text.strip()
    if value.endswith("Z") or value.endswith("z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
