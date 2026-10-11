"""
Single backend workflow entry point for frontend code.
"""

from __future__ import annotations

from pathlib import Path

from core.exiftool_wrapper import ExifToolWrapper
from core.models import EmbeddedPreview, PhotoInfo
from core.photo_loader import PhotoLoader
from services.models import (
    ApplyPreparation,
    ApplyWorkflowResult,
    SourceLoadResult,
    WorkflowMessage,
    WorkflowSession,
)
from services.photo_metadata_cache import PhotoMetadataCache
from services.photo_service import load_source_photo_info
from services.workflow_controller import (
    clear_gps_workflow,
    clear_source_workflow,
    execute_apply_workflow,
    load_source_workflow,
    prepare_apply_workflow,
    refresh_photo_workflow,
    restore_gps_states_workflow,
    write_date_tags_workflow,
)


class PhotoWorkflowFacade:
    """
    Backend workflow API used by the desktop frontend.
    """

    def __init__(self, loader=None, writer=None, metadata_cache=None) -> None:
        self.writer = writer or ExifToolWrapper()
        self.loader = loader or PhotoLoader(self.writer)
        self.metadata_cache = metadata_cache or PhotoMetadataCache()

    def read_photo_info(self, path: Path) -> PhotoInfo:
        """
        Read one photo's metadata, for example to use its GPS location.
        """
        return load_source_photo_info(path, self.loader)

    def read_embedded_previews(self, paths: list[Path]) -> dict[Path, EmbeddedPreview]:
        """
        Return the built-in previews of RAW files, for thumbnails. Files
        without a preview are left out.
        """
        return self.writer.read_embedded_previews(paths)

    def read_small_previews(self, paths: list[Path]) -> dict[Path, EmbeddedPreview]:
        """
        Return the small thumbnails stored near the start of photo files
        (JPEG EXIF thumbnails). Reading them avoids reading whole photos,
        which is slow for large photos on network shares.
        """
        return self.writer.read_embedded_previews(paths, tags=("ThumbnailImage",))

    def refresh_photo_workflow(self, session: WorkflowSession) -> WorkflowSession:
        return refresh_photo_workflow(session, self.loader, self.metadata_cache)

    def load_source_workflow(
        self,
        session: WorkflowSession,
        source_path: Path,
    ) -> SourceLoadResult:
        return load_source_workflow(session, source_path, self.loader)

    def clear_source_workflow(self, session: WorkflowSession) -> WorkflowMessage:
        return clear_source_workflow(session)

    def prepare_apply_workflow(
        self,
        *,
        session: WorkflowSession,
        selected_paths: list[Path],
        using_photo_source: bool,
        latitude_text: str,
        longitude_text: str,
    ) -> ApplyPreparation:
        return prepare_apply_workflow(
            session=session,
            selected_paths=selected_paths,
            using_photo_source=using_photo_source,
            latitude_text=latitude_text,
            longitude_text=longitude_text,
        )

    def execute_apply_workflow(
        self,
        *,
        session: WorkflowSession,
        preparation: ApplyPreparation,
        on_progress=None,
    ) -> ApplyWorkflowResult:
        return execute_apply_workflow(
            session=session,
            preparation=preparation,
            writer=self.writer,
            loader=self.loader,
            cache=self.metadata_cache,
            on_progress=on_progress,
        )

    def clear_gps_workflow(
        self,
        *,
        session: WorkflowSession,
        target_paths: list[Path],
        on_progress=None,
    ) -> ApplyWorkflowResult:
        return clear_gps_workflow(
            session=session,
            target_paths=target_paths,
            writer=self.writer,
            loader=self.loader,
            cache=self.metadata_cache,
            on_progress=on_progress,
        )

    def restore_gps_states_workflow(
        self,
        *,
        session: WorkflowSession,
        states: dict[Path, tuple[float | None, float | None]],
        on_progress=None,
    ) -> ApplyWorkflowResult:
        return restore_gps_states_workflow(
            session=session,
            states=states,
            writer=self.writer,
            loader=self.loader,
            cache=self.metadata_cache,
            on_progress=on_progress,
        )

    def write_date_tags_workflow(
        self,
        *,
        session: WorkflowSession,
        values_by_path: dict[Path, dict[str, str | None]],
        on_progress=None,
    ) -> ApplyWorkflowResult:
        """
        Write date tags to photos (see services/date_time_service.py for
        building them) and refresh the session.
        """
        return write_date_tags_workflow(
            session=session,
            values_by_path=values_by_path,
            writer=self.writer,
            loader=self.loader,
            cache=self.metadata_cache,
            on_progress=on_progress,
        )
