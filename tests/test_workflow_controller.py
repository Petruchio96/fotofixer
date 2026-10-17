import unittest
import tempfile
from pathlib import Path

from core.models import GpsCoordinates, PhotoInfo
from services.models import ApplyPreparation, WorkflowSession
from services.workflow_controller import (
    clear_gps_workflow,
    clear_source_workflow,
    execute_apply_workflow,
    load_source_workflow,
    prepare_apply_workflow,
    refresh_photo_workflow,
    restore_gps_states_workflow,
)
from services.workflow_facade import PhotoWorkflowFacade


class StubLoader:
    def __init__(self, photo_infos: dict[Path, PhotoInfo]) -> None:
        self.photo_infos = photo_infos
        self.calls: list[Path] = []

    def load_photo_info(self, path: Path) -> PhotoInfo:
        self.calls.append(path)
        return self.photo_infos[path]


class StubWriter:
    def __init__(self, failing_paths: set[Path] | None = None) -> None:
        self.calls: list[tuple[Path, float, float]] = []
        self.clear_calls: list[Path] = []
        self.failing_paths = failing_paths or set()

    def write_gps(self, path: Path, latitude: float, longitude: float, altitude="keep") -> None:
        self.calls.append((path, latitude, longitude))
        if path in self.failing_paths:
            raise RuntimeError("boom")

    def clear_gps(self, path: Path) -> None:
        self.clear_calls.append(path)
        if path in self.failing_paths:
            raise RuntimeError("boom")


