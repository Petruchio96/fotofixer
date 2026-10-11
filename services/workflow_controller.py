"""
Controller-style use cases for the desktop workflow.
"""

from __future__ import annotations

from pathlib import Path

from services.gps_workflow_service import (
    apply_gps_to_paths,
    clear_gps_from_paths,
    prepare_apply_gps,
    restore_gps_states,
    write_date_tags_to_paths,
)
from services.models import (
    ApplyPreparation,
    ApplyWorkflowResult,
    SourceLoadResult,
    WorkflowMessage,
    WorkflowSession,
)
from services.photo_service import load_source_photo_info, refresh_photo_session
from services.source_service import resolve_active_source


def refresh_photo_workflow(
    session: WorkflowSession,
    loader,
    cache=None,
) -> WorkflowSession:
    """
    Refresh the selected-photo portion of the workflow while preserving source state.
    """
    photo_session = refresh_photo_session(session.selected_paths, loader, cache)
    photo_session.target_paths = list(session.target_paths)
    photo_session.source_photo_info = session.source_photo_info
    photo_session.source_photo_path = session.source_photo_path
    return photo_session


def load_source_workflow(
    session: WorkflowSession,
    source_path: Path,
    loader,
) -> SourceLoadResult:
    """
    Load a source photo into the shared workflow session and return UI-facing feedback.
    """
    info = load_source_photo_info(source_path, loader)
    session.source_photo_info = info
    session.source_photo_path = source_path

    if info.gps_error:
        return SourceLoadResult(
            session=session,
            message=WorkflowMessage(
                text=f"Source photo could not load GPS data: {info.gps_error}",
                tone="error",
            ),
        )

    if info.current_latitude is None or info.current_longitude is None:
        return SourceLoadResult(
            session=session,
            message=WorkflowMessage(
                text="Source photo loaded, but it does not contain GPS coordinates.",
                tone="info",
            ),
        )

    return SourceLoadResult(
        session=session,
        message=WorkflowMessage(
            text="Source photo loaded and ready to apply.",
            tone="success",
        ),
    )


def clear_source_workflow(session: WorkflowSession) -> WorkflowMessage:
    """
    Clear the active source photo from the workflow session.
    """
    session.source_photo_info = None
    session.source_photo_path = None
    return WorkflowMessage(text="Source photo cleared.", tone="info")


def prepare_apply_workflow(
    *,
    session: WorkflowSession,
    selected_paths: list[Path],
    using_photo_source: bool,
    latitude_text: str,
    longitude_text: str,
) -> ApplyPreparation:
    """
    Build the apply preparation result from the current workflow session.
    """
    source_resolution = resolve_active_source(
        using_photo_source=using_photo_source,
        source_photo_info=session.source_photo_info,
        latitude_text=latitude_text,
        longitude_text=longitude_text,
    )
    return prepare_apply_gps(
        selected_paths=selected_paths,
        using_photo_source=using_photo_source,
        source_photo_path=session.source_photo_path,
        source_resolution=source_resolution,
        photo_info_by_path=session.loaded_photo_infos,
    )


def execute_apply_workflow(
    *,
    session: WorkflowSession,
    preparation: ApplyPreparation,
    writer,
    loader,
    cache=None,
    on_progress=None,
) -> ApplyWorkflowResult:
    """
    Execute an apply action and refresh selected-photo state afterward.
    """
    coordinates = preparation.coordinates
    if coordinates is None:
        raise ValueError("Apply preparation must include coordinates before execution.")

    execution_result = apply_gps_to_paths(
        preparation.target_paths,
        latitude=coordinates.latitude,
        longitude=coordinates.longitude,
        writer=writer,
        on_progress=on_progress,
    )
    refreshed_session = refresh_photo_workflow(session, loader, cache)
    return ApplyWorkflowResult(
        session=refreshed_session,
        execution_result=execution_result,
    )


def clear_gps_workflow(
    *,
    session: WorkflowSession,
    target_paths: list[Path],
    writer,
    loader,
    cache=None,
    on_progress=None,
) -> ApplyWorkflowResult:
    """
    Clear GPS from the target files and refresh selected-photo state afterward.
    """
    execution_result = clear_gps_from_paths(target_paths, writer=writer, on_progress=on_progress)
    refreshed_session = refresh_photo_workflow(session, loader, cache)
    return ApplyWorkflowResult(
        session=refreshed_session,
        execution_result=execution_result,
    )


def restore_gps_states_workflow(
    *,
    session: WorkflowSession,
    states: dict[Path, tuple[float | None, float | None]],
    writer,
    loader,
    cache=None,
    on_progress=None,
) -> ApplyWorkflowResult:
    """
    Restore GPS metadata states and refresh selected-photo workflow state.

    Every file is attempted even if some fail; failures are in the result.
    """
    execution_result = restore_gps_states(states, writer=writer, on_progress=on_progress)
    refreshed_session = refresh_photo_workflow(session, loader, cache)
    return ApplyWorkflowResult(
        session=refreshed_session,
        execution_result=execution_result,
    )


def write_date_tags_workflow(
    *,
    session: WorkflowSession,
    values_by_path: dict[Path, dict[str, str | None]],
    writer,
    loader,
    cache=None,
    on_progress=None,
) -> ApplyWorkflowResult:
    """
    Write date tags (a date change, or its undo/redo) and refresh the
    selected-photo state afterward. Every file is attempted even if some
    fail; failures are in the result.
    """
    execution_result = write_date_tags_to_paths(values_by_path, writer=writer, on_progress=on_progress)
    if cache is not None:
        # The file's modified time is part of the cache key and was just set
        # (undo can set it back to an earlier value): read these files again.
        cache.forget(list(values_by_path))
    refreshed_session = refresh_photo_workflow(session, loader, cache)
    return ApplyWorkflowResult(
        session=refreshed_session,
        execution_result=execution_result,
    )
