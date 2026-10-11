"""
Time zones for photo dates.

Why this file exists:
    Photos store a time zone as an offset ("-06:00" in OffsetTimeOriginal),
    not a name, and a named zone's offset changes with daylight saving. The
    Date & Time tab lists common named zones with the offset each has on the
    photo's date, picks a sensible default from the photos, and converts
    times between zones. Plain date math, no Qt.

The list has one zone per distinct offset/daylight-saving pattern (no
repeats such as several cities with the same rules), ordered from the
furthest east at the top to the furthest west at the bottom.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - zoneinfo is standard since Python 3.9
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception


@dataclass(frozen=True)
class Zone:
    """A named time zone in the list."""

    key: str
    name: str
    iana: str
    # Used if the zone database can't be loaded: the standard offset (hours).
    standard_hours: float


# East (top) to west (bottom).
ZONES: tuple[Zone, ...] = (
    Zone("auckland", "New Zealand (Auckland)", "Pacific/Auckland", 12),
    Zone("sydney", "Eastern Australia (Sydney)", "Australia/Sydney", 10),
    Zone("brisbane", "Queensland (Brisbane)", "Australia/Brisbane", 10),
    Zone("adelaide", "Central Australia (Adelaide)", "Australia/Adelaide", 9.5),
    Zone("tokyo", "Japan, Korea (Tokyo)", "Asia/Tokyo", 9),
    Zone("shanghai", "China, Singapore (Shanghai)", "Asia/Shanghai", 8),
    Zone("bangkok", "Indochina (Bangkok)", "Asia/Bangkok", 7),
    Zone("dhaka", "Bangladesh (Dhaka)", "Asia/Dhaka", 6),
    Zone("kolkata", "India (Kolkata)", "Asia/Kolkata", 5.5),
    Zone("karachi", "Pakistan (Karachi)", "Asia/Karachi", 5),
    Zone("dubai", "Gulf (Dubai)", "Asia/Dubai", 4),
    Zone("istanbul", "Turkey, Moscow (Istanbul)", "Europe/Istanbul", 3),
    Zone("athens", "Eastern Europe (Athens)", "Europe/Athens", 2),
    Zone("paris", "Central Europe (Paris)", "Europe/Paris", 1),
    Zone("london", "UK, Ireland, Portugal (London)", "Europe/London", 0),
    Zone("utc", "Coordinated Universal Time (UTC)", "Etc/UTC", 0),
    Zone("azores", "Azores", "Atlantic/Azores", -1),
    Zone("sao_paulo", "Brazil (São Paulo)", "America/Sao_Paulo", -3),
    Zone("st_johns", "Newfoundland (St. John's)", "America/St_Johns", -3.5),
    Zone("halifax", "Atlantic Time (Halifax)", "America/Halifax", -4),
    Zone("eastern", "Eastern Time (New York)", "America/New_York", -5),
    Zone("central", "Central Time (Chicago)", "America/Chicago", -6),
    Zone("mexico_city", "Mexico City (no daylight saving)", "America/Mexico_City", -6),
    Zone("mountain", "Mountain Time (Denver)", "America/Denver", -7),
    Zone("arizona", "Arizona (Phoenix, no daylight saving)", "America/Phoenix", -7),
    Zone("pacific", "Pacific Time (Los Angeles)", "America/Los_Angeles", -8),
    Zone("alaska", "Alaska (Anchorage)", "America/Anchorage", -9),
    Zone("hawaii", "Hawaii (Honolulu)", "Pacific/Honolulu", -10),
)
ZONES_BY_KEY = {zone.key: zone for zone in ZONES}
EASTERN = ZONES_BY_KEY["eastern"]

# Which zone a photo's offset most likely means, when several have it on
# that date (-06:00 in October is Mountain daylight time or Central
# standard time): US zones first, then the list order.
_US_FIRST = ("eastern", "central", "mountain", "pacific", "arizona", "alaska", "hawaii")
_MATCH_ORDER = [ZONES_BY_KEY[key] for key in _US_FIRST] + [
    zone for zone in ZONES if zone.key not in _US_FIRST
]


def _zone_info(zone: Zone):
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(zone.iana)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def offset_at_local(zone: Zone, local: datetime) -> timedelta:
    """The zone's offset for a clock time in that zone (daylight saving aware)."""
    info = _zone_info(zone)
    if info is None:
        return timedelta(hours=zone.standard_hours)
    return local.replace(tzinfo=info).utcoffset()


def offset_at_instant(zone: Zone, utc: datetime) -> timedelta:
    """The zone's offset at a moment given in UTC (naive)."""
    info = _zone_info(zone)
    if info is None:
        return timedelta(hours=zone.standard_hours)
    return utc.replace(tzinfo=timezone.utc).astimezone(info).utcoffset()