class WorkflowControllerTests(unittest.TestCase):
    def test_refresh_photo_workflow_preserves_source_state(self) -> None:
        source = Path("/tmp/source.jpg")
        target_photo = Path("/tmp/target-photo.jpg")
        source_info = PhotoInfo(
            path=source,
            file_type="JPG",
            current_latitude=40.5,
            current_longitude=-111.8,
        )
        loader = StubLoader(
            {
                target_photo: PhotoInfo(path=target_photo, file_type="JPG"),
            }
        )
        session = WorkflowSession(
            selected_paths=[target_photo],
            target_paths=[target_photo],
            source_photo_info=source_info,
            source_photo_path=source,
        )

        refreshed = refresh_photo_workflow(session, loader)

        self.assertEqual(refreshed.selected_paths, [target_photo])
        self.assertEqual(refreshed.target_paths, [target_photo])
        self.assertEqual(refreshed.thumbnail_items, [])
        self.assertEqual(refreshed.source_photo_path, source)
        self.assertEqual(refreshed.source_photo_info, source_info)

    def test_load_source_workflow_sets_session_and_returns_success_message(self) -> None:
        source = Path("/tmp/source.jpg")
        source_info = PhotoInfo(
            path=source,
            file_type="JPG",
            current_latitude=40.5,
            current_longitude=-111.8,
        )
        session = WorkflowSession()
        loader = StubLoader({source: source_info})

        result = load_source_workflow(session, source, loader)

        self.assertEqual(result.session.source_photo_path, source)
        self.assertEqual(result.session.source_photo_info, source_info)
        self.assertEqual(result.message.text, "Source photo loaded and ready to apply.")
        self.assertEqual(result.message.tone, "success")

    def test_clear_source_workflow_clears_session_and_returns_message(self) -> None:
        session = WorkflowSession(
            source_photo_path=Path("/tmp/source.jpg"),
            source_photo_info=PhotoInfo(path=Path("/tmp/source.jpg"), file_type="JPG"),
        )

        message = clear_source_workflow(session)

        self.assertIsNone(session.source_photo_path)
        self.assertIsNone(session.source_photo_info)
        self.assertEqual(message.text, "Source photo cleared.")
        self.assertEqual(message.tone, "info")

    def test_prepare_apply_workflow_uses_session_state(self) -> None:
        source = Path("/tmp/source.jpg")
        target_photo = Path("/tmp/target-photo.jpg")
        session = WorkflowSession(
            source_photo_path=source,
            source_photo_info=PhotoInfo(
                path=source,
                file_type="JPG",
                current_latitude=40.5,
                current_longitude=-111.8,
            ),
            loaded_photo_infos={
                target_photo: PhotoInfo(
                    path=target_photo,
                    file_type="JPG",
                    current_latitude=41.0,
                    current_longitude=-112.0,
                )
            },
        )

        preparation = prepare_apply_workflow(
            session=session,
            selected_paths=[source, target_photo],
            using_photo_source=True,
            latitude_text="",
            longitude_text="",
        )

        self.assertEqual(preparation.target_paths, [target_photo])
        self.assertEqual(
            [entry.display_text() for entry in preparation.overwrite_entries],
            ["target-photo.jpg — 41.000000, -112.000000"],
        )
        self.assertEqual(preparation.coordinates, GpsCoordinates(40.5, -111.8))

    def test_execute_apply_workflow_refreshes_session_after_write(self) -> None:
        target_photo = Path("/tmp/target-photo.jpg")
        session = WorkflowSession(
            selected_paths=[target_photo],
            source_photo_path=Path("/tmp/source.jpg"),
        )
        loader = StubLoader(
            {
                target_photo: PhotoInfo(
                    path=target_photo,
                    file_type="JPG",
                    current_latitude=40.5,
                    current_longitude=-111.8,
                )
            }
        )
        writer = StubWriter()

        result = execute_apply_workflow(
            session=session,
            preparation=ApplyPreparation(
                target_paths=[target_photo],
                coordinates=GpsCoordinates(40.5, -111.8),
            ),
            writer=writer,
            loader=loader,
        )

        self.assertEqual(writer.calls, [(target_photo, 40.5, -111.8)])
        self.assertEqual(result.execution_result.success_count, 1)
        self.assertEqual(result.session.selected_paths, [target_photo])
        self.assertEqual(result.session.source_photo_path, Path("/tmp/source.jpg"))
        self.assertIn(target_photo, result.session.loaded_photo_infos)

    def test_restore_gps_states_workflow_writes_and_clears_then_refreshes(self) -> None:
        write_path = Path("/tmp/write.jpg")
        clear_path = Path("/tmp/clear.jpg")
        session = WorkflowSession(selected_paths=[write_path, clear_path])
        loader = StubLoader(
            {
                write_path: PhotoInfo(
                    path=write_path,
                    file_type="JPG",
                    current_latitude=40.5,
                    current_longitude=-111.8,
                ),
                clear_path: PhotoInfo(path=clear_path, file_type="JPG"),
            }
        )
        writer = StubWriter()

        refreshed = restore_gps_states_workflow(
            session=session,
            states={
                write_path: (40.5, -111.8),
                clear_path: (None, None),
            },
            writer=writer,
            loader=loader,
        )

        self.assertEqual(writer.calls, [(write_path, 40.5, -111.8)])
        self.assertEqual(writer.clear_calls, [clear_path])
        self.assertEqual(refreshed.session.selected_paths, [write_path, clear_path])
        self.assertEqual(refreshed.execution_result.successful_paths, [write_path, clear_path])
        self.assertEqual(loader.calls, [write_path, clear_path])

    def test_restore_gps_states_workflow_continues_after_a_failure(self) -> None:
        first = Path("/tmp/first.jpg")
        failing = Path("/tmp/failing.jpg")
        last = Path("/tmp/last.jpg")
        loader = StubLoader(
            {path: PhotoInfo(path=path, file_type="JPG") for path in (first, failing, last)}
        )
        writer = StubWriter(failing_paths={failing})

        result = restore_gps_states_workflow(
            session=WorkflowSession(selected_paths=[first, failing, last]),
            states={first: (1.0, 2.0), failing: (None, None), last: (3.0, 4.0)},
            writer=writer,
            loader=loader,
        )

        self.assertEqual(result.execution_result.successful_paths, [first, last])
        self.assertEqual(result.execution_result.failed_paths, ["failing.jpg: boom"])
        self.assertEqual(writer.calls, [(first, 1.0, 2.0), (last, 3.0, 4.0)])

    def test_clear_gps_workflow_clears_every_file_and_reports_failures(self) -> None:
        first = Path("/tmp/first.jpg")
        failing = Path("/tmp/failing.jpg")
        last = Path("/tmp/last.jpg")
        loader = StubLoader(
            {path: PhotoInfo(path=path, file_type="JPG") for path in (first, failing, last)}
        )
        writer = StubWriter(failing_paths={failing})
        session = WorkflowSession(
            selected_paths=[first, failing, last],
            target_paths=[first, failing, last],
        )

        result = clear_gps_workflow(
            session=session,
            target_paths=[first, failing, last],
            writer=writer,
            loader=loader,
        )

        self.assertEqual(writer.clear_calls, [first, failing, last])
        self.assertEqual(result.execution_result.successful_paths, [first, last])
        self.assertEqual(result.execution_result.failed_paths, ["failing.jpg: boom"])
        self.assertEqual(result.session.target_paths, [first, failing, last])
        self.assertEqual(loader.calls, [first, failing, last])


