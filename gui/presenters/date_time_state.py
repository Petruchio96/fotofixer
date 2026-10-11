"""
Presenter for the Date & Time tab.

Why this file exists:
    The tab shows the selection's dates, a reference photo (Shift), the list
    of photos and the dates they will get, warnings, and the Apply button.
    Working all that out from the selection and the fields is plain logic,
    kept here without Qt so it is easy to test.

Shift, in short: the reference photo (the earliest selected, unless another
is chosen) gets its correct date and time; every selected photo with a date
moves by the same amount. A photo the correct time was copied from is never
changed. Change Time Zone gives the selected photos another zone: the same
moment by default, or the same clock time (keep_clock).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from core.models import PhotoInfo
from core.photo_dates import format_display_datetime
from core.time_zones import (
    ZONES,
    Zone,
    abbreviation,
    default_zone,
    describe_offset,
    offset_at_local,
    zone_label,
)
from services.date_time_service import (
    DatePlan,
    cameras_in,
    photos_by_date,
    plan_set,
    plan_shift,
    plan_zone_change,
    shifted_clock,
)

# The drop-down's entry for "no time zone" (offered when no photo has one).
NO_ZONE_KEY = ""
MIXED_ZONES_TIP = (
    "The selected photos have more than one time zone. Choosing a time zone "
    "here changes the time zone of all of them."
)

MODE_SHIFT = "shift"
MODE_SET = "set"
MODE_ZONE = "zone"

@dataclass(frozen=True)
class ChangeRow:
    """One line of the "Changing date to:" list."""

    name: str
    current: str
    # Empty when the date stays the same.
    new: str
    # "change", "same", "source" (not changed), or "skipped" (no date).
    kind: str


@dataclass(frozen=True)
class DateTimeState:
    # Selection summary above the tabs (on this tab).
    title: str
    summary: str
    selected_count: int

    # Shift: the reference photo and its corrected date.
    reference: Path | None
    reference_title: str
    reference_detail: str
    reference_is_earliest: bool
    reference_position: str
    can_step_back: bool
    can_step_forward: bool
    corrected_reference: datetime | None
    shift: timedelta

    # The photo with the correct time, when it is one of the selected photos
    # (left out of the change).
    source_selected: bool

    rows: tuple[ChangeRow, ...]
    plan: DatePlan

    # Time zone drop-down: (key, label) per entry, east to west; the entry
    # shown; whether the photos have more than one zone (red, with a warning).
    zone_items: tuple[tuple[str, str], ...]
    zone_key: str
    zone_mixed: bool
    zone_tooltip: str

    hint: str
    hint_tone: str
    can_apply: bool
    apply_label: str


def _photos(count: int) -> str:
    return f"{count} Photo" if count == 1 else f"{count} Photos"


def _photos_lower(count: int) -> str:
    return f"{count} photo" if count == 1 else f"{count} photos"


def describe_shift(shift: timedelta) -> str:
    """timedelta -> "1 day 2 h 14 min later" (or "earlier"); "" for none."""
    seconds = int(shift.total_seconds())
    if not seconds:
        return ""
    total = abs(seconds)
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'' if days == 1 else 's'}")
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if secs:
        parts.append(f"{secs} s")
    return " ".join(parts) + (" later" if seconds > 0 else " earlier")


def build_date_time_state(
    *,
    selected_paths: list[Path],
    photo_infos: Mapping[Path, PhotoInfo],
    mode: str,
    reference: Path | None,
    shift: timedelta,
    set_value: datetime,
    source: Path | None,
    zone: Zone | None = None,
    keep_clock: bool = False,
    now: datetime | None = None,
    computer_offset: timedelta = timedelta(0),
) -> DateTimeState:
    """
    Args:
        selected_paths:
            The photos to change.
        mode:
            MODE_SHIFT, MODE_SET, or None while no kind of change is chosen.
        reference:
            The reference photo chosen with the arrows (None: the earliest).
        shift:
            How far the photos move (Shift). The reference photo's corrected
            date is its date plus this.
        set_value:
            The date and time to give every photo (Set).
        source:
            The photo the correct time was copied from, if any; left out of
            the change when it is also selected.
        zone:
            The time zone chosen in the drop-down, or None if left alone
            (then every photo keeps its own time zone; Change Time Zone
            uses the default zone shown).
        keep_clock:
            Change Time Zone: keep the clock times instead of the moment.
        now / computer_offset:
            The date for zone labels when there is none, and the fallback
            for an unusual offset (see core/time_zones.default_zone).
    """
    now = now or datetime.now().replace(microsecond=0)
    count = len(selected_paths)
    # The photo the time was copied from only matters to Shift.
    source_selected = mode != MODE_ZONE and source is not None and source in selected_paths
    exclude = source if source_selected else None
    dated = photos_by_date(photo_infos, selected_paths, exclude=exclude)

    # Summary above the tabs.
    if count == 0:
        title = "No Photos Selected"
        summary = "Click photos in the Photo List to select them."
    elif count == 1:
        title = "1 Photo Selected"
        info = photo_infos.get(selected_paths[0])
        taken = info.date_taken if info is not None else None
        summary = f"{selected_paths[0].name} · " + (
            f"Taken {format_display_datetime(taken)}" if taken else "No date"
        )
    else:
        title = f"{count} Photos Selected"
        all_dated = photos_by_date(photo_infos, selected_paths)
        dates = (
            f"{format_display_datetime(photo_infos[all_dated[0]].date_taken)} – "
            f"{format_display_datetime(photo_infos[all_dated[-1]].date_taken)}"
            if all_dated
            else "No dates"
        )
        summary = f"{dates} · {', '.join(cameras_in(photo_infos, selected_paths))}"

    # Reference photo (Shift).
    ref = reference if reference in dated else (dated[0] if dated else None)
    ref_index = dated.index(ref) if ref is not None else -1
    ref_info = photo_infos.get(ref) if ref is not None else None
    if ref_info is not None:
        reference_title = f"{ref.name} · {ref_info.camera or 'Unknown Camera'}"
        reference_detail = f"Current Date: {_with_zone(ref_info.date_taken, ref_info.time_offset)}"
        corrected = shifted_clock(ref_info, shift, zone)[0]
    else:
        reference_title = "No selected photo has a date" if count else "No photos selected"
        reference_detail = ""
        corrected = None

    # Time zone drop-down: blank until a photo is selected, then the
    # default comes from the selected photos.
    selected_infos = [photo_infos[path] for path in selected_paths if path in photo_infos]
    default = (
        default_zone(
            [(info.date_taken, info.time_offset) for info in selected_infos],
            computer_offset=computer_offset,
            now=now,
        )
        if selected_infos
        else None
    )
    if mode == MODE_ZONE and zone is None:
        # Change Time Zone always has a zone: the one shown (the photos' most
        # common zone; the computer's when none of them has one).
        zone = default or default_zone([], computer_offset=computer_offset, now=now)
        default = zone

    # What will change.
    if mode == MODE_SHIFT:
        plan = plan_shift(photo_infos, selected_paths, shift, exclude=exclude, zone=zone)
    elif mode == MODE_SET:
        plan = plan_set(photo_infos, selected_paths, set_value, zone=zone)
    elif mode == MODE_ZONE:
        plan = plan_zone_change(photo_infos, selected_paths, zone, keep_clock=keep_clock)
    else:
        # Step 2 not done yet: nothing to change.
        plan = DatePlan()
    rows = _rows(photo_infos, selected_paths, plan, mode, exclude, zone) if mode else []
    # The red warning is about the photos that would change: the selection
    # only (with nothing selected, nothing changes).
    offsets = {
        photo_infos[path].time_offset
        for path in selected_paths
        if path in photo_infos and photo_infos[path].time_offset is not None
    }
    zone_mixed = len(offsets) > 1
    if mode == MODE_SHIFT:
        label_date = corrected or now
    elif mode == MODE_ZONE:
        label_date = (photo_infos[dated[0]].date_taken if dated else None) or now
    else:
        label_date = set_value or now
    items = [(z.key, zone_label(z, label_date)) for z in ZONES]
    if default is None:
        # Nothing selected: an empty box; selected photos without a zone:
        # "No time zone".
        items.insert(0, (NO_ZONE_KEY, "No time zone" if selected_infos else ""))
    shown = zone if zone is not None else default
    zone_key = shown.key if shown is not None else NO_ZONE_KEY
    zone_tooltip = (
        MIXED_ZONES_TIP
        if zone_mixed
        else "The time zone of the date and time above. Leave it to keep each photo's "
        "own time zone; choose one to give it to every photo changed."
    )

    # Hints: why Apply is off, and heads-ups.
    hints: list[str] = []
    tone = "info"
    if count == 0:
        hints.append("Select the photos to change in the Photo List.")
    else:
        # Only a shift assumes every camera's clock was off by the same amount.
        cameras = cameras_in(photo_infos, [path for path in selected_paths if path != exclude])
        if mode == MODE_SHIFT and len(cameras) > 1:
            hints.append(
                f"These photos come from {len(cameras)} cameras: {', '.join(cameras)}. "
                "Check that all of their clocks were off by the same amount."
            )
            tone = "warning"
        if mode in (MODE_SHIFT, MODE_ZONE) and plan.skipped_undated:
            skipped = len(plan.skipped_undated)
            hints.append(
                f"{_photos_lower(skipped)} without a date will be skipped "
                f"(use Set One Date and Time for {'it' if skipped == 1 else 'them'})."
            )
            tone = "warning"
        if mode == MODE_ZONE and dated and not plan.new_dates:
            hints.append("The selected photos are already in this time zone. Choose another one.")

    changing = len(plan.new_dates)
    can_apply = changing > 0
    if mode is None:
        apply_label = "Apply"
    elif mode == MODE_SHIFT:
        apply_label = f"Shift {_photos(len(dated))}" if dated else "Shift Selected Photos"
    elif mode == MODE_ZONE:
        apply_label = (
            f"Change Time Zone of {_photos(len(plan.new_dates))}"
            if plan.new_dates
            else "Change Time Zone of Selected Photos"
        )
    else:
        apply_label = f"Set Date on {_photos(count)}" if count else "Set Date on Selected Photos"

    return DateTimeState(
        title=title,
        summary=summary,
        selected_count=count,
        reference=ref,
        reference_title=reference_title,
        reference_detail=reference_detail,
        reference_is_earliest=ref_index == 0,
        reference_position=f"{ref_index + 1} of {len(dated)}" if ref is not None else "0 of 0",
        can_step_back=ref_index > 0,
        can_step_forward=0 <= ref_index < len(dated) - 1,
        corrected_reference=corrected,
        shift=shift,
        source_selected=source_selected,
        rows=tuple(rows),
        plan=plan,
        zone_items=tuple(items),
        zone_key=zone_key,
        zone_mixed=zone_mixed,
        zone_tooltip=zone_tooltip,
        hint="\n".join(hints),
        hint_tone=tone,
        can_apply=can_apply,
        apply_label=apply_label,
    )


def keep_clock_message(
    photo_infos: Mapping[Path, PhotoInfo],
    selected_paths: list[Path],
    zone: Zone,
) -> str:
    """
    The "Keep the Clock Time?" pop-up's text, with an example from the
    earliest selected photo that has a date and a zone (11:16 am MDT →
    11:16 am CDT, and how far that moves the moment).
    """
    text = "When enabled, the photos keep their clock times and only get the new time zone"
    for path in photos_by_date(photo_infos, selected_paths):
        info = photo_infos[path]
        if info.time_offset is None:
            continue
        clock = format_display_datetime(info.date_taken).split(" ", 1)[1]
        new_offset = offset_at_local(zone, info.date_taken)
        moved = describe_shift(info.time_offset - new_offset).replace(" later", "").replace(" earlier", "")
        example = (
            f"{clock} {describe_offset(info.time_offset, info.date_taken)} → "
            f"{clock} {abbreviation(zone, info.date_taken)}"
        )
        if moved:
            return (
                f"{text}: {example}. That moves the moment they were taken by the "
                f"difference between the zones ({moved} here)."
            )
        return f"{text}: {example}."
    return f"{text}, which moves the moment they were taken by the difference between the zones."


def _with_zone(value: datetime | None, offset: timedelta | None) -> str:
    """'10/03/2026 9:14:02am MDT'; a photo without a zone, just the date."""
    text = format_display_datetime(value)
    if value is None or offset is None:
        return text
    return f"{text} {describe_offset(offset, value)}"


def _rows(
    photo_infos: Mapping[Path, PhotoInfo],
    selected_paths: list[Path],
    plan: DatePlan,
    mode: str,
    exclude: Path | None,
    zone: Zone | None,
) -> list[ChangeRow]:
    """
    Every selected photo with its current date, and its new date when it
    changes: in date order, then the source photo and photos without a date.
    Dates show the photo's time zone when it has one (or is getting one).
    """
    def current(path: Path) -> str:
        info = photo_infos.get(path)
        if info is None:
            return format_display_datetime(None)
        return _with_zone(info.date_taken, info.time_offset)

    def new_text(path: Path, new: datetime) -> str:
        info = photo_infos.get(path)
        if zone is not None:
            text = f"{format_display_datetime(new)} {abbreviation(zone, new)}"
            if mode == MODE_ZONE and info is not None and info.time_offset is None:
                # No zone before, so no known moment: the clock time is kept.
                text += " (time kept, time zone added)"
            return text
        return _with_zone(new, info.time_offset if info is not None else None)

    ordered = photos_by_date(photo_infos, selected_paths, exclude=exclude)
    undated = [
        path for path in selected_paths
        if path != exclude and path not in ordered
    ]
    rows = []
    for path in ordered + (undated if mode == MODE_SET else []):
        new = plan.new_dates.get(path)
        rows.append(
            ChangeRow(
                name=path.name,
                current=current(path),
                new=new_text(path, new) if new is not None else "",
                kind="change" if new is not None else "same",
            )
        )
    if exclude is not None:
        rows.append(ChangeRow(exclude.name, current(exclude), "Source, not changed", "source"))
    if mode in (MODE_SHIFT, MODE_ZONE):
        rows.extend(ChangeRow(path.name, "No date", "Skipped", "skipped") for path in undated)
    return rows
