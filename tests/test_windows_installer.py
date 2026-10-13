"""
The Windows installer's fixed points: the names and hooks that CI, the
release checklist, and the in-app update checker rely on. Plain text checks
of packaging/windows_installer.iss and the workflow, so they run everywhere
without Inno Setup.
"""

import unittest
from pathlib import Path

from PIL import Image

from core.updates import LINUX_APPIMAGE_ASSET, RELEASE_ASSETS, WINDOWS_SETUP_ASSET

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTALLER_SCRIPT = PROJECT_ROOT / "packaging" / "windows_installer.iss"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "build.yml"
APPIMAGE_SCRIPT = PROJECT_ROOT / "packaging" / "build_appimage.sh"
SETUP_FILE_NAME = WINDOWS_SETUP_ASSET


class WindowsInstallerScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    def test_output_file_name_is_fixed(self) -> None:
        # The update checker downloads this exact name from the release.
        base_name = WINDOWS_SETUP_ASSET.removesuffix(".exe")
        self.assertIn(f"OutputBaseFilename={base_name}\n", self.script)

    def test_app_id_is_a_fixed_guid(self) -> None:
        # Upgrades in place depend on the AppId never changing.
        self.assertRegex(
            self.script,
            r"AppId=\{\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}",
        )

    def test_installs_per_user_without_admin(self) -> None:
        self.assertIn("PrivilegesRequired=lowest", self.script)
        self.assertIn("DefaultDirName={localappdata}\\Programs\\{#MyAppName}", self.script)
        self.assertIn('#define MyAppName "FotoFixer"', self.script)

    def test_upgrade_clears_the_old_build_first(self) -> None:
        start = self.script.index("[InstallDelete]")
        install_delete = self.script[start:self.script.index("[UninstallDelete]")]
        self.assertIn('Type: filesandordirs; Name: "{app}\\_internal"', install_delete)

    def test_silent_upgrade_reopens_the_app(self) -> None:
        # The in-app updater runs the setup silently and relies on this entry.
        run_section = self.script[self.script.index("[Run]"):]
        self.assertIn("Flags: nowait skipifnotsilent", run_section)
        self.assertIn("Flags: nowait postinstall skipifsilent", run_section)
        self.assertIn("RestartApplications=no", self.script)
        self.assertIn("CloseApplications=yes", self.script)


class WindowsInstallerWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_installer_is_uploaded_and_checked_for_the_release(self) -> None:
        self.assertIn(f"path: release-files/{SETUP_FILE_NAME}", self.workflow)
        release_check = self.workflow[self.workflow.index("Check all four build files are here"):]
        self.assertIn(SETUP_FILE_NAME, release_check)

    def test_installer_script_is_compiled_with_the_project_version(self) -> None:
        self.assertIn("packaging\\windows_installer.iss", self.workflow)
        self.assertIn("/DAppVersion=$version", self.workflow)

    def test_every_release_file_has_the_name_the_update_checker_expects(self) -> None:
        # core/updates.py finds each download by name; CI must upload and
        # check exactly those names.
        release_check = self.workflow[self.workflow.index("Check all four build files are here"):]
        for name in RELEASE_ASSETS:
            self.assertIn(f"path: release-files/{name}", self.workflow)
            self.assertIn(name, release_check)
        self.assertIn(LINUX_APPIMAGE_ASSET, APPIMAGE_SCRIPT.read_text(encoding="utf-8"))

    def test_release_job_checks_the_digests_the_updater_verifies_against(self) -> None:
        self.assertIn("Check every release file has a SHA-256 digest", self.workflow)


class WindowsIconTests(unittest.TestCase):
    def test_icon_has_the_sizes_windows_uses(self) -> None:
        icon = Image.open(PROJECT_ROOT / "assets" / "app_icon.ico")
        self.assertEqual(icon.format, "ICO")
        self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)} <= set(icon.info["sizes"]))


if __name__ == "__main__":
    unittest.main()
