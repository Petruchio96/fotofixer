"""
Wrapper around ExifTool for reading and writing GPS metadata.

Why this file exists:
    We do not want GUI code directly calling subprocess commands all over the
    project. This wrapper gives us one clean place to:
    1. check whether ExifTool exists
    2. read and write GPS metadata
    3. read the preview images embedded in RAW files, for thumbnails

Why ExifTool:
    ExifTool is the most reliable way to work with metadata across JPG and many
    RAW formats like CR2, CR3, and DNG.

Why one long-running ExifTool process:
    Starting ExifTool (a Perl program) takes far longer than the GPS read or
    write itself. ExifTool's "-stay_open" mode keeps one process running and
    accepts one command after another through stdin, so batches of photos
    no longer pay the startup cost for every file.
"""

from __future__ import annotations

import atexit
import base64
import itertools
import json
import queue
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import IO

from core.file_types import may_hold_preview
from core.models import EmbeddedPreview
from core.photo_dates import ALL_DATE_TAGS
from core.process_guard import NO_WINDOW_FLAGS, start_guarded_process, stop_process_tree
from core.runtime_paths import default_exiftool_executable

# Read along with GPS: the date tags and the camera (Make and Model).
METADATA_READ_OPTIONS = [f"-{tag}" for tag in (*ALL_DATE_TAGS, "Make", "Model")]
# The altitude (metres, with -n; GPSAltitudeRef 1 = below sea level), read
# so that undoing a geotag from a GPS track can put the original back.
ALTITUDE_READ_OPTIONS = ["-GPSAltitude", "-GPSAltitudeRef"]

# write_gps's altitude default: leave the photo's altitude as it is.
KEEP_ALTITUDE = object()

# Embedded JPEG previews to try for RAW thumbnails, smallest/fastest first.
# Many RAW files have a small ThumbnailImage; others only have a larger
# PreviewImage or a full-size JpgFromRaw.
EMBEDDED_PREVIEW_TAGS = ("ThumbnailImage", "PreviewImage", "JpgFromRaw")

# Upper bound on thumbnails remembered between the GPS read and the thumbnail
# request (see read_gps_many). Entries are removed as soon as they are used.
MAX_REMEMBERED_THUMBNAILS = 2048

# Marker for "no remembered entry", distinct from None ("has no thumbnail").
_NOT_REMEMBERED = object()

# How long to wait for one ExifTool command before giving up. Large RAW batches
# can take a while, so this is generous; it only guards against a hung process.
COMMAND_TIMEOUT_SECONDS = 300


