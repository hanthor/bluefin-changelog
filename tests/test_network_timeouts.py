"""Every network fetch must pass a finite socket timeout to urlopen.

Without one, a stalled connection to api.github.com or a release-asset host
blocks the process forever. The script has no .py suffix, so it is loaded by
path. Requires `rich` (the script imports it at module level).

Run with: python3 -I -m unittest discover -s tests -v
"""
import importlib.machinery
import importlib.util
import json
import os
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "bluefin-changelog")

_loader = importlib.machinery.SourceFileLoader("bluefin_changelog", SCRIPT)
_spec = importlib.util.spec_from_loader("bluefin_changelog", _loader)
bc = importlib.util.module_from_spec(_spec)
_loader.exec_module(bc)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _RecordingUrlopen:
    """Stands in for urllib.request.urlopen and records the keyword args of each call."""

    def __init__(self, payload_for_url):
        self._payload_for_url = payload_for_url
        self.calls = []

    def __call__(self, req, *args, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._payload_for_url(req.full_url))


def _assert_finite_timeout(test, kwargs):
    timeout = kwargs.get("timeout")
    test.assertIsNotNone(timeout, "urlopen was called without a timeout")
    test.assertIsInstance(timeout, (int, float))
    test.assertGreater(timeout, 0)
    test.assertLess(timeout, float("inf"))


class FetchJsonTimeoutTest(unittest.TestCase):
    def test_fetch_json_passes_finite_timeout(self):
        fake = _RecordingUrlopen(lambda url: {"ok": True})
        with mock.patch.object(bc.urllib.request, "urlopen", fake):
            result = bc.fetch_json("https://api.github.com/repos/x/y/releases")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(fake.calls), 1)
        _assert_finite_timeout(self, fake.calls[0])


class DownloadSbomTimeoutTest(unittest.TestCase):
    def test_download_sbom_passes_finite_timeout_on_every_fetch(self):
        release = {
            "tag_name": "v1",
            "assets_url": "https://api.github.com/repos/x/y/releases/1/assets",
        }
        assets = [{
            "name": "bluefin.spdx.json",
            "browser_download_url": "https://example.invalid/bluefin.spdx.json",
        }]

        def payload_for_url(url):
            return assets if url == release["assets_url"] else {"packages": []}

        fake = _RecordingUrlopen(payload_for_url)
        with mock.patch.object(bc, "_cache_get", return_value=None), \
                mock.patch.object(bc, "_cache_put"), \
                mock.patch.object(bc.urllib.request, "urlopen", fake):
            sbom = bc.download_sbom(release)

        self.assertEqual(sbom, {"packages": []})
        # Two calls: the assets listing (via fetch_json) and the SBOM download.
        self.assertEqual(len(fake.calls), 2)
        for kwargs in fake.calls:
            _assert_finite_timeout(self, kwargs)


if __name__ == "__main__":
    unittest.main()
