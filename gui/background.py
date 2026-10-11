"""
Run slow work (reading metadata, building thumbnails) off the GUI thread.

Why this file exists:
    Loading many photos, especially from a network share, takes seconds. Doing
    that on the GUI thread freezes the window. BackgroundRunner runs the work
    on one background thread and hands results back to the GUI thread, where
    Qt requires all widget updates to happen.

Rules for work functions:
    - Never touch widgets or QPixmap; QImage is fine.
    - Report partial results with runner.post(callback, value); the callback
      runs on the GUI thread.
    - Check a CancelToken between steps so cancelled work stops early.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, Signal


class CancelToken:
    """
    Shared flag a background job checks to see whether it should stop early.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class BackgroundRunner(QObject):
    """
    Run jobs one at a time on a single background thread.

    One thread keeps things simple and predictable: jobs never overlap, so a
    new photo load simply queues behind (and cancels) the previous one.

    Set run_inline = True to run everything immediately on the calling thread
    instead. Tests use this to keep existing synchronous checks working.
    """

    # Tells the GUI thread that results are waiting in _results. It carries
    # no data on purpose: passing Python objects through a queued Qt signal
    # from a Python thread crashed the Windows build (PySide frees them on
    # the wrong side). Results travel in a plain Python queue instead.
    _results_waiting = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.run_inline = False
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._results: queue.SimpleQueue = queue.SimpleQueue()
        self._results_waiting.connect(self._deliver_results, Qt.QueuedConnection)

        # Guards _closed and _busy, which shutdown() relies on.
        self._state = threading.Condition()
        self._closed = False
        self._busy = False

    def submit(
        self,
        work: Callable[[], object],
        on_done: Callable[[object], None],
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        """
        Run work() in the background, then on_done(result) on the GUI thread.

        If work() raises, on_error(exception) runs on the GUI thread instead.
        """
        if self._closed:
            return

        if self.run_inline:
            try:
                result = work()
            except Exception as exc:
                if on_error is not None:
                    on_error(exc)
                return
            on_done(result)
            return

        self._ensure_thread()
        self._jobs.put((work, on_done, on_error))

    def post(self, callback: Callable[[object], None], value: object) -> None:
        """
        Call callback(value) on the GUI thread. Safe to call from a job.
        """
        if self._closed:
            return
        if self.run_inline:
            callback(value)
        else:
            self._results.put((callback, value))
            self._results_waiting.emit()

    def shutdown(self, timeout: float = 5.0) -> bool:
        """
        Stop accepting work, drop queued jobs, and wait for the running job.

        Call this before the app exits. A job still using Qt (for example
        decoding thumbnails) while Qt shuts down can crash the app, so this
        waits for the current job; jobs check their CancelToken between
        batches, so that is normally well under a second.

        Returns:
            True if the background thread is idle.
        """
        with self._state:
            self._closed = True

        try:
            while True:
                self._jobs.get_nowait()
        except queue.Empty:
            pass

        deadline = time.monotonic() + timeout
        with self._state:
            while self._busy:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._state.wait(remaining)
        return True

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        # A daemon thread never keeps the app from exiting.
        self._thread = threading.Thread(
            target=self._run_jobs,
            name="photo-gps-editor-background",
            daemon=True,
        )
        self._thread.start()

    def _run_jobs(self) -> None:
        while True:
            work, on_done, on_error = self._jobs.get()
            with self._state:
                if self._closed:
                    continue
                self._busy = True
            try:
                try:
                    result = work()
                except Exception as exc:
                    if on_error is not None:
                        self.post(on_error, exc)
                    continue
                self.post(on_done, result)
            finally:
                with self._state:
                    self._busy = False
                    self._state.notify_all()

    def _deliver_results(self) -> None:
        """
        GUI thread: run the callbacks for every result waiting. One wake-up
        may find several results (or none, if an earlier one took them all).
        """
        while True:
            try:
                callback, value = self._results.get_nowait()
            except queue.Empty:
                return
            try:
                callback(value)
            except Exception:
                # Report it (see error_log.py) and keep delivering the rest.
                sys.excepthook(*sys.exc_info())


class InputBlocker(QObject):
    """
    While installed on the application, swallows clicks, keys, the mouse
    wheel, and shortcuts aimed at one window, so nothing can change while
    background work writes to the photos (the window still repaints and
    shows its progress). Install with QApplication.installEventFilter.
    """

    BLOCKED = {
        QEvent.MouseButtonPress,
        QEvent.MouseButtonRelease,
        QEvent.MouseButtonDblClick,
        QEvent.KeyPress,
        QEvent.KeyRelease,
        QEvent.Wheel,
        QEvent.Shortcut,
        QEvent.ShortcutOverride,
        QEvent.ContextMenu,
    }

    def __init__(self, window) -> None:
        super().__init__(window)
        self._window = window

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() not in self.BLOCKED:
            return False
        window = watched.window() if hasattr(watched, "window") else None
        # The main window and anything it opened (the map, menus).
        return window is self._window or (window is not None and window.parent() is self._window)
