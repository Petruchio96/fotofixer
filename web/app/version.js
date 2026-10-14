// The web version's version number: the same as the desktop app's
// (pyproject.toml and APP_VERSION in gui/main_window.py; the two are
// released together, and tests/test_docker_publish.py checks they match).
// Shown under Settings. The container image carries the same number in its
// tags and OCI labels (.github/workflows/docker.yml).
export const APP_VERSION = "1.10.1";
export const PROJECT_URL = "https://github.com/Petruchio96/fotofixer";
