"""
core/updates.py: versions, the release JSON, the install kinds, download
checks, and the hand-over to the installer. No Qt and no network.
"""

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

from core import updates
from core.updates import (
    LINUX_APPIMAGE_ASSET,
    LINUX_TARBALL_ASSET,
    MACOS_ZIP_ASSET,
    RELEASE_ASSETS,
    RELEASES_PAGE_URL,
    WINDOWS_SETUP_ASSET,
    Asset,
    DownloadVerifier,
    InstallKind,
    ReleaseInfo,
    UpdateMode,
    current_version,
    detect_install_kind,
    install_target,
    is_newer,
    is_trusted_download_url,
    is_trusted_page_url,
    parse_release,
    parse_version,
    pick_asset,
    posix_update_script,
    update_plan,
    verify_file,
    windows_installer_command,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "release_latest.json"


def _release(**assets_by_name) -> ReleaseInfo:
    """A release with the given assets (name -> (size, sha256))."""
    return ReleaseInfo(
        version=(1, 8, 0), tag="v1.8.0", title="Version 1.8", notes="", page_url=RELEASES_PAGE_URL,
        assets=tuple(
            Asset(name=name, url=f"https://github.com/x/{name}", size=size, sha256=sha)
            for name, (size, sha) in assets_by_name.items()
        ),
    )


GOOD_SHA = "a" * 64


class VersionTests(unittest.TestCase):
    def test_parses_tags_with_and_without_a_v(self) -> None:
        self.assertEqual(parse_version("v1.6.1"), (1, 6, 1))
        self.assertEqual(parse_version("1.10.0"), (1, 10, 0))
        self.assertEqual(parse_version("V2"), (2, 0, 0))
        self.assertEqual(parse_version(" 1.10 "), (1, 10, 0))

    def test_rejects_what_is_not_a_plain_version(self) -> None:
        for text in ("latest", "", None, "1.x", "v1.2.3-rc1", "1.2.3.4", "v"):
            self.assertIsNone(parse_version(text), text)

    def test_compares_numerically(self) -> None:
        self.assertTrue(is_newer((1, 10, 0), (1, 9, 2)))
        self.assertFalse(is_newer((1, 9, 2), (1, 10, 0)))
        self.assertFalse(is_newer((1, 7, 0), (1, 7, 0)))

    def test_pretend_version_overrides_the_apps(self) -> None:
        self.assertEqual(current_version("1.8.0", {}), (1, 8, 0))
        self.assertEqual(current_version("1.8.0", {updates.PRETEND_VERSION_ENV: "1.0.0"}), (1, 0, 0))
        # A bad pretend value is ignored.
        self.assertEqual(current_version("1.8.0", {updates.PRETEND_VERSION_ENV: "old"}), (1, 8, 0))


class ParseReleaseTests(unittest.TestCase):
    def test_reads_a_real_api_answer(self) -> None:
        release = parse_release(json.loads(FIXTURE.read_text(encoding="utf-8")))

        self.assertEqual(release.tag, "v1.7.0")
        self.assertEqual(release.version, (1, 7, 0))
        self.assertEqual(release.title, "Version 1.7")
        self.assertIn("## What's new", release.notes)
        self.assertEqual(release.page_url, "https://github.com/Petruchio96/photo-gps-editor/releases/tag/v1.7.0")
        self.assertEqual(sorted(asset.name for asset in release.assets), sorted(RELEASE_ASSETS))
        for asset in release.assets:
            self.assertGreater(asset.size, 0, asset.name)
            self.assertRegex(asset.sha256, r"^[0-9a-f]{64}$")
            self.assertTrue(asset.url.startswith("https://github.com/"), asset.url)

    def test_tolerates_a_bare_release(self) -> None:
        release = parse_release({"tag_name": "v2.0"})
        self.assertEqual(release.version, (2, 0, 0))
        self.assertEqual(release.title, "v2.0")
        self.assertEqual(release.notes, "")
        self.assertEqual(release.page_url, RELEASES_PAGE_URL)
        self.assertEqual(release.assets, ())

    def test_asset_without_a_digest_has_no_sha256(self) -> None:
        release = parse_release({"tag_name": "v2.0", "assets": [
            {"name": "a", "browser_download_url": "https://github.com/a", "size": 5},
            {"name": "b", "browser_download_url": "https://github.com/b", "size": 5, "digest": "md5:abc"},
            {"name": "c", "browser_download_url": "https://github.com/c", "size": 5, "digest": "sha256:" + "B" * 64},
        ]})
        self.assertIsNone(release.asset_named("a").sha256)
        self.assertIsNone(release.asset_named("b").sha256)
        self.assertEqual(release.asset_named("c").sha256, "b" * 64)
        self.assertIsNone(release.asset_named("missing"))

    def test_rejects_a_release_without_a_version_tag(self) -> None:
        with self.assertRaises(ValueError):
            parse_release({"tag_name": "nightly"})
        with self.assertRaises(ValueError):
            parse_release({"name": "no tag"})

    def test_untrusted_page_url_falls_back_to_the_releases_page(self) -> None:
        release = parse_release({"tag_name": "v2.0", "html_url": "https://evil.example/x"})
        self.assertEqual(release.page_url, RELEASES_PAGE_URL)


class InstallKindTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def _kind(self, platform: str, *, frozen: bool = True, executable: Path | None = None, env=None) -> InstallKind:
        return detect_install_kind(
            frozen=frozen, platform=platform,
            executable=executable or self.root / "Photo GPS Editor",
            environ=env or {},
        )

    def test_source_and_container(self) -> None:
        self.assertEqual(self._kind("linux", frozen=False), InstallKind.SOURCE)
        self.assertEqual(self._kind("win32", frozen=False), InstallKind.SOURCE)
        self.assertEqual(
            self._kind("linux", frozen=False, env={updates.CONTAINER_ENV: "1"}), InstallKind.CONTAINER
        )

    def test_windows_installed_or_portable(self) -> None:
        exe = self.root / "Photo GPS Editor.exe"
        self.assertEqual(self._kind("win32", executable=exe), InstallKind.WINDOWS_PORTABLE)
        (self.root / "unins000.exe").write_bytes(b"")
        self.assertEqual(self._kind("win32", executable=exe), InstallKind.WINDOWS_INSTALLED)

    def test_mac_app_or_translocated(self) -> None:
        app_exe = Path("/Applications/Photo GPS Editor.app/Contents/MacOS/Photo GPS Editor")
        self.assertEqual(self._kind("darwin", executable=app_exe), InstallKind.MAC_APP)
        moved = Path("/private/var/folders/x/AppTranslocation/ABC/d/Photo GPS Editor.app/Contents/MacOS/Photo GPS Editor")
        self.assertEqual(self._kind("darwin", executable=moved), InstallKind.MAC_TRANSLOCATED)

    def test_linux_appimage_or_folder(self) -> None:
        self.assertEqual(self._kind("linux"), InstallKind.LINUX_FOLDER)
        env = {"APPIMAGE": "/home/me/Apps/Photo_GPS_Editor-x86_64.AppImage", "APPIMAGE_EXTRACT_AND_RUN": "1"}
        self.assertEqual(self._kind("linux", env=env), InstallKind.LINUX_APPIMAGE)

    def test_install_targets(self) -> None:
        exe = self.root / "Photo GPS Editor"
        self.assertEqual(install_target(InstallKind.WINDOWS_INSTALLED, exe, {}), exe)
        self.assertEqual(
            install_target(InstallKind.LINUX_APPIMAGE, exe, {"APPIMAGE": "/apps/x.AppImage"}),
            Path("/apps/x.AppImage"),
        )
        self.assertIsNone(install_target(InstallKind.LINUX_APPIMAGE, exe, {}))
        # The folder only counts when it is the one-folder build.
        self.assertIsNone(install_target(InstallKind.LINUX_FOLDER, exe, {}))
        (self.root / "_internal").mkdir()
        self.assertEqual(install_target(InstallKind.LINUX_FOLDER, exe, {}), self.root)
        app_exe = Path("/Applications/Photo GPS Editor.app/Contents/MacOS/Photo GPS Editor")
        self.assertEqual(install_target(InstallKind.MAC_APP, app_exe, {}), Path("/Applications/Photo GPS Editor.app"))
        self.assertIsNone(install_target(InstallKind.MAC_APP, exe, {}))
        for kind in (InstallKind.SOURCE, InstallKind.CONTAINER, InstallKind.WINDOWS_PORTABLE, InstallKind.MAC_TRANSLOCATED):
            self.assertIsNone(install_target(kind, exe, {}), kind)


class UpdatePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.asset = Asset(name=LINUX_APPIMAGE_ASSET, url="https://github.com/a", size=10, sha256=GOOD_SHA)
        self.target = Path("/apps/Photo_GPS_Editor-x86_64.AppImage")

    def test_source_and_container_only_notice(self) -> None:
        for kind in (InstallKind.SOURCE, InstallKind.CONTAINER):
            self.assertEqual(update_plan(kind, None, self.asset).mode, UpdateMode.NOTICE)

    def test_one_click_when_writable(self) -> None:
        plan = update_plan(InstallKind.LINUX_APPIMAGE, self.target, self.asset, writable=lambda _p: True)
        self.assertEqual(plan, updates.UpdatePlan(UpdateMode.INSTALL))
        plan = update_plan(InstallKind.WINDOWS_INSTALLED, Path("C:/x.exe"), self.asset, writable=lambda _p: False)
        self.assertEqual(plan.mode, UpdateMode.INSTALL)

    def test_download_page_with_a_reason_otherwise(self) -> None:
        cases = {
            "not writable": update_plan(InstallKind.LINUX_APPIMAGE, self.target, self.asset, writable=lambda _p: False),
            "no target": update_plan(InstallKind.LINUX_FOLDER, None, self.asset, writable=lambda _p: True),
            "no asset": update_plan(InstallKind.MAC_APP, self.target, None, writable=lambda _p: True),
            "no digest": update_plan(
                InstallKind.MAC_APP, self.target, Asset("x", "https://github.com/x", 10, None), writable=lambda _p: True
            ),
            "portable": update_plan(InstallKind.WINDOWS_PORTABLE, None, self.asset),
            "translocated": update_plan(InstallKind.MAC_TRANSLOCATED, None, self.asset),
        }
        for name, plan in cases.items():
            self.assertEqual(plan.mode, UpdateMode.DOWNLOAD, name)
            self.assertTrue(plan.reason, name)

    def test_picks_the_asset_for_the_kind(self) -> None:
        release = _release(**{
            WINDOWS_SETUP_ASSET: (1, GOOD_SHA), MACOS_ZIP_ASSET: (2, GOOD_SHA),
            LINUX_APPIMAGE_ASSET: (3, GOOD_SHA), LINUX_TARBALL_ASSET: (4, GOOD_SHA),
        })
        expected = {
            InstallKind.WINDOWS_INSTALLED: WINDOWS_SETUP_ASSET,
            InstallKind.WINDOWS_PORTABLE: WINDOWS_SETUP_ASSET,
            InstallKind.MAC_APP: MACOS_ZIP_ASSET,
            InstallKind.MAC_TRANSLOCATED: MACOS_ZIP_ASSET,
            InstallKind.LINUX_APPIMAGE: LINUX_APPIMAGE_ASSET,
            InstallKind.LINUX_FOLDER: LINUX_TARBALL_ASSET,
        }
        for kind, name in expected.items():
            self.assertEqual(pick_asset(release, kind).name, name)
        self.assertIsNone(pick_asset(release, InstallKind.SOURCE))
        self.assertIsNone(pick_asset(_release(), InstallKind.MAC_APP))


class DownloadChecksTests(unittest.TestCase):
    def test_trusted_download_urls(self) -> None:
        for url in (
            "https://github.com/Petruchio96/photo-gps-editor/releases/download/v1.7.0/x.zip",
            "https://objects.githubusercontent.com/github-production-release-asset/1/2?x=y",
            "https://release-assets.githubusercontent.com/github-production-release-asset/1/2?x=y",
            "https://api.github.com/repos/x/y/releases/latest",
            "https://GitHub.com/x",
        ):
            self.assertTrue(is_trusted_download_url(url), url)
        for url in (
            "http://github.com/x",
            "https://evil.example/x",
            "https://github.com.evil.example/x",
            "https://github.com@evil.example/x",
            "https://user:pw@github.com/x",
            "ftp://github.com/x",
            "",
        ):
            self.assertFalse(is_trusted_download_url(url), url)

    def test_trusted_page_urls(self) -> None:
        self.assertTrue(is_trusted_page_url("https://github.com/Petruchio96/photo-gps-editor/releases/tag/v1.7.0"))
        self.assertFalse(is_trusted_page_url("https://objects.githubusercontent.com/x"))
        self.assertFalse(is_trusted_page_url("http://github.com/x"))

    def test_verifier_matches_size_and_hash(self) -> None:
        data = b"hello " * 1000
        digest = hashlib.sha256(data).hexdigest()
        verifier = DownloadVerifier()
        for start in range(0, len(data), 700):
            verifier.update(data[start:start + 700])
        self.assertTrue(verifier.matches(len(data), digest))
        self.assertTrue(verifier.matches(len(data), digest.upper()))
        self.assertFalse(verifier.matches(len(data) - 1, digest))
        self.assertFalse(verifier.matches(len(data), "0" * 64))
        self.assertFalse(verifier.matches(len(data), None))

    def test_verify_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "download.bin"
            data = os.urandom(3000)
            path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            self.assertTrue(verify_file(path, len(data), digest))
            self.assertFalse(verify_file(path, len(data) + 1, digest))
            self.assertFalse(verify_file(path, len(data), "f" * 64))
            self.assertFalse(verify_file(path, len(data), None))
            self.assertFalse(verify_file(Path(temp) / "missing", 1, digest))

    def test_cleanup_download_dir_never_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "Photo GPS Editor update"
            folder.mkdir()
            (folder / "setup.exe").write_bytes(b"x")
            updates.cleanup_download_dir(folder)
            self.assertFalse(folder.exists())
            updates.cleanup_download_dir(folder)  # already gone


class HandOverTests(unittest.TestCase):
    def test_windows_installer_runs_silently_and_logs(self) -> None:
        command = windows_installer_command(Path("C:/t/setup.exe"), Path("C:/logs/update-log.txt"))
        self.assertEqual(command[0], "C:\\t\\setup.exe" if os.name == "nt" else "C:/t/setup.exe")
        for flag in ("/SILENT", "/SP-", "/NOCANCEL", "/NORESTART", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS"):
            self.assertIn(flag, command)
        self.assertTrue(command[-1].startswith("/LOG="))

    def _script(self, kind: InstallKind, target: str = "/Apps/My Photos/target") -> str:
        return posix_update_script(
            kind,
            downloaded=Path("/tmp/Photo GPS Editor update/download"),
            target=Path(target),
            app_pid=4242,
            log_path=Path("/home/me/.local/share/update-log.txt"),
        )

    def test_scripts_wait_for_the_app_and_log(self) -> None:
        for kind in (InstallKind.LINUX_APPIMAGE, InstallKind.LINUX_FOLDER, InstallKind.MAC_APP):
            script = self._script(kind)
            self.assertTrue(script.startswith("#!/bin/sh\n"), kind)
            self.assertIn("while kill -0 4242 2>/dev/null; do", script)
            self.assertIn("exec >>/home/me/.local/share/update-log.txt 2>&1", script)
            # Paths with spaces are quoted.
            self.assertIn("'/Apps/My Photos/target'", script)
            # The relaunch is the last thing it does.
            self.assertTrue(script.rstrip().endswith("exit 0"), kind)

    def test_appimage_script_replaces_the_file(self) -> None:
        script = self._script(InstallKind.LINUX_APPIMAGE)
        self.assertIn("chmod +x", script)
        self.assertIn("mv -f \"$staged\" '/Apps/My Photos/target'", script)
        self.assertIn("nohup '/Apps/My Photos/target' >/dev/null", script)

    def test_folder_script_unpacks_and_swaps(self) -> None:
        script = self._script(InstallKind.LINUX_FOLDER)
        self.assertIn("tar -xzf '/tmp/Photo GPS Editor update/download' -C \"$stage\"", script)
        self.assertIn("test -x \"$stage\"/'Photo GPS Editor'/'Photo GPS Editor'", script)
        self.assertIn("rm -rf \"$backup\" \"$stage\"", script)
        self.assertIn("nohup '/Apps/My Photos/target'/'Photo GPS Editor' >/dev/null", script)

    def test_mac_script_uses_ditto_and_open(self) -> None:
        script = self._script(InstallKind.MAC_APP, "/Applications/Photo GPS Editor.app")
        self.assertIn("ditto -x -k", script)
        self.assertNotIn("unzip", script)
        self.assertIn("xattr -dr com.apple.quarantine", script)
        self.assertIn("open -n '/Applications/Photo GPS Editor.app'", script)

    def test_other_kinds_have_no_script(self) -> None:
        with self.assertRaises(ValueError):
            self._script(InstallKind.WINDOWS_INSTALLED)


@unittest.skipIf(sys.platform == "win32" or shutil.which("sh") is None, "needs /bin/sh")
class RunScriptTests(unittest.TestCase):
    """Run the update scripts for real, against fake files and a fake app."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.log = self.root / "update-log.txt"
        # The "app": a short sleep the script has to wait for.
        self.app = subprocess.Popen(["sleep", "0.6"])
        self.addCleanup(self.app.wait)

    def _run(self, script: str) -> int:
        path = self.root / "update.sh"
        path.write_text(script, encoding="utf-8")
        started = time.monotonic()
        result = subprocess.run(["sh", str(path)], timeout=30)
        # It waited for the "app" to end before touching anything.
        self.assertGreaterEqual(time.monotonic() - started, 0.4)
        return result.returncode

    def test_appimage_is_replaced_and_relaunched(self) -> None:
        marker = self.root / "relaunched"
        target = self.root / "apps" / "Photo_GPS_Editor-x86_64.AppImage"
        target.parent.mkdir()
        target.write_text("#!/bin/sh\necho old\n")
        download = self.root / "download"
        download.write_text(f"#!/bin/sh\ntouch {shlex_quote(marker)}\n")

        code = self._run(posix_update_script(
            InstallKind.LINUX_APPIMAGE, downloaded=download, target=target,
            app_pid=self.app.pid, log_path=self.log,
        ))

        self.assertEqual(code, 0)
        self.assertIn("touch", target.read_text())
        self.assertTrue(target.stat().st_mode & stat.S_IXUSR)
        self.assertFalse(download.exists())
        self.assertFalse(target.with_name(target.name + ".new").exists())
        self._wait_for(marker)
        self.assertIn("Installed. Reopening the app.", self.log.read_text())

    def test_folder_is_swapped_and_relaunched(self) -> None:
        marker = self.root / "relaunched"
        target = self.root / "apps" / "Photo GPS Editor"
        (target / "_internal").mkdir(parents=True)
        (target / "Photo GPS Editor").write_text("#!/bin/sh\necho old\n")
        (target / "_internal" / "stale.so").write_text("old")
        download = self.root / "download.tar.gz"
        with tarfile.open(download, "w:gz") as tar:
            exe = f"#!/bin/sh\ntouch {shlex_quote(marker)}\n".encode()
            info = tarfile.TarInfo("Photo GPS Editor/Photo GPS Editor")
            info.size = len(exe)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(exe))
            info = tarfile.TarInfo("Photo GPS Editor/_internal/new.so")
            info.size = 3
            tar.addfile(info, io.BytesIO(b"new"))

        code = self._run(posix_update_script(
            InstallKind.LINUX_FOLDER, downloaded=download, target=target,
            app_pid=self.app.pid, log_path=self.log,
        ))

        self.assertEqual(code, 0)
        self.assertTrue((target / "_internal" / "new.so").exists())
        self.assertFalse((target / "_internal" / "stale.so").exists())
        self.assertFalse(target.with_name(target.name + ".old").exists())
        self.assertEqual([p.name for p in target.parent.iterdir()], ["Photo GPS Editor"])
        self.assertFalse(download.exists())
        self._wait_for(marker)

    def test_bad_download_leaves_the_old_folder_alone(self) -> None:
        target = self.root / "apps" / "Photo GPS Editor"
        (target / "_internal").mkdir(parents=True)
        (target / "Photo GPS Editor").write_text("#!/bin/sh\necho old\n")
        download = self.root / "download.tar.gz"
        with tarfile.open(download, "w:gz") as tar:
            info = tarfile.TarInfo("Photo GPS Editor/readme.txt")
            info.size = 2
            tar.addfile(info, io.BytesIO(b"hi"))

        code = self._run(posix_update_script(
            InstallKind.LINUX_FOLDER, downloaded=download, target=target,
            app_pid=self.app.pid, log_path=self.log,
        ))

        self.assertEqual(code, 1)
        self.assertEqual((target / "Photo GPS Editor").read_text(), "#!/bin/sh\necho old\n")
        self.assertEqual([p.name for p in target.parent.iterdir()], ["Photo GPS Editor"])
        self.assertIn("Could not unpack the update.", self.log.read_text())

    def _wait_for(self, marker: Path) -> None:
        for _ in range(50):
            if marker.exists():
                return
            time.sleep(0.1)
        self.fail(f"The relaunched app never ran: {marker}")


def shlex_quote(path: Path) -> str:
    import shlex

    return shlex.quote(str(path))


if __name__ == "__main__":
    unittest.main()
