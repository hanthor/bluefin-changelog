"""Unit tests for the pure helpers in the `bluefin-changelog` script.

Run with: python3 -m unittest discover -s tests -v
(needs the `rich` package the script itself imports; no network access).
"""

import importlib.machinery
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "bluefin-changelog"


def _load():
    loader = importlib.machinery.SourceFileLoader("bluefin_changelog", str(SCRIPT))
    spec = importlib.util.spec_from_loader("bluefin_changelog", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


bc = _load()


class DetectVariantTests(unittest.TestCase):
    def test_dakota_image(self):
        self.assertEqual(bc.detect_variant("ghcr.io/projectbluefin/dakota:latest"), "dakota")

    def test_lts_image_needs_both_markers(self):
        self.assertEqual(bc.detect_variant("ghcr.io/ublue-os/bluefin-lts:lts"), "lts")
        self.assertIsNone(bc.detect_variant("ghcr.io/ublue-os/bluefin:stable"))

    def test_unknown_image(self):
        self.assertIsNone(bc.detect_variant("quay.io/fedora/fedora-bootc:42"))

    def test_from_tag(self):
        self.assertEqual(bc.detect_variant_from_tag("lts.20260505"), "lts")
        self.assertEqual(bc.detect_variant_from_tag("2026-05-05-abc123"), "dakota")
        self.assertIsNone(bc.detect_variant_from_tag("v1.2.3"))
        self.assertIsNone(bc.detect_variant_from_tag("2026-05-05"))


class ComponentUrlTests(unittest.TestCase):
    def test_unknown_component(self):
        self.assertIsNone(bc.component_url("nonesuch", "1.0"))

    def test_release_url_when_unchanged_or_no_old(self):
        self.assertEqual(bc.component_url("Podman", "5.1.0"),
                         "https://github.com/containers/podman/releases/tag/v5.1.0")
        self.assertEqual(bc.component_url("Podman", "5.1.0", "5.1.0"),
                         "https://github.com/containers/podman/releases/tag/v5.1.0")

    def test_compare_url_when_changed(self):
        self.assertEqual(bc.component_url("Podman", "5.2.0", "5.1.0"),
                         "https://github.com/containers/podman/compare/v5.1.0...v5.2.0")

    def test_tag_prefix_overrides(self):
        self.assertEqual(bc.component_url("fish", "4.0.0"),
                         "https://github.com/fish-shell/fish-shell/releases/tag/4.0.0")
        self.assertEqual(bc.component_url("Mesa", "25.1.0", "25.0.0"),
                         "https://gitlab.freedesktop.org/mesa/mesa/-/compare/mesa-25.0.0...mesa-25.1.0")

    def test_kernel_minor_bump_links_changelog(self):
        self.assertEqual(
            bc.component_url("Kernel", "6.14.3", "6.14.2"),
            "https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.14.3")

    def test_kernel_major_bump_links_kernelnewbies(self):
        self.assertEqual(bc.component_url("Kernel", "7.0.1", "6.19.4"),
                         "https://kernelnewbies.org/Linux_7.0")

    def test_kernel_release_url_uses_major_minor(self):
        self.assertEqual(bc.component_url("Kernel", "6.14.3"),
                         "https://kernelnewbies.org/Linux_6.14")


class SbomLinkTests(unittest.TestCase):
    def test_case_insensitive_lookup(self):
        self.assertEqual(bc.sbom_pkg_link("Podman")[1], "containers/podman")

    def test_unknown(self):
        self.assertIsNone(bc.sbom_pkg_link("bash"))


def _rel(tag):
    return {"tag_name": tag}


class FindReleaseTests(unittest.TestCase):
    def test_dakota_exact_date_prefix(self):
        releases = [_rel("2026-05-04-aaa"), _rel("2026-05-05-bbb")]
        self.assertEqual(bc.find_release_for_date(releases, "2026-05-05", "dakota"),
                         releases[1])

    def test_dakota_falls_back_to_neighbour_day(self):
        releases = [_rel("2026-05-06-ccc")]
        self.assertEqual(bc.find_release_for_date(releases, "2026-05-05", "dakota"),
                         releases[0])

    def test_dakota_prefers_later_day_first(self):
        releases = [_rel("2026-05-04-aaa"), _rel("2026-05-06-ccc")]
        self.assertEqual(bc.find_release_for_date(releases, "2026-05-05", "dakota"),
                         releases[1])

    def test_dakota_none_within_window(self):
        self.assertIsNone(
            bc.find_release_for_date([_rel("2026-05-20-zzz")], "2026-05-05", "dakota"))

    def test_lts_exact(self):
        releases = [_rel("lts.20260504"), _rel("lts.20260505")]
        self.assertEqual(bc.find_release_for_date(releases, "2026-05-05", "lts"),
                         releases[1])

    def test_lts_neighbour_across_month_boundary(self):
        releases = [_rel("lts.20260501")]
        self.assertEqual(bc.find_release_for_date(releases, "2026-04-30", "lts"),
                         releases[0])

    def test_lts_none(self):
        self.assertIsNone(bc.find_release_for_date([_rel("lts.20260101")], "2026-05-05", "lts"))

    def test_variants_do_not_cross_match(self):
        self.assertIsNone(
            bc.find_release_for_date([_rel("lts.20260505")], "2026-05-05", "dakota"))


LTS_BODY = """\
## 📦 Bluefin Packages

### ❌ Removed
| Package | Version |
|---|---|
| oldpkg | 1.0 |

### 🔄 Changed
| Package | Version |
|---|---|
| kernel | 6.12.1 ➡️ 6.12.2 |
| weird | no-arrow |

### ✨ Added
| Package | Version |
|---|---|
| newpkg | 2.0 |
|  | blank-name |
| single |

## 📦 Bluefin-dx Packages
### ✨ Added
| Package | Version |
|---|---|
| docker | 27.0 |
"""


class ParseLtsBodyTests(unittest.TestCase):
    def setUp(self):
        self.result = bc.parse_lts_body(LTS_BODY)

    def test_sections_named_without_decoration(self):
        self.assertEqual(list(self.result), ["Bluefin", "Bluefin-dx"])

    def test_each_subsection(self):
        s = self.result["Bluefin"]
        self.assertEqual(s["removed"], {"oldpkg": "1.0"})
        self.assertEqual(s["added"], {"newpkg": "2.0"})
        self.assertEqual(s["changed"]["kernel"], ("6.12.1", "6.12.2"))

    def test_changed_row_without_arrow_stored_as_plain_version(self):
        self.assertEqual(self.result["Bluefin"]["changed"]["weird"], "no-arrow")

    def test_malformed_rows_skipped(self):
        added = self.result["Bluefin"]["added"]
        self.assertNotIn("", added)
        self.assertNotIn("single", added)

    def test_second_section_is_independent(self):
        self.assertEqual(self.result["Bluefin-dx"]["added"], {"docker": "27.0"})
        self.assertEqual(self.result["Bluefin-dx"]["removed"], {})

    def test_table_rows_before_any_section_ignored(self):
        self.assertEqual(bc.parse_lts_body("| a | b |\n"), {})

    def test_empty(self):
        self.assertEqual(bc.parse_lts_body(""), {})


KEY_BODY = """\
# Release

### Key component versions

| Component | Version | Change |
|---|---|---|
| Kernel | `6.14.3` | 6.14.2 → 6.14.3 |
| GNOME | `49.1` | |
| | `1.0` | blank name |
| short | row |

After the table.
| Ignored | `9` | x |
"""


class ParseKeyComponentsTests(unittest.TestCase):
    def test_parses_rows_and_strips_backticks(self):
        got = bc.parse_key_components(KEY_BODY)
        self.assertEqual(got["Kernel"], {"version": "6.14.3", "change": "6.14.2 → 6.14.3"})
        self.assertEqual(got["GNOME"], {"version": "49.1", "change": ""})

    def test_skips_header_blank_name_and_short_rows(self):
        got = bc.parse_key_components(KEY_BODY)
        self.assertNotIn("Component", got)
        self.assertNotIn("", got)
        self.assertNotIn("short", got)

    def test_stops_at_blank_line_after_table(self):
        self.assertNotIn("Ignored", bc.parse_key_components(KEY_BODY))

    def test_no_section(self):
        self.assertEqual(bc.parse_key_components("| a | `1` | c |\n"), {})


class ExtractPackagesTests(unittest.TestCase):
    def test_filters(self):
        sbom = {"packages": [
            {"name": "keep-src", "versionInfo": "x", "sourceInfo": "git_repo"},
            {"name": "keep-ver", "versionInfo": "1.2.3", "sourceInfo": "rpm"},
            {"name": "drop-src", "versionInfo": "x", "sourceInfo": "rpm"},
            {"name": "no-ver", "versionInfo": "", "sourceInfo": "git_repo"},
            {"name": "", "versionInfo": "1.0", "sourceInfo": "git_repo"},
            {"name": "hashver", "versionInfo": "a" * 40, "sourceInfo": "git_repo"},
            {"name": "b" * 40, "versionInfo": "1.0", "sourceInfo": "git_repo"},
            {"name": "/usr/bin/x", "versionInfo": "1.0", "sourceInfo": "git_repo"},
        ]}
        self.assertEqual(bc.extract_packages(sbom),
                         {"keep-src": "x", "keep-ver": "1.2.3"})

    def test_missing_packages_key(self):
        self.assertEqual(bc.extract_packages({}), {})


class DiffPackagesTests(unittest.TestCase):
    def test_added_removed_changed(self):
        old = {"a": "1", "b": "1", "c": "1"}
        new = {"b": "1", "c": "2", "d": "1"}
        added, removed, changed = bc.diff_packages(old, new)
        self.assertEqual(added, {"d": "1"})
        self.assertEqual(removed, {"a": "1"})
        self.assertEqual(changed, {"c": ("1", "2")})

    def test_identical(self):
        self.assertEqual(bc.diff_packages({"a": "1"}, {"a": "1"}), ({}, {}, {}))


class FormatDateTests(unittest.TestCase):
    def test_formats_without_zero_padding(self):
        self.assertEqual(bc.format_date("2026-05-05"), "May 5, 2026")

    def test_invalid_returned_unchanged(self):
        self.assertEqual(bc.format_date("not-a-date"), "not-a-date")


class HtmlHelperTests(unittest.TestCase):
    def test_h_escapes_and_stringifies(self):
        self.assertEqual(bc.h("<a href=\"x\">&"), "&lt;a href=&quot;x&quot;&gt;&amp;")
        self.assertEqual(bc.h(5), "5")

    def test_chip_unchanged_is_release_link(self):
        out = bc.chip_html("Podman", "5.1.0")
        self.assertIn('href="https://github.com/containers/podman/releases/tag/v5.1.0"', out)
        self.assertIn("Release notes for 5.1.0", out)
        self.assertNotIn("chipChanged", out)
        self.assertNotIn("chipOld", out)

    def test_chip_changed_is_compare_link_with_old_version(self):
        out = bc.chip_html("Podman", "5.2.0", "5.1.0")
        self.assertIn("chipChanged", out)
        self.assertIn("compare/v5.1.0...v5.2.0", out)
        self.assertIn('<span class="chipOld_vZzQ">5.1.0</span>', out)
        self.assertIn("Compare 5.1.0 → 5.2.0", out)

    def test_chip_same_old_version_is_not_changed(self):
        self.assertNotIn("chipChanged", bc.chip_html("Podman", "5.1.0", "5.1.0"))

    def test_chip_unknown_component_is_plain_span_and_escaped(self):
        out = bc.chip_html("<x>", "1<2")
        self.assertTrue(out.startswith("<span"))
        self.assertNotIn("<a ", out)
        self.assertIn("&lt;x&gt;", out)
        self.assertIn("1&lt;2", out)

    def test_diff_section_empty_renders_nothing(self):
        self.assertEqual(bc.diff_section_html("Added", "c", [], ["Name"]), "")

    def test_diff_section_counts_rows(self):
        out = bc.diff_section_html("Added <b>", "added", ["<tr><td>1</td></tr>"] * 2,
                                   ["Name", "Version"])
        self.assertIn("Added &lt;b&gt;", out)
        self.assertIn('<span class="diff-count added">2</span>', out)
        self.assertIn("<th>Name</th><th>Version</th>", out)


class CacheTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(bc, "CACHE_DIR", tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = tmp.name

    def test_path_sanitises_key(self):
        path = bc._cache_path("a/b c:d")
        self.assertEqual(path, os.path.join(self.dir, "a_b_c_d.json"))

    def test_round_trip(self):
        bc._cache_put("k", {"x": [1, 2]})
        self.assertEqual(bc._cache_get("k"), {"x": [1, 2]})

    def test_miss(self):
        self.assertIsNone(bc._cache_get("absent"))

    def test_expired_entry_ignored(self):
        bc._cache_put("k", {"x": 1})
        old = time.time() - 7200
        os.utime(bc._cache_path("k"), (old, old))
        self.assertIsNone(bc._cache_get("k", max_age_s=3600))
        self.assertEqual(bc._cache_get("k", max_age_s=86400), {"x": 1})

    def test_corrupt_entry_ignored(self):
        Path(bc._cache_path("k")).write_text("{not json")
        self.assertIsNone(bc._cache_get("k"))

    def test_put_swallows_oserror(self):
        with mock.patch("os.makedirs", side_effect=OSError("ro")):
            bc._cache_put("k", {"x": 1})  # must not raise


class FetchJsonTests(unittest.TestCase):
    def _response(self, payload):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__.return_value = resp
        return resp

    def test_cache_hit_skips_network(self):
        with mock.patch.object(bc, "_cache_get", return_value={"c": 1}), \
             mock.patch.object(bc.urllib.request, "urlopen") as urlopen:
            self.assertEqual(bc.fetch_json("http://x", cache_key="k"), {"c": 1})
            urlopen.assert_not_called()

    def test_miss_fetches_sets_user_agent_and_caches(self):
        with mock.patch.object(bc, "_cache_get", return_value=None), \
             mock.patch.object(bc, "_cache_put") as put, \
             mock.patch.object(bc.urllib.request, "urlopen",
                               return_value=self._response({"n": 2})) as urlopen:
            self.assertEqual(bc.fetch_json("http://x", cache_key="k"), {"n": 2})
            req = urlopen.call_args[0][0]
            self.assertEqual(req.get_header("User-agent"), "bluefin-changelog/1.0")
            put.assert_called_once_with("k", {"n": 2})

    def test_without_cache_key_never_touches_cache(self):
        with mock.patch.object(bc, "_cache_get") as get, \
             mock.patch.object(bc, "_cache_put") as put, \
             mock.patch.object(bc.urllib.request, "urlopen",
                               return_value=self._response([1])):
            self.assertEqual(bc.fetch_json("http://x"), [1])
            get.assert_not_called()
            put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
