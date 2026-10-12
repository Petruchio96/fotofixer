"""
The update check's moving parts, on the GUI thread:

    - UpdateFetcher: the network (GitHub's API and the download), with a
      fake for tests, like the map's TileFetcher.
    - UpdateChecker: once a day, skip-this-version, and the result.
    - UpdateInstaller: download, verify, and start the installer after the
      app has quit.

All of it uses QNetworkAccessManager on the GUI thread, so no result ever
crosses a thread (see CLAUDE.md on queued signals). The decisions (which
file, which install kind, the hand-over commands) live in core/updates.py.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from core.updates import (
    LATEST_RELEASE_API_URL,
    Asset,
    DownloadVerifier,
    InstallKind,
    ReleaseInfo,
    Version,
    is_newer,
    is_trusted_download_url,
    parse_release,
    posix_update_script,
    windows_installer_command,
)
from gui import error_log

# QSettings keys.
CHECK_ON_START_SETTING = "updates/check_on_start"
LAST_CHECK_SETTING = "updates/last_check"
SKIPPED_VERSION_SETTING = "updates/skipped_version"

API_TIMEOUT_MS = 10_000
# A transfer timeout is an inactivity timeout: a slow download keeps going
# as long as data arrives.
DOWNLOAD_TIMEOUT_MS = 30_000
MAX_REDIRECTS = 5

# Download outcomes (download_finished's first argument).
DOWNLOAD_OK = "ok"
DOWNLOAD_CANCELLED = "cancelled"
DOWNLOAD_UNTRUSTED = "untrusted"
DOWNLOAD_FAILED = "failed"

# Check results (CheckResult.status).
NEWER = "newer"
CURRENT = "current"
OFFLINE = "offline"
RATE_LIMITED = "rate_limited"
NO_RELEASES = "no_releases"
BAD_RESPONSE = "bad_response"

# What the user reads for each failure.
FAILURE_MESSAGES = {
    OFFLINE: "Couldn't reach GitHub. Check your connection and try again.",
    RATE_LIMITED: "GitHub is busy right now. Try again in an hour.",
    NO_RELEASES: "Couldn't reach GitHub. Check your connection and try again.",
    BAD_RESPONSE: "GitHub sent an answer this app doesn't understand. Try again later.",
}
DOWNLOAD_MESSAGES = {
    DOWNLOAD_UNTRUSTED: "The download came from an unexpected address and was stopped.",
    DOWNLOAD_FAILED: "Couldn't download the update. Check your connection and try again.",
}
DAMAGED_MESSAGE = "The download was damaged. Try again."


class UpdateFetcher(QObject):
    """
    Talks to GitHub. Tests replace it with a fake that answers at once.

    release_finished(status, body): the API's HTTP status (0 when nothing
    came back) and its text. download_finished(outcome, detail): one of
    the DOWNLOAD_* outcomes and a line for the error log.
    """

    release_finished = Signal(int, str)
    download_progress = Signal(int, int)
    download_finished = Signal(str, str)

    def fetch_release(self, url: str) -> None:
        raise NotImplementedError

    def download(self, url: str, destination: Path, verifier: DownloadVerifier) -> None:
        """Save url to destination, feeding every chunk to the verifier."""
        raise NotImplementedError

    def cancel(self) -> None:
        """Stop the download in progress, if any (download_finished still fires)."""

    def is_busy(self) -> bool:
        return False


class NetworkUpdateFetcher(UpdateFetcher):
    """One request at a time over HTTPS, redirects checked against the allowlist."""

    def __init__(self, *, user_agent: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._user_agent = user_agent.encode("utf-8")
        self._manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._file = None
        self._verifier: DownloadVerifier | None = None
        self._destination: Path | None = None
        self._redirects = 0
        self._untrusted = False
        self._bad_status = False

    def is_busy(self) -> bool:
        return self._reply is not None

    def _request(self, url: str, timeout_ms: int) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", self._user_agent)
        request.setTransferTimeout(timeout_ms)
        request.setAttribute(
            QNetworkRequest.Attribute.CacheLoadControlAttribute,
            QNetworkRequest.CacheLoadControl.AlwaysNetwork,
        )
        # Every redirect goes through _redirected before it is followed.
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.UserVerifiedRedirectPolicy,
        )
        return request

    def _start(self, request: QNetworkRequest) -> QNetworkReply:
        self._redirects = 0
        self._untrusted = False
        self._bad_status = False
        reply = self._manager.get(request)
        self._reply = reply
        reply.redirected.connect(lambda url: self._redirected(reply, url))
        return reply

    def _redirected(self, reply: QNetworkReply, url: QUrl) -> None:
        self._redirects += 1
        if self._redirects > MAX_REDIRECTS or not is_trusted_download_url(url.toString()):
            self._untrusted = True
            reply.abort()
            return
        reply.redirectAllowed.emit()

    # --- the API ---

    def fetch_release(self, url: str) -> None:
        if self._reply is not None:
            return
        request = self._request(url, API_TIMEOUT_MS)
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"X-GitHub-Api-Version", b"2022-11-28")
        reply = self._start(request)
        reply.finished.connect(lambda: self._release_finished(reply))

    def _release_finished(self, reply: QNetworkReply) -> None:
        self._reply = None
        reply.deleteLater()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        body = bytes(reply.readAll()).decode("utf-8", errors="replace")
        if self._untrusted or not isinstance(status, int):
            self.release_finished.emit(0, reply.errorString())
            return
        self.release_finished.emit(status, body)

    # --- the download ---

    def download(self, url: str, destination: Path, verifier: DownloadVerifier) -> None:
        if self._reply is not None:
            return
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(destination, "wb")
        except OSError as error:
            self.download_finished.emit(DOWNLOAD_FAILED, f"Couldn't create {destination}: {error}")
            return
        self._destination = destination
        self._verifier = verifier
        reply = self._start(self._request(url, DOWNLOAD_TIMEOUT_MS))
        reply.readyRead.connect(lambda: self._chunk_arrived(reply))
        # Qt's progress is (qlonglong, qlonglong); a plain connect to an
        # (int, int) signal is refused, so convert.
        reply.downloadProgress.connect(
            lambda received, total: self.download_progress.emit(int(received), int(total))
        )
        reply.finished.connect(lambda: self._download_finished(reply))

    def _chunk_arrived(self, reply: QNetworkReply) -> None:
        if self._bad_status or self._file is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status != 200:
            # An error page is not the file; stop writing and let finished sort it out.
            self._bad_status = True
            return
        data = bytes(reply.readAll())
        try:
            self._file.write(data)
        except OSError:
            self._bad_status = True
            reply.abort()
            return
        self._verifier.update(data)

    def _download_finished(self, reply: QNetworkReply) -> None:
        self._reply = None
        reply.deleteLater()
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                self._bad_status = True
            self._file = None
        error = reply.error()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if self._untrusted:
            outcome, detail = DOWNLOAD_UNTRUSTED, f"redirect refused: {reply.url().toString()}"
        elif error == QNetworkReply.NetworkError.OperationCanceledError:
            outcome, detail = DOWNLOAD_CANCELLED, "cancelled"
        elif error != QNetworkReply.NetworkError.NoError or self._bad_status or status != 200:
            outcome, detail = DOWNLOAD_FAILED, f"HTTP {status}: {reply.errorString()}"
        else:
            outcome, detail = DOWNLOAD_OK, "downloaded"
        if outcome != DOWNLOAD_OK and self._destination is not None:
            try:
                self._destination.unlink()
            except OSError:
                pass
        self._destination = None
        self._verifier = None
        self.download_finished.emit(outcome, detail)

    def cancel(self) -> None:
        if self._reply is not None:
            self._reply.abort()


@dataclass
class CheckResult:
    status: str
    release: ReleaseInfo | None = None


class UpdateChecker(QObject):
    """
    Asks GitHub for the latest release and remembers what the user said
    about it. One request at a time: a second check while one runs just
    waits for the same answer.
    """

    def __init__(
        self,
        *,
        fetcher: UpdateFetcher,
        settings: QSettings,
        current_version: Version,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.fetcher = fetcher
        self.settings = settings
        self.current_version = current_version
        # The newest release seen, when it is newer than this app.
        self.latest: ReleaseInfo | None = None
        self._callbacks: list[Callable[[CheckResult], None]] = []
        self._dismissed_tag: str | None = None
        fetcher.release_finished.connect(self._handle_release)

    @property
    def is_checking(self) -> bool:
        return bool(self._callbacks)

    def is_due(self, now: datetime.datetime | None = None) -> bool:
        """The automatic check runs once a calendar day."""
        now = now or datetime.datetime.now()
        last = self.settings.value(LAST_CHECK_SETTING, "", type=str)
        try:
            last_date = datetime.datetime.fromisoformat(last).date()
        except ValueError:
            return True
        return last_date != now.date()

    def check(self, on_result: Callable[[CheckResult], None]) -> None:
        self._callbacks.append(on_result)
        if len(self._callbacks) == 1:
            self.fetcher.fetch_release(LATEST_RELEASE_API_URL)

    def _handle_release(self, status: int, body: str) -> None:
        if status == 200:
            try:
                release = parse_release(json.loads(body))
            except (ValueError, TypeError):
                result = CheckResult(BAD_RESPONSE)
            else:
                if is_newer(release.version, self.current_version):
                    self.latest = release
                    result = CheckResult(NEWER, release)
                else:
                    result = CheckResult(CURRENT, release)
        elif status == 0:
            result = CheckResult(OFFLINE)
        elif status in (403, 429):
            result = CheckResult(RATE_LIMITED)
        elif status == 404:
            result = CheckResult(NO_RELEASES)
        else:
            result = CheckResult(BAD_RESPONSE)

        if status != 0:
            # GitHub answered, so today's check happened. Offline doesn't
            # count: try again at the next start.
            self.settings.setValue(LAST_CHECK_SETTING, datetime.datetime.now().isoformat(timespec="seconds"))
        if result.status not in (NEWER, CURRENT):
            error_log.log(f"Update check: {result.status} (HTTP {status}) {body[:200]!r}")

        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback(result)

    # --- what the user said ---

    def skip(self, release: ReleaseInfo) -> None:
        """Don't mention this version again (a newer one will still show)."""
        self.settings.setValue(SKIPPED_VERSION_SETTING, release.tag)

    def is_skipped(self, release: ReleaseInfo) -> bool:
        return self.settings.value(SKIPPED_VERSION_SETTING, "", type=str) == release.tag

    def dismiss(self, release: ReleaseInfo) -> None:
        """Hide the notice until the app is next opened."""
        self._dismissed_tag = release.tag

    def is_dismissed(self, release: ReleaseInfo) -> bool:
        return self._dismissed_tag == release.tag


