import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
from common import parse_m3u, base_id, url_hash
from epg import parse_ts
from probe import apply_history, looks_ts


class T(unittest.TestCase):
    def test_m3u_crlf(self):
        t = '#EXTM3U\r\n#EXTINF:-1 tvg-id="A.uk@SD" group-title="News",A (720p)\r\n#EXTVLCOPT:http-referrer=http://r/\r\nhttp://x/a.m3u8\r\n'
        r = parse_m3u(t)
        self.assertEqual((r[0]["url"], r[0]["tvg-id"], r[0]["http-referrer"]), ("http://x/a.m3u8", "A.uk@SD", "http://r/"))
        self.assertEqual(base_id("A.uk@SD"), "A.uk")
        self.assertEqual(len(url_hash("x")), 16)

    def test_ts(self):
        self.assertEqual(parse_ts("20261024040000 +0530"), parse_ts("20261023223000 +0000"))
        self.assertTrue(looks_ts(b"\x47" + b"\0" * 187 + b"\x47"))
        self.assertFalse(looks_ts(b"<html>"))

    def test_dead_needs_two_days(self):
        out, h = apply_history({"x": "d"}, {}, None)
        self.assertEqual(out["x"], "t")
        out, h = apply_history({"x": "d"}, h, None)
        self.assertEqual(out["x"], "d")
        out, h = apply_history({"x": "a"}, h, None)
        self.assertEqual((out["x"], h["x"]["n"]), ("a", 0))


if __name__ == "__main__":
    unittest.main()