class ExifToolWrapper:
    """
    Small helper class for interacting with the external 'exiftool' program.

    This class keeps command construction and subprocess handling in one place,
    which makes the rest of the application simpler and easier to test.
    """

    def __init__(self, executable: str | None = None) -> None:
        """
        Store the executable name or path.

        Args:
            executable:
                The command name or full path to ExifTool.
                Usually just "exiftool" if it is installed in PATH.
        """
        self.executable = executable or default_exiftool_executable()

        # When True, an untouched copy of each file is saved next to it as
        # "<name>_original.<ext>" (IMG_0995.jpg -> IMG_0995_original.jpg) the
        # first time its GPS changes, if it had GPS before. Later changes leave
        # that copy alone, so it always holds the original.
        self.keep_backups = False
        # Backups made since take_created_backups() was last called.
        self._created_backups: list[Path] = []

        # The long-running ExifTool process is started on first use.
        self._process: subprocess.Popen | None = None
        self._stdout_lines: queue.Queue[str | None] = queue.Queue()
        self._stderr_lines: queue.Queue[str | None] = queue.Queue()
        self._command_numbers = itertools.count(1)
        # Only one command may talk to the process at a time.
        self._lock = threading.Lock()
        self._registered_atexit = False

        # Small RAW thumbnails captured during read_gps_many(), waiting for
        # read_embedded_previews() to pick them up. Keyed by (path, modified
        # time, size) so a changed file never gets a stale thumbnail. None means
        # "this file has no small thumbnail", which is also worth remembering.
        self._remembered_thumbnails: dict[
            tuple[Path, int, int], EmbeddedPreview | None
        ] = {}

    def is_available(self) -> bool:
        """
        Check whether ExifTool can be found on the system PATH.

        Returns:
            True if ExifTool is available, otherwise False.
        """
        return shutil.which(self.executable) is not None

    def read_gps(self, path: Path) -> dict:
        """
        Read GPS metadata from a file using ExifTool and return it in a cleaner form.

        Why we use "-n":
            By default, ExifTool may return GPS values as nicely formatted text
            like:
                40 deg 29' 10.77" N
            That is fine for humans, but not ideal for a program.

            The "-n" option tells ExifTool to return raw numeric values instead,
            which are much easier for our application to use. For example:
                40.486325
                -111.813414

        Args:
            path:
                Path to the image file we want to inspect.

        Returns:
            A dictionary with these keys:
                "latitude": float | None
                "longitude": float | None

            If the image has no GPS data, the values will be None.

        Raises:
            RuntimeError:
                If ExifTool fails, such as when the file cannot be read.
        """
        output = self._run(
            ["-json", "-n", "-GPSLatitude", "-GPSLongitude", *ALTITUDE_READ_OPTIONS, *METADATA_READ_OPTIONS],
            [path],
            "Failed to read metadata.",
        )
        data = json.loads(output)
        return _metadata_from_record(data[0] if data else {})

    def read_gps_many(self, paths: list[Path]) -> dict[Path, dict]:
        """
        Read GPS metadata for many files with one ExifTool command per file type.

        Why RAW files are read separately:
            While ExifTool has a RAW file open for its GPS data, it can also
            return the small thumbnail stored inside it. Remembering that
            thumbnail saves opening every RAW file a second time when the
            thumbnail grid is drawn, which matters most for files on a
            network share. JPEGs don't need this; their thumbnails are made
            from the image itself.
        """
        if not paths:
            return {}

        raw_paths = [path for path in paths if may_hold_preview(path)]
        other_paths = [path for path in paths if not may_hold_preview(path)]

        gps_by_path: dict[Path, dict] = {}
        if other_paths:
            gps_by_path.update(self._read_gps_records(other_paths, with_thumbnails=False))
        if raw_paths:
            gps_by_path.update(self._read_gps_records(raw_paths, with_thumbnails=True))

        return gps_by_path

    def _read_gps_records(self, paths: list[Path], *, with_thumbnails: bool) -> dict[Path, dict]:
        """
        Run one bulk GPS read, optionally capturing small embedded thumbnails.
        """
        extra_options = (
            ["-b", "-ThumbnailImage", "-Orientation", "-ImageSize"] if with_thumbnails else []
        )
        output = self._run(
            ["-json", "-n", *extra_options, "-GPSLatitude", "-GPSLongitude", *ALTITUDE_READ_OPTIONS, *METADATA_READ_OPTIONS],
            paths,
            "Failed to read metadata.",
        )
        records = json.loads(output)
        gps_by_path: dict[Path, dict] = {}

        for record in records:
            source_file = record.get("SourceFile")
            if source_file is None:
                continue

            path = Path(source_file)
            gps_by_path[path] = _metadata_from_record(record)

            if with_thumbnails:
                self._remember_thumbnail(path, _decode_preview(record, "ThumbnailImage"))

        return gps_by_path

    def _remember_thumbnail(self, path: Path, preview: EmbeddedPreview | None) -> None:
        key = _file_key(path)
        if key is None:
            return
        if len(self._remembered_thumbnails) >= MAX_REMEMBERED_THUMBNAILS:
            self._remembered_thumbnails.clear()
        self._remembered_thumbnails[key] = preview

    def read_embedded_preview(self, path: Path) -> EmbeddedPreview | None:
        """
        Read the JPEG preview stored inside one RAW file, for a thumbnail.

        Returns:
            The preview, or None if there is no preview.
            See read_embedded_previews() for details.
        """
        return self.read_embedded_previews([path]).get(path)

    def read_embedded_previews(
        self,
        paths: list[Path],
        tags: tuple[str, ...] = EMBEDDED_PREVIEW_TAGS,
    ) -> dict[Path, EmbeddedPreview]:
        """
        Read the JPEG previews stored inside RAW files, for thumbnails.

        tags limits which preview types are tried, for example only
        ("ThumbnailImage",) for JPEG photos: their small thumbnail sits near
        the start of the file, while larger previews can be near the end.

        Small thumbnails already captured by read_gps_many() are used without
        opening the file again. Otherwise one ExifTool command is used per
        preview type rather than one per file, smallest type first; only files
        without a small preview are asked for a larger one.

        Returns:
            {path: EmbeddedPreview} for every file that has an embedded
            preview. Files without one, or that cannot be read, are left out.
        """
        previews: dict[Path, EmbeddedPreview] = {}
        # Files the GPS read showed have no small thumbnail; skip asking again.
        known_without_thumbnail: set[Path] = set()

        for path in paths:
            key = _file_key(path)
            if key is None:
                continue
            # A single pop() (not "in" then pop) stays correct if the GPS read
            # on another thread changes the dictionary at the same time.
            remembered = self._remembered_thumbnails.pop(key, _NOT_REMEMBERED)
            if remembered is _NOT_REMEMBERED:
                continue
            if remembered is None:
                known_without_thumbnail.add(path)
            else:
                previews[path] = remembered

        remaining = [path for path in paths if path not in previews]

        for tag in tags:
            candidates = [
                path for path in remaining
                if not (tag == "ThumbnailImage" and path in known_without_thumbnail)
            ]
            if not candidates:
                continue

            # With -json, "-b" returns binary data as "base64:..." text, which
            # travels safely through the text connection to ExifTool. The exit
            # status is ignored: one unreadable file should not cost the rest
            # their thumbnails, and missing files simply get no preview.
            _, output, _ = self._execute(
                [
                    "-charset",
                    "filename=utf8",
                    "-json",
                    "-b",
                    "-n",
                    f"-{tag}",
                    "-Orientation",
                    "-ImageSize",
                    *[str(path) for path in candidates],
                ]
            )
            try:
                records = json.loads(output) if output.strip() else []
            except json.JSONDecodeError:
                records = []

            for record in records:
                source_file = record.get("SourceFile")
                preview = _decode_preview(record, tag)
                if source_file is not None and preview is not None:
                    previews[Path(source_file)] = preview

            remaining = [path for path in remaining if path not in previews]

        return previews

    def write_gps(
        self, path: Path, latitude: float, longitude: float, altitude: float | None | object = KEEP_ALTITUDE
    ) -> None:
        """
        Write GPS metadata to a file using ExifTool.

        Why we set latitude/longitude references explicitly:
            GPS metadata is commonly stored as a positive numeric value plus a
            directional reference:
                latitude  -> N or S
                longitude -> E or W

            This keeps the metadata explicit and avoids ambiguity.

        Args:
            path:
                Path to the image file to update.
            latitude:
                Decimal latitude value.
            longitude:
                Decimal longitude value.
            altitude:
                Metres above sea level (negative below), written with the
                coordinates: geotagging from a GPS track has it. None clears
                the altitude (undo of a photo that had none). The default,
                KEEP_ALTITUDE, leaves the photo's altitude as it is (Apply
                Location).

        Raises:
            RuntimeError:
                If ExifTool fails to write the metadata.
        """
        latitude_ref = "N" if latitude >= 0 else "S"
        longitude_ref = "E" if longitude >= 0 else "W"
        altitude_options = []
        if altitude is None:
            altitude_options = ["-GPSAltitude=", "-GPSAltitudeRef="]
        elif altitude is not KEEP_ALTITUDE:
            # GPSAltitudeRef 0 = above sea level, 1 = below.
            altitude_options = [
                f"-GPSAltitude={abs(altitude)}",
                f"-GPSAltitudeRef={1 if altitude < 0 else 0}",
            ]

        self._back_up_original(path)
        self._run(
            [
                *self._overwrite_options(),
                f"-GPSLatitude={abs(latitude)}",
                f"-GPSLatitudeRef={latitude_ref}",
                f"-GPSLongitude={abs(longitude)}",
                f"-GPSLongitudeRef={longitude_ref}",
                *altitude_options,
            ],
            [path],
            "Failed to write metadata.",
        )

    def clear_gps(self, path: Path) -> None:
        """
        Remove GPS metadata from a file using ExifTool: the coordinates,
        and the altitude a geotag from a GPS track may have written.
        """
        self._back_up_original(path)
        self._run(
            [
                *self._overwrite_options(),
                "-GPSLatitude=",
                "-GPSLatitudeRef=",
                "-GPSLongitude=",
                "-GPSLongitudeRef=",
                "-GPSAltitude=",
                "-GPSAltitudeRef=",
            ],
            [path],
            "Failed to clear metadata.",
        )

    def write_date_tags(self, path: Path, values: dict[str, str | None]) -> None:
        """
        Write date tags to a file: {tag: "2026:10:03 09:14:02"}. None removes
        the tag (used by undo when the photo didn't have it), except the
        file's own modified date, which every file has and is then left as is.

        Date changes never make a backup copy: undo puts back the exact
        values read before the change.

        Raises:
            RuntimeError:
                If ExifTool fails to write the metadata.
        """
        assignments = [
            f"-{tag}={value if value is not None else ''}"
            for tag, value in values.items()
            if value is not None or tag != "FileModifyDate"
        ]
        if not assignments:
            return
        self._run(
            [*self._overwrite_options(), *assignments],
            [path],
            "Failed to write the date.",
        )

    def _overwrite_options(self) -> list[str]:
        """
        ExifTool changes the file in place. Backups are made by
        _back_up_original instead: ExifTool's own backups are named
        "IMG_0995.jpg_original", which isn't a photo name anything shows.
        """
        return ["-overwrite_original"]

    def _back_up_original(self, path: Path) -> None:
        """
        With keep_backups on, copy the file to "<name>_original.<ext>" next
        to it before its first change. An existing backup is left alone (it
        holds the true original), and a backup is never backed up itself.
        A photo with no GPS yet isn't backed up: adding GPS loses nothing.

        Raises:
            OSError:
                If the copy can't be made; the photo is then not changed.
        """
        if not self.keep_backups or path.stem.endswith("_original"):
            return
        backup = path.with_name(f"{path.stem}_original{path.suffix}")
        if backup.exists():
            return
        gps = self.read_gps(path)
        if gps["latitude"] is None and gps["longitude"] is None:
            return
        shutil.copy2(path, backup)
        self._created_backups.append(backup)

    def take_created_backups(self) -> list[Path]:
        """
        The backups made since the last call (so the app can add them to the
        Photo List), and forget them.
        """
        backups, self._created_backups = self._created_backups, []
        return backups

    def close(self) -> None:
        """
        Stop the long-running ExifTool process, if one is running.

        Safe to call more than once. A later command starts a new process.
        """
        # If a background thread is in the middle of a long command, don't
        # wait for it forever (this also runs at app exit): stop the process
        # without the lock, which makes that command fail promptly.
        if self._lock.acquire(timeout=2):
            try:
                self._stop_process()
            finally:
                self._lock.release()
        elif self._process is not None:
            stop_process_tree(self._process)

    def __enter__(self) -> ExifToolWrapper:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _run(self, options: list[str], paths: list[Path], failure_message: str) -> str:
        """
        Run one ExifTool command with the given options on the given files.

        Why everything goes through stdin instead of the command line:
            The long-running process reads its commands from stdin anyway.
            This also fixes Windows file names: command-line arguments there
            are limited to the system code page, so some names (for example
            Japanese or emoji characters) cannot be passed correctly. ExifTool's
            recommended fix is a UTF-8 argument list plus "-charset filename=utf8".

        Args:
            options:
                ExifTool options to use, such as ["-json", "-n"].
            paths:
                Files to process. These should be absolute paths, because
                ExifTool argument lists ignore lines starting with "#" and
                strip leading spaces.
            failure_message:
                Error text used when ExifTool fails without printing a reason.

        Returns:
            ExifTool's standard output for this command as text.

        Raises:
            RuntimeError:
                If the command fails, or ExifTool stops or stops responding.
        """
        arguments = ["-charset", "filename=utf8", *options, *[str(path) for path in paths]]
        status, output, errors = self._execute(arguments)

        if status != 0:
            raise RuntimeError(errors.strip() or failure_message)

        return output

    def _execute(self, arguments: list[str]) -> tuple[int, str, str]:
        """
        Send one command to the long-running ExifTool process.

        Protocol (see "-stay_open" in the ExifTool documentation):
            1. Write the arguments, one per line.
            2. "-echo4 {statusN}${status}" makes ExifTool print the command's
               exit status to stderr once it finishes.
            3. "-executeN" runs the command; ExifTool then prints "{readyN}" to
               stdout. N is a unique number, so replies cannot get mixed up.

        Returns:
            (exit status, stdout text, stderr text) for this command.
        """
        with self._lock:
            process = self._ensure_process()
            number = next(self._command_numbers)
            ready_marker = f"{{ready{number}}}"
            status_marker = f"{{status{number}}}"

            request = "\n".join(
                [*arguments, "-echo4", status_marker + "${status}", f"-execute{number}"]
            )
            try:
                process.stdin.write(request + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                self._stop_process()
                raise RuntimeError("ExifTool stopped unexpectedly.") from exc

            output_lines = self._read_until(
                self._stdout_lines,
                lambda line: line == ready_marker,
            )
            error_lines = self._read_until(
                self._stderr_lines,
                lambda line: line.startswith(status_marker),
            )

        # Drop the marker lines; they are protocol, not command output.
        output_lines.pop()
        status_line = error_lines.pop()
        error_text = "\n".join(error_lines)
        status_text = status_line[len(status_marker):]
        if status_text.isdigit():
            status = int(status_text)
        else:
            # Very old ExifTool versions do not support ${status}; fall back to
            # treating any "Error" message as a failure.
            status = 1 if "Error" in error_text else 0

        return status, "\n".join(output_lines), error_text

    def _read_until(self, lines: queue.Queue[str | None], is_marker) -> list[str]:
        """
        Collect lines from one ExifTool output stream up to and including a marker.

        Raises:
            RuntimeError:
                If ExifTool exits or does not answer within the timeout. The
                process is stopped so the next command starts a fresh one.
        """
        collected: list[str] = []
        while True:
            try:
                line = lines.get(timeout=COMMAND_TIMEOUT_SECONDS)
            except queue.Empty:
                self._stop_process()
                raise RuntimeError("ExifTool stopped responding.") from None

            if line is None:
                self._stop_process()
                raise RuntimeError("ExifTool stopped unexpectedly.")

            collected.append(line)
            if is_marker(line):
                return collected

    def _ensure_process(self) -> subprocess.Popen:
        """
        Return the running ExifTool process, starting a new one if needed.
        """
        if self._process is not None and self._process.poll() is None:
            return self._process

        self._stop_process()

        # Guarded so ExifTool cannot keep running if the app crashes.
        process = start_guarded_process(
            [self.executable, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # ExifTool writes UTF-8; do not rely on the OS default encoding,
            # which is Windows-1252 on many Windows systems.
            encoding="utf-8",
            errors="replace",
            creationflags=NO_WINDOW_FLAGS,
        )

        # Fresh queues, so nothing from an old process can leak into replies.
        self._stdout_lines = queue.Queue()
        self._stderr_lines = queue.Queue()

        # Read stdout and stderr on background threads. Reading only one of them
        # could deadlock if ExifTool fills the other pipe's buffer.
        for stream, lines in (
            (process.stdout, self._stdout_lines),
            (process.stderr, self._stderr_lines),
        ):
            threading.Thread(
                target=_pump_lines,
                args=(stream, lines),
                daemon=True,
            ).start()

        if not self._registered_atexit:
            atexit.register(self.close)
            self._registered_atexit = True

        self._process = process
        return process

    def _stop_process(self) -> None:
        """
        Ask ExifTool to exit, and force it if it does not. Caller holds the lock.
        """
        process = self._process
        self._process = None
        if process is None:
            return

        if process.poll() is None:
            try:
                process.stdin.write("-stay_open\nFalse\n")
                process.stdin.flush()
                process.wait(timeout=5)
            except (BrokenPipeError, OSError, ValueError, subprocess.TimeoutExpired):
                pass

        # Kills ExifTool if it is still running, plus any helper processes.
        stop_process_tree(process)

        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass


def _metadata_from_record(record: dict) -> dict:
    """
    One file's ExifTool record -> {"latitude", "longitude", "date_tags",
    "make", "model"}. date_tags maps each date tag to its text, or None.
    """
    return {
        "latitude": record.get("GPSLatitude"),
        "longitude": record.get("GPSLongitude"),
        "altitude": _altitude_from_record(record),
        "date_tags": {
            tag: str(record[tag]) if record.get(tag) not in (None, "") else None
            for tag in ALL_DATE_TAGS
        },
        "make": record.get("Make"),
        "model": record.get("Model"),
    }


def _altitude_from_record(record: dict) -> float | None:
    """GPSAltitude in metres, negative below sea level (GPSAltitudeRef 1), or None."""
    altitude = record.get("GPSAltitude")
    if altitude in (None, ""):
        return None
    try:
        value = float(altitude)
    except (TypeError, ValueError):
        return None
    below = str(record.get("GPSAltitudeRef", "0")).strip() in ("1", "Below Sea Level")
    return -abs(value) if below else value


def _decode_preview(record: dict, tag: str) -> EmbeddedPreview | None:
    """
    Pull a base64 preview image, orientation, and photo size out of one JSON record.

    Returns None if the record has no such preview.
    """
    value = record.get(tag)
    if not isinstance(value, str) or not value.startswith("base64:"):
        return None

    orientation = record.get("Orientation")
    if not isinstance(orientation, int) or not 1 <= orientation <= 8:
        orientation = 1

    # With -n, ImageSize is "WIDTH HEIGHT" (some versions use "WIDTHxHEIGHT").
    image_width = image_height = None
    size_parts = re.findall(r"\d+", str(record.get("ImageSize", "")))
    if len(size_parts) == 2 and all(int(part) > 0 for part in size_parts):
        image_width, image_height = (int(part) for part in size_parts)

    return EmbeddedPreview(
        jpeg_bytes=base64.b64decode(value[len("base64:"):]),
        orientation=orientation,
        image_width=image_width,
        image_height=image_height,
    )


def _file_key(path: Path) -> tuple[Path, int, int] | None:
    """
    Identify a specific version of a file: its path, modified time, and size.
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return (path, stat.st_mtime_ns, stat.st_size)


def _pump_lines(stream: IO[str], lines: queue.Queue[str | None]) -> None:
    """
    Copy lines from an ExifTool output stream into a queue until it closes.

    None is queued at the end so readers know the process has exited.
    """
    try:
        for line in stream:
            lines.put(line.rstrip("\r\n"))
    except (OSError, ValueError):
        pass
    finally:
        lines.put(None)
