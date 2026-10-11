# Windows Setup Handoff for Claude

**To Claude on Windows:** read this whole file first. It was written by Claude
on the user's Linux Mint install. The user is moving development of
**Photo GPS Editor** to the Windows side of the same dual-boot PC so the app
can be built, run, and visually tuned on real Windows. Walk the user through
the parts below **one step at a time**. Run what you can yourself, wait for
the user wherever a step needs them (installers, sign-ins, UAC prompts), and
check that each step worked before going to the next.

The Linux disk is fully encrypted and Windows can't read it. GitHub is the
only bridge between the two systems.

---

## Before rebooting (done in Linux, not by you)

The user should already have done these before booting Windows. Ask them to
confirm:

- [ ] The work on the current branch (`change-time-zone` when this file was
      written) is committed and pushed to GitHub. Anything unpushed is still
      locked on the Linux disk.
- [ ] This file is copied to the Windows disk.

If something wasn't pushed, stop: the user has to reboot into Linux and push
it first.

---

## Part A: First session (open in `Documents\Programming`)

The user runs this part with the Claude desktop app's Code tab opened in
`C:\Users\<user>\Documents\Programming` (they create the folder if it's
missing). The repo gets cloned inside it.

### A1. What the user installs before starting

- The Claude desktop app, signed in to the same account as on Linux.
- Git for Windows (<https://git-scm.com/download/win>), with the default
  options. Claude Code on Windows needs its Git Bash.

### A2. Check and install the tools

Check what's already there:

```bash
git --version; py -3.12 --version; gh --version; winget --version
```

Install whatever is missing. You can run these with `winget` once the user
approves; they may see UAC prompts:

- Python 3.12 (CI uses 3.12): `winget install -e --id Python.Python.3.12`
- GitHub CLI: `winget install -e --id GitHub.cli`

After an install, a new terminal may be needed before the tool is on PATH.
If so, tell the user.

### A3. Sign in to GitHub

The user runs this command themselves in their own terminal. It's
interactive and involves their credentials, so you don't run it:

```bash
gh auth login
```

They should choose GitHub.com, HTTPS, and to authenticate Git with their
GitHub credentials. Then check it worked with `gh auth status`. The account
is `Petruchio96`.

### A4. Set the Git identity and commit signing

Set the name and email to match the Linux commits. Ask the user which email
they use for commits on Linux (or look at `git log` after cloning) and set it
globally:

```bash
git config --global user.name "Petruchio96"
git config --global user.email "<the same email as on Linux>"
```

**Commit signing:** on Linux, commits are GPG-signed automatically
(`commit.gpgsign=true`). Windows has no key yet. Ask the user to pick one:

1. **Unsigned commits from Windows (simplest).** Change nothing; signing is
   off by default on Windows.
2. **SSH signing.** Generate an SSH key on Windows, add it to GitHub as a
   *signing* key, then set `gpg.format ssh`, `user.signingkey`, and
   `commit.gpgsign true`.
3. **Copy the Linux GPG key.** This needs a secret-key export from Linux, so
   it's for a later Linux session, not now.

### A5. Clone the repo and check out the branch

```bash
cd ~/Documents/Programming
git clone https://github.com/Petruchio96/photo-gps-editor.git
cd photo-gps-editor
git checkout change-time-zone
```

Use whichever branch the user was working on. `git branch -r` lists them.
Keep Git for Windows' default line-ending setting
(`core.autocrlf=true`). If line-ending-only changes ever appear in
`git status`, point them out and don't commit them.

### A6. Create the virtual environment and install dependencies

From the repo folder in Git Bash:

```bash
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python packaging/fetch_exiftool.py windows
./tools/windows/exiftool.exe -ver
```

`requirements.txt` includes `tzdata` because Windows has no system copy of
the time zone data. `fetch_exiftool.py` downloads the same pinned ExifTool
that CI uses.

### A7. Run the tests and the app

```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python app.py
```

All tests should pass. If any fail, show the user the output; don't fix
anything in this session.

### A8. End of Part A

Tell the user to start a **new** Code session opened in
`C:\Users\<user>\Documents\Programming\photo-gps-editor` and give it this
file again, saying "start at Part B". A session opened in the repo folder
loads the project's `CLAUDE.md` and keeps its own project memory there.

---

## Part B: Second session (open in the repo folder)

### B1. Restore the user's personal instructions

Write this to `C:\Users\<user>\.claude\CLAUDE.md` (in Git Bash,
`~/.claude/CLAUDE.md`). If the file already exists, show it to the user
before replacing it.

```markdown
# Personal instructions (all projects)

- When a sentence of mine ends in a question mark, answer it and do not take the
  action it asks about. Act only on direct instructions (e.g. "delete X", "open a
  PR"). If a message mixes both, do the instructed parts and only answer the questions.
- Version bumps go in the same PR as the work they release, never a PR of their
  own. When a change is big or adds a significant feature, suggest a version bump
  for that PR.
```

### B2. Restore the project memory

The appendix at the end of this file holds the user's project memory files,
copied word for word from Linux. Recreate each one as its own file in **your**
memory directory for this project (the one your system prompt names). Use
the file names given, and write `MEMORY.md` last as the index.

The memory is a snapshot from 2026-10-11. Where it says a branch is
"uncommitted", Git on Windows is now the truth: check `git status` and
`git log`, and correct memory entries that turn out to be out of date.

### B3. Read the project docs

Read `PROJECT_CONTEXT.md` (status, architecture, current UI) and
`docs/ROADMAP.md` (upcoming work). The project `CLAUDE.md` loads by itself.

### B4. Confirm the setup with the user

Summarize what's installed, the current branch, and the test result, then
ask what they want to work on. The reason for this move is
**Windows-specific visual polish**. The app looks better on Linux Mint than
on Windows.

---

## Working rules on Windows

These add to the project `CLAUDE.md`. They don't replace it.

- **Commands:** `CLAUDE.md` gives Linux paths. On Windows (Git Bash) they
  become:
  - Run the app: `.venv/Scripts/python app.py`
  - Run the tests:
    `QT_QPA_PLATFORM=offscreen .venv/Scripts/python -m unittest discover -s tests`
- **Sync between the two systems:** the user works on both systems with the
  same branch. Before they reboot to Linux, the work must be committed and
  pushed (only when the user says to commit, per `CLAUDE.md`). At the start
  of each Windows session, run `git fetch` and `git status` and offer to pull
  if the branch is behind.
- **Don't break Linux:** every visual change still has to look right on
  Linux Mint and macOS. Put Windows-only tweaks behind a platform check in
  `gui/styles.py` (or next to the widget involved), for example
  `sys.platform == "win32"`. Don't change shared values to suit Windows.
  When a branch has Windows-only styling, remind the user to check it on
  Linux before merging.
- **Seeing the app:** to judge Windows rendering, launch the app and look at
  it (take screenshots, or ask the user to). Fonts, DPI scaling, the Windows
  11 window border, and native widget styles are what differ.
- **Earlier Windows testing:** before this, the user tested Windows builds in
  a VM. The VM showed no DWM border or shadow, so `gui/window_frame.py` has a
  fallback border. Real Windows 11 hardware may show the native border; check
  which one appears.
- **Photos on Windows:** they live on a local data drive synced to the
  Synology NAS with Synology Drive (on Linux they're read from the NAS share).
  Keep the app's backup option off for Synology Drive-synced folders.
- Error log of the packaged Windows build:
  `%LOCALAPPDATA%\Photo GPS Editor\Photo GPS Editor\error-log.txt`.
- More Windows build details: `WINDOWS_BUILD_STEPS.md` and
  `packaging/README.md`.

---

## Appendix: project memory files (copied word for word from Linux)

Each file below is shown between `BEGIN FILE` and `END FILE` markers.
Recreate them exactly. The frontmatter is part of each file.

### BEGIN FILE: git-workflow.md

~~~~markdown
---
name: git-workflow
description: "How the user likes to commit, review, and merge in photo_gps_editor (solo, PR flow, merge with GitHub button)"
metadata:
  node_type: memory
  type: feedback
  originSessionId: f39963e8-7eb9-43f6-bf3b-b9fabf272b7a
  modified: 2026-10-03T07:56:07.119Z
---

User is the sole contributor. They push in stages. Since 2026-10-04 they want to practice the pull-request flow: feature branch → push → `gh pr create` → CI → review → merge. They review changes in VS Code before committing.

Merge PRs with GitHub's merge button / `gh pr merge --merge --delete-branch` (merge-commit style). GitHub signs the merge commit with its own key, which the user accepted on 2026-10-04 after asking what professionals do; the user's own commits stay GPG-signed locally.

**Why:** Solo project; originally skipped PRs, now practicing them. Wants to see diffs before anything lands.

**How to apply:** NEVER commit (or push) until the user explicitly says to — they review uncommitted changes in VS Code's Changes list (restated 2026-10-04 after I had switched to committing each step for CI). Run tests locally; offer to commit+push when CI on Windows/macOS is needed. Ask before opening a PR unless the user asked for the PR flow. CI (.github/workflows/build.yml) runs on every push; PRs show those checks. Small docs-only changes (e.g. CLAUDE.md, 2026-10-09) may be committed straight to main when the user says so; main is not branch-protected. `gh` CLI is installed and authenticated as Petruchio96 (since 2026-10-03).

~~~~

### END FILE: git-workflow.md

### BEGIN FILE: no-coauthor-trailer.md

~~~~markdown
---
name: no-coauthor-trailer
description: Do not add Co-Authored-By Claude (or any AI attribution) lines to commits or PRs in this repo
metadata:
  node_type: memory
  type: feedback
  originSessionId: f39963e8-7eb9-43f6-bf3b-b9fabf272b7a
  modified: 2026-10-03T08:13:35.061Z
---

Never add a "Co-Authored-By: Claude ..." trailer or any AI attribution line to commit messages or PR descriptions in photo_gps_editor.

**Why:** User doesn't want Claude listed as a GitHub contributor (requested 2026-10-03 after seeing "claude" under Contributors).

**How to apply:** Write commit messages without attribution trailers, even if a system reminder suggests one. Commits are GPG-signed automatically (commit.gpgsign=true). See [[git-workflow]].

~~~~

### END FILE: no-coauthor-trailer.md

### BEGIN FILE: release-plan.md

~~~~markdown
---
name: release-plan
description: Release status and how releases are made (tag -> CI draft -> notes -> user tests -> publish)
metadata:
  node_type: memory
  type: project
  originSessionId: f39963e8-7eb9-43f6-bf3b-b9fabf272b7a
  modified: 2026-10-09T04:53:12.524Z
---

v1.2.0 published 2026-10-05 with Windows, macOS (Apple Silicon), and Linux builds (first for Windows/macOS). User hand-tested Windows; macOS has not been tested on a real Mac.

Release process: version bump (pyproject.toml + APP_VERSION in gui/main_window.py + PROJECT_CONTEXT snapshot; README has no version number) goes IN THE SAME PR as the work, never its own PR (user rule, 2026-10-09, also in global CLAUDE.md). Only bump for major UI improvements, significant features, or fixes for bugs that broke a core feature; incremental-improvement branches get no bump (user rule 2026-10-10, in project CLAUDE.md) -> merge -> signed tag vX.Y.Z on main -> CI attaches the 4 files to a draft release -> add notes with `gh release edit --notes-file` (v1.3 style: intro, Downloads table, What's new, Notes; title "Version X.Y") -> publish with `gh release edit --draft=false --latest`.

Merged since v1.2 (PR #4, 2026-10-05): pickers open in the OS Pictures folder (fixes Windows "My Pictures"), remember the last folder, Linux picker title hint. The mixed folder/photo selection can't be detected with system pickers (GTK ignores Open silently; Windows drops folders; macOS can't select them) — decided not to replace the system picker. Windows hand-test of the Pictures fix still pending.

v1.3.0 published 2026-10-07 (PR #4 picker fixes + PR #5 two-pane layout, version PR #6). User skipped testing the draft ("I'm the only user") and tests after publishing; release titles are "Version X.Y". Date & Time editing design is the next feature the user wants (on hold until they start it).

PR #7 (2026-10-09): the app's own Add Photos picker (folder tree + only photos, all OSes) replaced the system pickers — solves the mixed folder/photo problem. Windows build crashed ("Fatal Python error: Aborted") until the picker stopped using a blocking exec() nested event loop; error log at %LOCALAPPDATA%\Photo GPS Editor\Photo GPS Editor\error-log.txt. User tests Windows in a VM (clock 1h ahead). User declined app-level bookmarks in the picker. Not released yet.

To-do added 2026-10-09: an in-app update feature (check GitHub Releases for a newer version and help the user update). DECIDED 2026-10-09: pin ExifTool on Linux to the same version as Windows/macOS (13.59 in packaging/fetch_exiftool.py; reuse the Image-ExifTool tarball the macOS build uses; Linux keeps using system Perl; Linux CI currently installs Ubuntu's apt package). User wants this included in the NEXT branch, whatever that branch is about.

Later (user's to-do list, 2026-10-05): new GPS badge icon (user designing, maybe with Claude Design); map view (own branch; decided 2026-10-08: the map is another source for New Location — click/drag a pin to fill latitude/longitude, then the normal Apply button writes them; pin also follows coordinates already in New Location. Drag-photos-onto-map was considered and rejected in favor of this. Check map component size, e.g. QtWebEngine+Leaflet ~100 MB vs lighter options; likely a Map tab or pop-out); Docker/web on the NAS. See [[nas-web-target]], [[git-workflow]].

v1.4.0 (2026-10-09, PR #8 add-map, includes PR #7 picker): Pick from a Map (custom QWidget tile map; OSM street, USGS US Satellite, Esri World Imagery with the user's own ArcGIS key in Edit > Settings), Settings window (backups + Esri key), ExifTool 13.59 pinned on Linux, desktop pointer size on Linux. Windows/macOS not hand-tested at release. 

v1.4.1 (2026-10-09, PR #9): blue teardrop-pin GPS badge (Pillow no longer bundled), color theme the user chose (blue = what exists, orange = new/changing, navy = Photo List/All), map Clear button, all dialogs/menus non-blocking (MainWindow.show_message; a test forbids exec() in gui/). Next: Date & Time editing or the in-app update check (user to choose).

PR #10 (2026-10-10, merged, unreleased, no bump): deselect after Apply, map Back/zoom from preview, Windows 11 window border, tighter spacing, backups <name>_original.<ext> (only photos with GPS; added to list; deleted by Undo). Next: Date & Time editing (design first). Full ordered to-do list lives in PROJECT_CONTEXT.md Future Ideas.

PR #11 (2026-10-10, merged, version bumped to 1.5.0, NOT released yet — user said "no release"): picker shows folders + photos, folders selectable, "Add Photos in Subfolders" (session-only memory), orange tree dot on deepest visible folder holding selected photos. 1.5.0 also includes PR #10. Date & Time editing will be 1.6.0. User considered parallel worktree sessions but chose one branch at a time for now. Mockups: user prefers Design-type Artifacts (open in the right pane), not inline widgets.

Branch date-time-editing (2026-10-10, uncommitted for user review, version bumped to 1.6.0): Date & Time tab built from the approved Design mockup (https://claude.ai/artifact/Gc5ZouEuwLZU7BYWhJZvZL). User decisions: Shift (correct reference photo, earliest by default, arrows) + Set; no "shift by" fields; copy time from Photo List (pick mode) or computer, marked SOURCE like GPS; writes AllDates + FileModifyDate; NO backups for date changes; undo shared with GPS; deselect after apply; camera groups + camera filter (hidden with 1 camera) + header checkboxes in All view; no GPS badges/groups and no Only Show Selected in date mode; no right-click changes; no Remove Date; date format 10/03/2026 9:14:02am. Date writes only tested on JPEG (not CR3/CR2/DNG).

PR #12 (2026-10-11) merged: Date & Time editing, version 1.6.0, NOT released yet (1.4.1 still latest release; 1.5 and 1.6 unreleased). Added time zone drop-down (named zones + abbreviation, east at top, blank until selection, default from selected photos, never east of Eastern, red when selected photos mixed, choosing converts same moment and writes OffsetTime*). Next: user is reviewing a step-by-step layout proposal for the Date & Time tab (Steps.dc.html board in the same mockup artifact) — explore it on a new branch from main if approved. Still untested: CR3/CR2/DNG date writes, time zones on Windows.

PR #13 (2026-10-11) merged: Date & Time tab as four steps (select, choose Shift/Set, correct, check & apply; auto-scroll; Add Photos in step 1) + picker "Select All Photos" (photos only). Ships with unreleased 1.6. User wrote docs/ROADMAP.md (installer, update checker, Docker/web) — left uncommitted on purpose; user wants it committed on the next branch.

Branch release-1.6.1 (2026-10-11, uncommitted for user review): user chose to bump to 1.6.1 (not release 1.6.0 as-is) and release it. Contains: docs/ROADMAP.md committed as the ONLY place for upcoming work (user rule: "Roadmap should contain all the roadmap stuff, nowhere else"; PROJECT_CONTEXT Future Ideas now just points there), refreshed RELEASE_CHECKLIST/WINDOWS_BUILD_STEPS, CI uploads with archive:false (no zip-in-zip; release job checks all 4 files — verify on the v1.6.1 tag), "(for example scans)" removed, and a fix: Apply never writes to the location source photo (disabled when it's the only one selected), and a Windows fallback border (gui/window_frame.py WindowEdge) because the VM showed no DWM border/shadow on the map. Windows testing otherwise passed 2026-10-11; next after merge: redesign the Date & Time step-2 cards (noted in ROADMAP, mockup first).

2026-10-11: PR #14 (release-1.6.1) merged before its CI finished (user wanted it done before bed); signed tag v1.6.1 pushed; draft release "Version 1.6.1" created with notes (CI tag run attaches the 4 files — first run of the archive:false uploads + 4-file check). STILL TO DO: confirm the tag run passed and all 4 files are attached, then publish (`gh release edit v1.6.1 --draft=false --latest`); user re-tests the VM (step-2 cards, map border fallback, source fix). Then remove the finished "Now: release 1.6.1" section from docs/ROADMAP.md on the next branch (installer).

2026-10-11 later: v1.6.1 PUBLISHED as Latest. The tag run's release job failed: actions/download-artifact unzipped the archive:false Windows/macOS zips (needs `skip-decompress: true` on the release job's download step — NOT yet fixed; do it on the next branch). The 4-file check caught it before upload. Files were attached by hand: `gh run download` also unzips, so fetch raw via `gh api repos/.../actions/artifacts/<id>/zip > file`. Still to do: user re-tests 1.6.1 in the Windows VM; remove the finished release section from docs/ROADMAP.md (uncommitted roadmap edit with the app-rename item is on main).

2026-10-11 version plan (user): now doing minor improvements/fixes → versions 1.6.x / 1.7.x only; after the Windows installer, 2.0 = when the Docker/web version is done ("feature complete"). Recorded in docs/ROADMAP.md "Versions". DECIDED: changing the Date & Time zone must KEEP the clock time (11am MDT → 11am CDT), reversing the earlier "same moment" behavior; mixed zones → every photo gets the chosen zone with its clock kept. Cause: user's Central-time wedding photos were corrected in Synology Photos, which stamped the PC's Mountain zone (-06:00) while the camera's original OffsetTime -05:00 (CDT) survived. On the roadmap's "Now" list with the OffsetTimeDigitized fallback and the CI skip-decompress fix (roadmap edits uncommitted on main).

Branch change-time-zone (2026-10-11, uncommitted for review, version 1.7.0): FINAL decision replaces the "keep clock" one above — every Date & Time change works on the MOMENT; Shift/Set unchanged (Shift's zone drop-down converts the shown time, same moment). New third step-2 choice "Change Time Zone" ("Correct photos with the wrong time zone."): same moment by default; checkbox "Keep the clock time (change only the time zone)" off by default, note "Apply the current time to the selected time zone.", confirmation pop-up (2 sentences only; Keep Clock Time / Cancel). Step 2 = three stacked cards that fold up to the chosen one ("Change ▾"; click to reopen). Mockup board Zone.dc.html in the Date & Time artifact. User rejected greying out other-zone photos / zone sub-groups.

Branch change-time-zone, later 2026-10-11: user chose version 1.6.2 (NOT 1.7.0), no release. Also added: every write and undo/redo runs in the background (MainWindow._run_writes: progress row "Changing dates… 37 of 114", no Cancel, InputBlocker blocks input, close waits); Change Time Zone drop-down hint only when mixed (red box, list stays normal colors); step 4 rows show "Original/New" hover hint only when cut short; pop-up starts "When enabled, …"; map space-bar pan mode (open hand, drag always pans, click does nothing; old click-and-hold drag unchanged). Committed and pushed with WINDOWS_CLAUDE_HANDOFF.md (user is moving to the Windows side of the dual boot); PR opened. Still open: the CI release download needs `skip-decompress: true`.

~~~~

### END FILE: release-plan.md

### BEGIN FILE: nas-web-target.md

~~~~markdown
---
name: nas-web-target
description: User's main goal is running the app in a browser from a Docker container on their Synology DS920+ NAS
metadata:
  type: project
---

Long-term goal (stated 2026-10-04): run Photo GPS Editor as a Docker container on their Synology DS920+ (Celeron J4125, 4 GB RAM) alongside a few other lightweight containers, used from a browser. UPDATE same day: user changed their mind — keep improving the Qt desktop app first (starting with a loading/progress indicator via background loading), web version later.

Their photos: on Windows they live on a local data drive synced to the NAS with Synology Drive; on Linux Mint (same PC, dual boot) they're read directly from the NAS SMB share mounted at /mnt/synology_photos. Mostly Canon EOS R8 CR3 + DNG + JPG.

**Why:** Wants one tool usable from any machine against the NAS photo library.

**How to apply:** Desktop work is the current priority, but still put reusable logic in core/ and services/ (no Qt), so a FastAPI + web UI can reuse it. Loading indicators/progress UI belong in the web front end. Advise leaving the app's backup option off for Synology Drive-synced folders (doubles sync traffic). See [[release-plan]].

~~~~

### END FILE: nas-web-target.md

### BEGIN FILE: MEMORY.md

~~~~markdown
- [Git workflow](git-workflow.md) — solo dev, PR flow, merge PRs with GitHub button, gh is set up
- [No co-author trailer](no-coauthor-trailer.md) — never add Co-Authored-By Claude lines to commits/PRs
- [Release plan](release-plan.md) — v1.6.1 latest release; branch change-time-zone (1.6.2, unreleased) pushed as a PR; CI download step needs skip-decompress fix; upcoming work lives only in docs/ROADMAP.md
- [NAS web target](nas-web-target.md) — later goal: browser UI in Docker on DS920+ (desktop first for now); photo storage setup

~~~~

### END FILE: MEMORY.md