def to_zone(utc: datetime, zone: Zone) -> tuple[datetime, timedelta]:
    """A UTC moment as clock time in a zone, and the offset used."""
    offset = offset_at_instant(zone, utc)
    return utc + offset, offset


def abbreviation(zone: Zone, local: datetime) -> str:
    """'MDT', 'CET'; zones without a letter name give 'UTC−6'."""
    info = _zone_info(zone)
    name = local.replace(tzinfo=info).tzname() if info is not None else None
    if not name or name[0] in "+-":
        return offset_short(offset_at_local(zone, local))
    return name


def parse_offset(text) -> timedelta | None:
    """'-06:00' / '+05:30' / 'Z' -> timedelta; anything else None."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if text in ("Z", "+00:00", "-00:00"):
        return timedelta(0)
    if len(text) != 6 or text[0] not in "+-" or text[3] != ":":
        return None
    try:
        hours, minutes = int(text[1:3]), int(text[4:6])
    except ValueError:
        return None
    if hours > 14 or minutes > 59:
        return None
    sign = -1 if text[0] == "-" else 1
    return sign * timedelta(hours=hours, minutes=minutes)


def format_offset(offset: timedelta) -> str:
    """timedelta -> '-06:00', the form EXIF stores."""
    minutes = int(offset.total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    hours, rest = divmod(abs(minutes), 60)
    return f"{sign}{hours:02d}:{rest:02d}"


def offset_short(offset: timedelta) -> str:
    """timedelta -> 'UTC−6', 'UTC+5:30', 'UTC'."""
    minutes = int(offset.total_seconds() // 60)
    if not minutes:
        return "UTC"
    sign = "−" if minutes < 0 else "+"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")


def zone_label(zone: Zone, local: datetime) -> str:
    """
    The drop-down text: 'Mountain Time (Denver) — MDT' on that date (its
    abbreviation follows daylight saving). Zones without a letter
    abbreviation show their offset, 'Gulf (Dubai) — UTC+4'.
    """
    return f"{zone.name} — {abbreviation(zone, local)}"


def zone_for_offset(offset: timedelta, local: datetime) -> Zone | None:
    """The listed zone a photo's offset most likely means on its date."""
    for zone in _MATCH_ORDER:
        if offset_at_local(zone, local) == offset:
            return zone
    return None


def describe_offset(offset: timedelta | None, local: datetime) -> str:
    """A photo's own zone for display: 'MDT', or 'UTC−6' if not in the list."""
    if offset is None:
        return ""
    zone = zone_for_offset(offset, local)
    return abbreviation(zone, local) if zone is not None else offset_short(offset)


def east_of_eastern(zone: Zone, local: datetime) -> bool:
    return offset_at_local(zone, local) > offset_at_local(EASTERN, local)


def default_zone(
    photos: Iterable[tuple[datetime | None, timedelta | None]],
    *,
    computer_offset: timedelta,
    now: datetime,
) -> Zone | None:
    """
    The time zone the drop-down starts on, from the photos considered (the
    selected photos, or every photo in the list when none are selected):

    - No photos: the computer's zone.
    - No photo has a zone: None (no time zone).
    - Otherwise the zone most of them have; on a tie, the zone of the
      earliest photo among the tied ones.
    - Never further east than US Eastern (choosing one by hand still works).

    Args:
        photos:
            (date taken, offset) per photo; either may be None.
    """
    photo_list = list(photos)
    if not photo_list:
        zone = zone_for_offset(computer_offset, now) or EASTERN
        return EASTERN if east_of_eastern(zone, now) else zone

    with_zone = [(taken, offset) for taken, offset in photo_list if offset is not None]
    if not with_zone:
        return None

    counts = Counter(offset for _, offset in with_zone)
    top = max(counts.values())
    tied = {offset for offset, count in counts.items() if count == top}
    candidates = [(taken, offset) for taken, offset in with_zone if offset in tied]
    taken, offset = min(candidates, key=lambda pair: (pair[0] is None, pair[0] or now))
    when = taken or now
    zone = zone_for_offset(offset, when)
    if zone is None:
        # An offset the list doesn't have: east of Eastern clamps to it,
        # anything else falls back to the computer's zone.
        if offset > offset_at_local(EASTERN, when):
            return EASTERN
        return default_zone([], computer_offset=computer_offset, now=now)
    return EASTERN if east_of_eastern(zone, when) else zone


def computer_utc_offset(now: datetime | None = None) -> timedelta:
    """The computer's current offset from UTC."""
    moment = (now or datetime.now()).astimezone()
    return moment.utcoffset() or timedelta(0)
