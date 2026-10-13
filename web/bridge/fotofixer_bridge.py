"""
The web version's Python entry points, run through Pyodide in the worker.

Why this file exists:
    The browser reuses the app's pure logic unchanged: coordinate parsing
    (services/coordinate_service.py), the Date & Time rules
    (services/date_time_service.py, core/photo_dates.py, core/time_zones.py)
    and the Date & Time presenter (gui/presenters/date_time_state.py, which
    has no Qt in it). JavaScript can't call those comfortably (Path keys,
    datetimes, dataclasses), so this module takes plain JSON in and gives
    plain JSON out. packaging/fetch_web_vendor.py zips it with the modules
    it imports; tests/test_web_bridge.py exercises it on the desktop.

    Photos arrive as {id: {name, dates, make, model}} and go into PhotoInfo
    objects whose path is "<index>/<name>", so the presenter's path.name is
    the file name while ids (which hold "|") stay out of the way.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from core.models import PhotoInfo
from core.photo_dates import (
    DATE_TAKEN_TAGS,
    camera_name,
    date_taken_from_tags,
    format_display_datetime,
    format_exif_datetime,
    time_offset_from_tags,
)
from core.time_zones import ZONES_BY_KEY, describe_offset, offset_at_local, to_zone
from gui.presenters.date_time_state import (
    MODE_SET,
    build_date_time_state,
    describe_shift,
    keep_clock_message,
)
from services.coordinate_service import (
    parse_coordinate_text,
    parse_latitude_text,
    parse_longitude_text,
    parse_manual_coordinates,
)
from services.date_time_service import date_tag_values, photo_instant, saved_date_tags

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

# The file's own modified date can't be set from a browser (writing a file
# through a handle stamps "now"; a download has no date to keep), so the
# web version writes the photo's three date tags and leaves it out.
FILE_DATE_TAG = "FileModifyDate"


# ----- coordinates -----


def parse(op: str, a: str | None, b: str | None = None) -> str:
    """Coordinate parsing for the Location tab (see exif_worker.js)."""
    try:
        if op == "pair":
            result = parse_coordinate_text(a or "")
            return json.dumps({"ok": True, "result": list(result) if result else None})
        if op == "manual":
            result = parse_manual_coordinates(a or "", b or "")
            return json.dumps({"ok": True, "result": list(result) if result else None})
        if op == "latitude":
            return json.dumps({"ok": True, "result": parse_latitude_text(a or "")})
        if op == "longitude":
            return json.dumps({"ok": True, "result": parse_longitude_text(a or "")})
        return json.dumps({"ok": False, "error": f"unknown op {op}"})
    except ValueError as error:
        return json.dumps({"ok": False, "error": str(error)})


# ----- photos -----


def _info(index: int, photo: dict) -> PhotoInfo:
    tags = {tag: value for tag, value in (photo.get("dates") or {}).items()}
    return PhotoInfo(
        path=Path(str(index)) / photo["name"],
        file_type=Path(photo["name"]).suffix.lstrip(".").lower(),
        date_taken=date_taken_from_tags(tags),
        time_offset=time_offset_from_tags(tags),
        camera=camera_name(photo.get("make"), photo.get("model")),
        date_tags=tags,
    )


def _parse_iso(text) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(str(text)[:19], ISO_FORMAT)
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return value.strftime(ISO_FORMAT) if value is not None else None


def describe_photo(photo: dict) -> dict:
    """
    What the Photo List shows about a photo's dates: when it was taken (ISO,
    for sorting), the app's display text, its zone, and its camera.
    """
    info = _info(0, photo)
    return {
        "dateTaken": _iso(info.date_taken),
        "dateText": format_display_datetime(info.date_taken) if info.date_taken else "",
        "offsetText": describe_offset(info.time_offset, info.date_taken) if info.date_taken and info.time_offset is not None else "",
        "camera": info.camera,
    }


# ----- the Date & Time tab -----


def _shift(reference: PhotoInfo | None, typed: datetime | None, source: PhotoInfo | None, zone) -> timedelta:
    """
    The shift of the moment each photo was taken: from the source photo's
    time when there is one (taken at the same moment as the reference),
    else from the corrected date typed for the reference (in the chosen
    zone, or the photo's own), else none. Ports the desktop's
    date_reference_edited and _current_shift.
    """
    if reference is None or reference.date_taken is None:
        return timedelta(0)
    if source is not None and source.date_taken is not None:
        if zone is None and (source.time_offset is None or reference.time_offset is None):
            return source.date_taken - reference.date_taken
        return photo_instant(source, zone) - photo_instant(reference, zone)
    if typed is not None:
        if zone is None:
            return typed - reference.date_taken
        return (typed - offset_at_local(zone, typed)) - photo_instant(reference, zone)
    return timedelta(0)


def _write_tags(name: str, new: datetime, offset: timedelta | None, own_offset: timedelta | None, computer_offset: timedelta) -> dict:
    """
    The tags a change writes for one photo: the three date tags, the offset
    tags when a zone was chosen, and for a CR3 its QuickTime copies as UTC.
    ExifTool in the browser runs in UTC, so a plain CreateDate would be
    stored as UTC in the CR3's QuickTime tags; the desktop converts from
    the computer's zone. Here the photo's own zone is used (the new one if
    a zone was chosen), else the visitor's.
    """
    tags = {tag: value for tag, value in date_tag_values(new, offset).items() if tag != FILE_DATE_TAG}
    if name.lower().endswith(".cr3"):
        zone_offset = offset if offset is not None else own_offset if own_offset is not None else computer_offset
        utc = format_exif_datetime(new - zone_offset)
        tags["QuickTime:CreateDate"] = utc
        tags["QuickTime:ModifyDate"] = utc
    return tags


def _before_tags(name: str, info: PhotoInfo, computer_offset: timedelta) -> dict:
    """The tags as read, for undo ("" deletes a tag that wasn't there)."""
    saved = {tag: value for tag, value in saved_date_tags(info).items() if tag != FILE_DATE_TAG}
    if name.lower().endswith(".cr3"):
        create = date_taken_from_tags({"DateTimeOriginal": saved.get("CreateDate")})
        if create is not None:
            utc = format_exif_datetime(create - (info.time_offset if info.time_offset is not None else computer_offset))
            saved["QuickTime:CreateDate"] = utc
            saved["QuickTime:ModifyDate"] = utc
    return saved


def date_state(payload: dict) -> dict:
    """
    Everything the Date & Time tab shows and writes, from the tab's state:
    photos {id: {name, dates, make, model}}, selected [ids], mode
    ("shift" | "set" | "zone" | null), reference id, typedReference
    (ISO, the corrected date typed for the reference), setValue (ISO),
    source id or sourceInfo ({name, dates, make, model} for a photo from
    the computer), zoneKey, keepClock, computerOffsetMinutes, now (ISO).
    """
    photos = payload.get("photos") or {}
    ids = list(photos)
    infos = {}
    paths = {}
    for index, photo_id in enumerate(ids):
        info = _info(index, photos[photo_id])
        infos[info.path] = info
        paths[photo_id] = info.path
    ids_by_path = {path: photo_id for photo_id, path in paths.items()}

    selected = [paths[photo_id] for photo_id in payload.get("selected") or [] if photo_id in paths]
    mode = payload.get("mode") or None
    reference = paths.get(payload.get("reference"))
    zone = ZONES_BY_KEY.get(payload.get("zoneKey") or "")
    computer_offset = timedelta(minutes=int(payload.get("computerOffsetMinutes") or 0))
    now = _parse_iso(payload.get("now")) or datetime.now().replace(microsecond=0)

    # The source photo: one in the list, or one chosen from the computer.
    source_path = paths.get(payload.get("source"))
    source_info = infos.get(source_path)
    if source_info is None and payload.get("sourceInfo"):
        source_info = _info(len(ids), payload["sourceInfo"])
        source_path = source_info.path
    if source_info is not None and source_info.date_taken is None:
        source_info = None
        source_path = None

    # The reference photo as the presenter resolves it (earliest selected
    # with a date, the source left out), for the shift.
    exclude = source_path if source_path in selected else None
    dated = sorted(
        [path for path in selected if path != exclude and infos[path].date_taken is not None],
        key=lambda path: (infos[path].date_taken, path.name.casefold()),
    )
    resolved_reference = reference if reference in dated else (dated[0] if dated else None)
    reference_info = infos.get(resolved_reference) if resolved_reference else None
    shift = _shift(reference_info, _parse_iso(payload.get("typedReference")), source_info, zone)

    set_value = _parse_iso(payload.get("setValue"))
    if set_value is None:
        # Set starts from the reference photo's (corrected) date, else noon today.
        set_value = (reference_info.date_taken + shift) if reference_info is not None else now.replace(hour=12, minute=0, second=0)

    state = build_date_time_state(
        selected_paths=selected,
        photo_infos=infos,
        mode=mode,
        reference=reference,
        shift=shift,
        set_value=set_value,
        source=source_path,
        zone=zone,
        keep_clock=bool(payload.get("keepClock")),
        now=now,
        computer_offset=computer_offset,
    )
    chosen_zone = ZONES_BY_KEY.get(state.zone_key) if mode == "zone" or zone is not None else None
    changes = {}
    before = {}
    for path, new in state.plan.new_dates.items():
        photo_id = ids_by_path[path]
        info = infos[path]
        offset = state.plan.new_offsets.get(path)
        changes[photo_id] = _write_tags(path.name, new, offset, info.time_offset, computer_offset)
        before[photo_id] = _before_tags(path.name, info, computer_offset)

    source_card = None
    if source_info is not None:
        source_card = {
            "title": f"Time from {source_info.path.name}",
            "detail": f"{source_info.camera or 'Unknown Camera'} · {format_display_datetime(source_info.date_taken)}",
        }

    return {
        "title": state.title,
        "summary": state.summary,
        "selectedCount": state.selected_count,
        "reference": ids_by_path.get(state.reference),
        "referenceTitle": state.reference_title,
        "referenceDetail": state.reference_detail,
        "referenceIsEarliest": state.reference_is_earliest,
        "referencePosition": state.reference_position,
        "canStepBack": state.can_step_back,
        "canStepForward": state.can_step_forward,
        "correctedReference": _iso(state.corrected_reference),
        "shiftSeconds": int(state.shift.total_seconds()),
        "shiftText": describe_shift(state.shift),
        "sourceSelected": state.source_selected,
        "sourceCard": source_card,
        "setValue": _iso(set_value),
        "rows": [{"name": row.name, "current": row.current, "new": row.new, "kind": row.kind} for row in state.rows],
        "zoneItems": [list(item) for item in state.zone_items],
        "zoneKey": state.zone_key,
        "zoneName": chosen_zone.name if chosen_zone is not None else "",
        "zoneMixed": state.zone_mixed,
        "zoneTooltip": state.zone_tooltip,
        "hint": state.hint,
        "hintTone": state.hint_tone,
        "canApply": state.can_apply,
        "applyLabel": state.apply_label,
        "changes": changes,
        "before": before,
        "newDates": {ids_by_path[path]: format_display_datetime(new) for path, new in state.plan.new_dates.items()},
    }


def convert_set_value(value_iso: str, from_key: str, to_key: str) -> str | None:
    """
    Set: the chosen zone changed, so the date and time shown convert to it
    (the same moment), like the desktop's date_zone_chosen.
    """
    value = _parse_iso(value_iso)
    shown = ZONES_BY_KEY.get(from_key or "")
    zone = ZONES_BY_KEY.get(to_key or "")
    if value is None or shown is None or zone is None:
        return value_iso
    instant = value - offset_at_local(shown, value)
    return _iso(to_zone(instant, zone)[0])


def keep_clock_text(payload: dict) -> str:
    """The "Keep the Clock Time?" question with an example from the selection."""
    photos = payload.get("photos") or {}
    infos = {}
    paths = {}
    for index, photo_id in enumerate(photos):
        info = _info(index, photos[photo_id])
        infos[info.path] = info
        paths[photo_id] = info.path
    selected = [paths[photo_id] for photo_id in payload.get("selected") or [] if photo_id in paths]
    zone = ZONES_BY_KEY.get(payload.get("zoneKey") or "")
    if zone is None:
        return "When enabled, the photos keep their clock times and only get the new time zone."
    return keep_clock_message(infos, selected, zone)


def dates(op: str, payload_json: str) -> str:
    """The worker's one entry point for the Date & Time tab (JSON in, JSON out)."""
    try:
        payload = json.loads(payload_json) if payload_json else {}
        if op == "state":
            return json.dumps({"ok": True, "result": date_state(payload)})
        if op == "describe":
            return json.dumps({"ok": True, "result": describe_photo(payload)})
        if op == "convert_set_value":
            return json.dumps({"ok": True, "result": convert_set_value(payload.get("value"), payload.get("fromKey"), payload.get("toKey"))})
        if op == "keep_clock_text":
            return json.dumps({"ok": True, "result": keep_clock_text(payload)})
        return json.dumps({"ok": False, "error": f"unknown op {op}"})
    except Exception as error:  # noqa: BLE001 - reported to the page, never silent
        return json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"})


__all__ = ["parse", "dates", "date_state", "describe_photo", "convert_set_value", "keep_clock_text", "DATE_TAKEN_TAGS", "MODE_SET"]