class PhotoWorkflowFacadeTests(unittest.TestCase):
    def test_facade_refresh_uses_configured_loader(self) -> None:
        target_photo = Path("/tmp/target-photo.jpg")
        loader = StubLoader(
            {
                target_photo: PhotoInfo(
                    path=target_photo,
                    file_type="JPG",
                    current_latitude=40.5,
                    current_longitude=-111.8,
                )
            }
        )
        facade = PhotoWorkflowFacade(loader=loader, writer=StubWriter())
        session = WorkflowSession(selected_paths=[target_photo])

        refreshed = facade.refresh_photo_workflow(session)

        self.assertEqual(loader.calls, [target_photo])
        self.assertIn(target_photo, refreshed.loaded_photo_infos)

    def test_facade_execute_apply_uses_configured_writer_and_loader(self) -> None:
        target_photo = Path("/tmp/target-photo.jpg")
        loader = StubLoader(
            {
                target_photo: PhotoInfo(
                    path=target_photo,
                    file_type="JPG",
                    current_latitude=40.5,
                    current_longitude=-111.8,
                )
            }
        )
        writer = StubWriter()
        facade = PhotoWorkflowFacade(loader=loader, writer=writer)
        session = WorkflowSession(selected_paths=[target_photo])

        result = facade.execute_apply_workflow(
            session=session,
            preparation=ApplyPreparation(
                target_paths=[target_photo],
                coordinates=GpsCoordinates(40.5, -111.8),
            ),
        )

        self.assertEqual(writer.calls, [(target_photo, 40.5, -111.8)])
        self.assertEqual(loader.calls, [target_photo])
        self.assertEqual(result.execution_result.success_count, 1)

    def test_facade_reuses_metadata_cache_for_unchanged_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target_photo = Path(temp_dir) / "target-photo.jpg"
            target_photo.write_text("photo data", encoding="utf-8")
            loader = StubLoader(
                {
                    target_photo: PhotoInfo(
                        path=target_photo,
                        file_type="JPG",
                        current_latitude=40.5,
                        current_longitude=-111.8,
                    )
                }
            )
            facade = PhotoWorkflowFacade(loader=loader, writer=StubWriter())
            session = WorkflowSession(selected_paths=[target_photo])

            facade.refresh_photo_workflow(session)
            facade.refresh_photo_workflow(session)

        self.assertEqual(loader.calls, [target_photo])

    def test_facade_restore_gps_states_uses_configured_writer_and_loader(self) -> None:
        target_photo = Path("/tmp/target-photo.jpg")
        loader = StubLoader(
            {
                target_photo: PhotoInfo(
                    path=target_photo,
                    file_type="JPG",
                    current_latitude=40.5,
                    current_longitude=-111.8,
                )
            }
        )
        writer = StubWriter()
        facade = PhotoWorkflowFacade(loader=loader, writer=writer)
        session = WorkflowSession(selected_paths=[target_photo])

        refreshed = facade.restore_gps_states_workflow(
            session=session,
            states={target_photo: (40.5, -111.8)},
        )

        self.assertEqual(writer.calls, [(target_photo, 40.5, -111.8)])
        self.assertIn(target_photo, refreshed.session.loaded_photo_infos)

    def test_facade_clear_gps_uses_configured_writer_and_loader(self) -> None:
        target_photo = Path("/tmp/target-photo.jpg")
        loader = StubLoader({target_photo: PhotoInfo(path=target_photo, file_type="JPG")})
        writer = StubWriter()
        facade = PhotoWorkflowFacade(loader=loader, writer=writer)

        result = facade.clear_gps_workflow(
            session=WorkflowSession(selected_paths=[target_photo]),
            target_paths=[target_photo],
        )

        self.assertEqual(writer.clear_calls, [target_photo])
        self.assertEqual(result.execution_result.successful_paths, [target_photo])


if __name__ == "__main__":
    unittest.main()