class UpdateInstaller(QObject):
    """
    Downloads the release file, checks it, and later (after the app has
    quit) starts what installs it: Setup on Windows, the shell script
    elsewhere. spawn is subprocess.Popen; tests pass a recorder.
    """

    progress = Signal(int, int)
    failed = Signal(str)
    cancelled = Signal()
    ready = Signal()

    def __init__(
        self,
        *,
        fetcher: UpdateFetcher,
        kind: InstallKind,
        download_dir: Path,
        log_path: Path,
        spawn: Callable = subprocess.Popen,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.fetcher = fetcher
        self.kind = kind
        self.download_dir = download_dir
        self.log_path = log_path
        self._spawn = spawn
        self._asset: Asset | None = None
        self._verifier: DownloadVerifier | None = None
        self.downloaded: Path | None = None
        fetcher.download_progress.connect(self.progress)
        fetcher.download_finished.connect(self._download_finished)

    @property
    def is_downloading(self) -> bool:
        return self._asset is not None

    def start(self, asset: Asset) -> None:
        if self._asset is not None:
            return
        if not is_trusted_download_url(asset.url):
            error_log.log(f"Update download refused: {asset.url}")
            self.failed.emit(DOWNLOAD_MESSAGES[DOWNLOAD_UNTRUSTED])
            return
        self._asset = asset
        self._verifier = DownloadVerifier()
        self.downloaded = None
        self.fetcher.download(asset.url, self.download_dir / asset.name, self._verifier)

    def cancel(self) -> None:
        self.fetcher.cancel()

    def _download_finished(self, outcome: str, detail: str) -> None:
        asset, self._asset = self._asset, None
        verifier, self._verifier = self._verifier, None
        if asset is None:
            return
        if outcome == DOWNLOAD_CANCELLED:
            self.cancelled.emit()
            return
        if outcome != DOWNLOAD_OK:
            error_log.log(f"Update download failed: {detail}")
            self.failed.emit(DOWNLOAD_MESSAGES[outcome])
            return
        path = self.download_dir / asset.name
        if not verifier.matches(asset.size, asset.sha256):
            error_log.log(
                f"Update download damaged: {asset.name} got {verifier.received} bytes, expected {asset.size}"
            )
            try:
                path.unlink()
            except OSError:
                pass
            self.failed.emit(DAMAGED_MESSAGE)
            return
        self.downloaded = path
        self.ready.emit()

    def launch(self, *, target: Path | None, app_pid: int) -> None:
        """
        Start the installer, detached, so it outlives this process. Call
        after the window has closed and the event loop has ended. Never
        through core/process_guard: that would end the installer with us.
        """
        if self.downloaded is None:
            return
        if self.kind == InstallKind.WINDOWS_INSTALLED:
            command = windows_installer_command(self.downloaded, self.log_path)
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            self._spawn(
                command,
                creationflags=flags,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(self.download_dir),
            )
            return
        if target is None:
            return
        script = posix_update_script(
            self.kind, downloaded=self.downloaded, target=target, app_pid=app_pid, log_path=self.log_path
        )
        script_path = self.download_dir / "update.sh"
        script_path.write_text(script, encoding="utf-8")
        self._spawn(
            ["/bin/sh", str(script_path)],
            start_new_session=True,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def running_executable() -> Path:
    return Path(sys.executable)


def environment() -> dict[str, str]:
    return dict(os.environ)
