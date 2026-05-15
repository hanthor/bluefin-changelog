# bluefin-changelog

Shows the pending update changelog for [Project Bluefin](https://projectbluefin.io) images — diffing your currently booted image against the staged update using GitHub release notes and attached SPDX SBOMs.

## What it does

1. Reads `bootc status` to find your booted and staged image digests
2. Matches them to GitHub releases on [`projectbluefin/dakota`](https://github.com/projectbluefin/dakota/releases)
3. Parses the "Key component versions" table from the release notes
4. Downloads and diffs the SPDX 2.3 SBOMs attached to both releases
5. Renders a rich TUI in the terminal, or exports a styled HTML page

## Requirements

- Python 3.11+
- [`rich`](https://github.com/Textualize/rich) (`pip install rich`)
- `sudo` access (needed for `bootc status`)
- A [Bluefin](https://projectbluefin.io) image with a pending staged update

## Install

```bash
git clone https://github.com/hanthor/bluefin-changelog
cd bluefin-changelog
./install.sh
```

This creates a venv at `~/.local/share/bluefin-changelog-venv/` and installs the script to `~/.local/bin/bluefin-changelog`.

Or manually, if you already have `rich` available:

```bash
pip install rich
cp bluefin-changelog ~/.local/bin/
chmod +x ~/.local/bin/bluefin-changelog
```

## Usage

```bash
# Terminal TUI
bluefin-changelog

# Export to HTML (styled to match docs.projectbluefin.io)
bluefin-changelog --html update.html
```

API responses and SBOMs are cached in `~/.cache/bluefin-changelog/` (releases: 30 min, SBOMs: 7 days).

## Current limitations

- Only supports the **Dakota** image variant. Support for other Bluefin variants (Bluefin stable, LTS, GDX) is tracked in [#1](https://github.com/hanthor/bluefin-changelog/issues/1).
- SBOM diffs only go back to the first automated release (2026-05-14). Images built before that have no baseline SBOM, so the diff falls back to the nearest available release.
- Component → upstream URL mapping is hand-coded; newly added components won't have diff links until the map is updated.

## How it works

Bluefin Dakota publishes SPDX 2.3 SBOMs as GitHub release assets on each build. The SBOM is a BuildStream artifact graph — not a flat RPM list — so the diff focuses on named components with recognisable version strings rather than every cargo crate or build dependency.

The HTML export uses CSS classes and variables directly from `docs.projectbluefin.io` so the output matches the site's visual style.
