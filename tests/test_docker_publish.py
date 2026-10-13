"""
The container image's fixed points: the GHCR name that the compose file,
the Dockerfile, and the publishing workflow must agree on, the events that
publish it, and the version number the web page shows, which must match the
desktop app's (the two are released together). Plain text checks, so they
run everywhere without Docker. The web job of build.yml runs this file too.
"""

import re
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLISH_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "docker.yml"
BUILD_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "build.yml"
COMPOSE_FILE = PROJECT_ROOT / "docker" / "compose.yaml"
DOCKERFILE = PROJECT_ROOT / "docker" / "Dockerfile"
SELF_HOSTING = PROJECT_ROOT / "docs" / "SELF_HOSTING.md"
WEB_VERSION = PROJECT_ROOT / "web" / "app" / "version.js"

# Lowercase is required by the registry; the repository owner is not.
IMAGE = "ghcr.io/petruchio96/fotofixer"


def desktop_version() -> str:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


class PublishWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    def test_publishes_on_published_releases_only(self) -> None:
        # Publishing the release is what ships the image; drafts and
        # pre-releases must not.
        self.assertRegex(self.workflow, r"release:\n\s+types: \[published\]")
        self.assertIn("!github.event.release.prerelease", self.workflow)

    def test_image_name_and_platforms(self) -> None:
        self.assertIn(f"IMAGE: {IMAGE}\n", self.workflow)
        self.assertIn("platforms: linux/amd64,linux/arm64", self.workflow)
        self.assertIn("file: docker/Dockerfile", self.workflow)

    def test_version_tags(self) -> None:
        # X.Y.Z, X.Y, latest for a release, edge from main.
        self.assertIn("pattern={{version}}", self.workflow)
        self.assertIn("pattern={{major}}.{{minor}}", self.workflow)
        self.assertIn("type=raw,value=latest,enable=${{ github.event_name == 'release'", self.workflow)
        self.assertIn("type=edge,branch=main", self.workflow)

    def test_can_push_packages_and_nothing_more(self) -> None:
        self.assertRegex(self.workflow, r"permissions:\n  contents: read\n  packages: write\n")

    def test_build_workflow_treats_it_as_a_web_file(self) -> None:
        # A change to docker.yml alone must not start the desktop builds.
        build = BUILD_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(r"\.github/workflows/docker\.yml$", build)


class ComposeAndDockerfileTests(unittest.TestCase):
    def test_compose_runs_the_published_image(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        self.assertIn(f"image: {IMAGE}:latest\n", compose)
        # The port stays on the loopback address: the reverse proxy is the way in.
        self.assertIn('"127.0.0.1:8080:8080"', compose)

    def test_dockerfile_names_the_image_and_license(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn(IMAGE, dockerfile)
        self.assertIn('org.opencontainers.image.licenses="MIT"', dockerfile)
        # The vendor stage must not run under emulation for every platform.
        self.assertIn("FROM --platform=$BUILDPLATFORM python", dockerfile)

    def test_self_hosting_guide_uses_the_image(self) -> None:
        guide = SELF_HOSTING.read_text(encoding="utf-8")
        self.assertIn(IMAGE, guide)
        for section in ("Synology", "Caddy", "Traefik", "APP_PASSWORD"):
            self.assertIn(section, guide)


class WebVersionTests(unittest.TestCase):
    def test_web_version_matches_the_desktop_version(self) -> None:
        source = WEB_VERSION.read_text(encoding="utf-8")
        match = re.search(r'export const APP_VERSION = "([^"]+)"', source)
        self.assertIsNotNone(match, "APP_VERSION not found in web/app/version.js")
        self.assertEqual(match.group(1), desktop_version())


if __name__ == "__main__":
    unittest.main()
