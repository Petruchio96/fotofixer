import unittest
from pathlib import Path

from core.models import GpsCoordinates, PhotoInfo
from services.gps_workflow_service import apply_gps_to_paths, prepare_apply_gps, write_gps_values
from services.models import SourceResolution


class StubWriter:
    def __init__(self, failing_paths: set[Path] | None = None) -> None:
        self.calls: list[tuple] = []
        self.failing_paths = failing_paths or set()
        self.clears: list[Path] = []

    def clear_gps(self, path: Path) -> None:
        self.clears.append(path)

    def write_gps(self, path: Path, latitude: float, longitude: float, altitude="keep") -> None:
        self.calls.append((path, latitude, longitude) if altitude == "keep" else (path, latitude, longitude, altitude))
        if path in self.failing_paths:
            raise RuntimeError("boom")


class GpsWorkflowServiceTests(unittest.TestCase):
    def test_restore_gps_states_writes_an_altitude_when_the_state_has_one(self) -> None:
        from services.gps_workflow_service import restore_gps_states
        a, b, c = Path("/p/a.jpg"), Path("/p/b.jpg"), Path("/p/c.jpg")
        writer = StubWriter()
        d = Path("/p/d.jpg")
        restore_gps_states({a: (40.5, -111.8), b: (None, None), c: (40.7, -111.6, 2050.0), d: (40.8, -111.5, None)}, writer=writer)
        # Two values leave the altitude alone; None in the third clears it.
        self.assertEqual(writer.calls, [(a, 40.5, -111.8), (c, 40.7, -111.6, 2050.0), (d, 40.8, -111.5, None)])

    def test_write_gps_values_gives_each_photo_its_own_position(self) -> None:
        a, b, c = Path("/p/a.jpg"), Path("/p/b.jpg"), Path("/p/c.jpg")
        writer = StubWriter(failing_paths={b})
        progress = []

        result = write_gps_values(
            {a: (40.5, -111.8, 2050.0), b: (40.6, -111.7, None), c: (40.7, -111.6, -3.0)},
            writer=writer,
            on_progress=lambda done, total: progress.append((done, total)),
        )

        # No altitude: the plain call, so writers without the parameter keep working.
        self.assertEqual(writer.calls, [(a, 40.5, -111.8, 2050.0), (b, 40.6, -111.7), (c, 40.7, -111.6, -3.0)])
        self.assertEqual(result.successful_paths, [a, c])
        self.assertEqual(result.failed_paths, ["b.jpg: boom"])
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])

    def test_prepare_apply_gps_rejects_empty_photo_selection(self) -> None:
        preparation = prepare_apply_gps(
            selected_paths=[],
            using_photo_source=False,
            source_photo_path=None,
            source_resolution=SourceResolution(
                coordinates=GpsCoordinates(40.5, -111.8)
            ),
            photo_info_by_path={},
        )

        self.assertEqual(
            preparation.error_message,
            "Select one or more photos before applying GPS.",
        )

    def test_prepare_apply_gps_collects_overwrite_entries(self) -> None:
        source_path = Path("/tmp/source.jpg")
        target_path = Path("/tmp/target.jpg")
        preparation = prepare_apply_gps(
            selected_paths=[source_path, target_path],
            using_photo_source=True,
            source_photo_path=source_path,
            source_resolution=SourceResolution(
                coordinates=GpsCoordinates(40.5, -111.8)
            ),
            photo_info_by_path={
                target_path: PhotoInfo(
                    path=target_path,
                    file_type="JPG",
                    current_latitude=41.0,
                    current_longitude=-112.0,
                )
            },
        )

        self.assertEqual(preparation.target_paths, [target_path])
        self.assertEqual(
            [entry.display_text() for entry in preparation.overwrite_entries],
            ["target.jpg — 41.000000, -112.000000"],
        )

    def test_apply_gps_to_paths_collects_successes_and_failures(self) -> None:
        first = Path("/tmp/first.jpg")
        second = Path("/tmp/second.jpg")
        writer = StubWriter(failing_paths={second})

        result = apply_gps_to_paths(
            [first, second],
            latitude=40.5,
            longitude=-111.8,
            writer=writer,
        )

        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.failed_paths, ["second.jpg: boom"])
        self.assertEqual(
            writer.calls,
            [
                (first, 40.5, -111.8),
                (second, 40.5, -111.8),
            ],
        )


if __name__ == "__main__":
    unittest.main()
