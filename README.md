# bluefin-changelog

Shows the pending update changelog for [Project Bluefin](https://projectbluefin.io) images — diffing your currently booted image against the staged update using GitHub release notes and, for Dakota, attached SPDX SBOMs.

Supported variants (auto-detected from the booted image):

| Variant | Image | Releases | Diff source |
|---|---|---|---|
| Dakota | `projectbluefin/dakota` | [`projectbluefin/dakota`](https://github.com/projectbluefin/dakota/releases) | SPDX SBOMs plus the release notes |
| LTS | `ublue-os/bluefin*:lts` | [`ublue-os/bluefin-lts`](https://github.com/ublue-os/bluefin-lts/releases) | RPM package tables in the release notes (no SBOM is published) |

## What it does

1. Reads `bootc status` to find your booted and staged image digests
2. Matches them to GitHub releases for the detected variant (see the table above)
3. Dakota: parses the "Key component versions" table from the release notes
4. Dakota: downloads and diffs the SPDX 2.3 SBOMs attached to both releases. LTS: reads the Changed/Added/Removed RPM tables from the release notes instead
5. Renders a rich TUI in the terminal, or exports a styled HTML page

## Requirements

- Python 3.11+
- [`rich`](https://github.com/Textualize/rich) (`pip install rich`)
- `sudo` access (needed for `bootc status`; not needed with `--from`/`--to`)
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

# Generate the HTML and open it in your browser (writes to /tmp, needs a desktop
# session because it launches xdg-open)
bluefin-changelog --open

# Diff two releases without a staged update. Skips `bootc status`; the variant
# is inferred from the tag format (lts.YYYYMMDD → LTS, YYYY-MM-DD-<sha> → Dakota)
bluefin-changelog --from lts.20260505 --to lts.20260511
```

API responses and SBOMs are cached in `~/.cache/bluefin-changelog/` (releases: 30 min, SBOMs: 7 days).

## Current limitations

- Only the Dakota and LTS variants are supported. On any other image (including Bluefin stable and GDX) the tool exits with `Unsupported image:`; use `--from`/`--to` with a Dakota or LTS tag if you only want to read a diff.
- LTS has no SBOM diff and no key-component chips, because LTS releases publish neither; the diff is whatever the release notes list.
- SBOM diffs only go back to the first automated release (2026-05-14). Images built before that have no baseline SBOM, so the diff falls back to the nearest available release.
- Component → upstream URL mapping is hand-coded; newly added components won't have diff links until the map is updated.

## How it works

Bluefin Dakota publishes SPDX 2.3 SBOMs as GitHub release assets on each build. The SBOM is a BuildStream artifact graph — not a flat RPM list — so the diff focuses on named components with recognisable version strings rather than every cargo crate or build dependency.

The HTML export uses CSS classes and variables directly from `docs.projectbluefin.io` so the output matches the site's visual style.
