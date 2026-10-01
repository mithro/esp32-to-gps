# esp32-to-gps

An ESP32 running Tasmota that talks to a GPS/GNSS receiver module, pulls a
correction feed from the proxy on ten64.welland.mithis.com, and publishes the
complete receiver state to Home Assistant over MQTT. Modelled on
[mithro/esp32-to-433mhz](https://github.com/mithro/esp32-to-433mhz); follow its
layout, script style and conventions unless there is a reason not to.

## Git workflow (mandatory)

- **Small, logical commits.** Each commit is one logical unit of work (one
  file, one fix, one feature step). Never make a giant "big bang" commit; split
  unrelated changes before committing. Commit messages use the
  "Area: what changed" style.
- **One branch per logical piece of work, in its own worktree.** Create every
  branch from `origin/main` in `.worktrees/<branch>` (use the
  `superpowers:using-git-worktrees` skill). Keep each branch isolated to a
  single feature or set of related work; start a new branch rather than adding
  unrelated changes to an existing one.
- **The primary worktree stays at exactly `origin/main`.** Never commit, edit
  files, or switch branches in the primary checkout
  (`~/github/mithro/esp32-to-gps`). The only permitted change there is a
  fast-forward: `git fetch origin && git merge --ff-only origin/main`. If it is
  dirty or has diverged, report it rather than fixing it.
- Never push, open PRs or merge to `main` without the user asking.

## Project rules

- **Phase gate.** Work happens in this order: (1) wiring diagrams for ESP32 to
  each GPS module, (2) Tasmota-based firmware, (3) hardware confirmation that
  the wiring and firmware work. Only after the user confirms (3) does work start
  on the carrier board / PCB. Do not start any PCB or KiCad carrier work before
  that confirmation.
- **Supported GPS modules:** GT-U7, MAX-M10S ("MAX10S"), the Quectel module
  used on ten64, and the u-blox M8T.
- **Correction feed:** the firmware pulls corrections from the proxy on
  ten64.welland.mithis.com and forwards them to modules that accept them.
- **Everything to Home Assistant.** *All* GPS state (fix, position, velocity,
  time, DOP/accuracy, per-satellite data, signal quality, correction status,
  module status) is published over MQTT with Home Assistant discovery.
- **Open source tools only** (Python, KiCad, Tasmota/PlatformIO, etc.). No
  proprietary tools such as u-center or QGNSS in the build, test or docs
  workflow.
- Generated artefacts (diagrams, boards) come from scripts in `scripts/` and
  must regenerate byte-identically; CI checks this with `git diff --exit-code`.

## Tooling

- Python via `uv` only (`uv run`, PEP 723 `# /// script` headers on scripts).
- Scratch files go in the project-local `tmp/` (gitignored), never `/tmp`.
- Dates are ISO 8601 (YYYY-MM-DD).
