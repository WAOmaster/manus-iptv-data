import os, sys, unittest
from datetime import datetime
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "extra_epg"))
import hiru, rupavahini

NOW = int(datetime(2026, 10, 24, 6, 0, tzinfo=hiru.SL).timestamp())  # Saturday 06:00 Sri Lanka


def load(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return f.read()


def local(ts):
    return datetime.fromtimestamp(ts, hiru.SL).strftime("%a %H:%M")


class T(unittest.TestCase):
    def test_hiru(self):
        p = hiru.parse(load("hiru.html"), NOW)
        self.assertEqual({x["channel_id"] for x in p}, {"HiruTV.lk"})
        self.assertEqual((local(p[0]["start"]), p[0]["title"]), ("Sat 04:30", "Hiru Sadaham Himidiriya"))
        self.assertEqual(p[0]["stop"], p[1]["start"])
        self.assertTrue(any(local(x["start"]) == "Sun 04:30" for x in p))  # tomorrow included
        self.assertTrue(all(x["stop"] > x["start"] for x in p))

    def test_rupavahini(self):
        p = rupavahini.parse(load("rupavahini.html"), NOW)
        self.assertEqual(p[0]["channel_id"], "Rupavahini.lk")
        self.assertEqual((local(p[0]["start"]), p[0]["title"]), ("Sat 05:31", "STATION OPENING"))
        self.assertIn("Tom & Jerry", [x["title"] for x in p])  # entity decoded
        self.assertTrue(any(local(x["start"]) == "Sun 06:00" for x in p))

    def test_rupavahini_live_page(self):
        # live page of 2026-10-25: 24:00 / 24:13:30 rows in the Monday table used to crash the whole channel
        p = rupavahini.parse(load("rupavahini-2026-10-25.html"), int(datetime(2026, 10, 26, 23, 30, tzinfo=hiru.SL).timestamp()))
        got = {(local(x["start"]), x["title"]) for x in p}
        self.assertIn(("Tue 00:00", "SETH PIRITH"), got)
        self.assertIn(("Tue 00:13", "END OF TRANSMISSION."), got)
        self.assertTrue(all(x["stop"] > x["start"] for x in p))

    def test_rupavahini_time_formats(self):
        p = rupavahini.parse(load("rupavahini-formats.html"), NOW)
        got = [(local(x["start"]), x["title"]) for x in p]
        self.assertIn(("Sat 00:30", "LATE NIGHT NEWS"), got)   # 12-hour AM
        self.assertIn(("Sat 05:31", "STATION OPENING"), got)   # HH:MM
        self.assertIn(("Sat 06:30", "DOT TIME SHOW"), got)     # HH.MM
        self.assertIn(("Sat 20:15", "EVENING DRAMA"), got)     # 12-hour PM
        self.assertIn(("Sat 10:00", "RANGE SHOW"), got)        # range, start taken
        self.assertIn(("Sun 00:00", "SETH PIRITH"), got)       # 24.00 = next day 00:00
        self.assertIn(("Sun 00:30", "AFTER MIDNIGHT"), got)    # 24:30:00 = next day 00:30
        self.assertNotIn("UNKNOWN TIME", [t for _, t in got])  # unparseable row skipped

    def test_failure_returns_empty(self):
        hiru.URL = rupavahini.URL = "http://127.0.0.1:9/"
        self.assertEqual((hiru.fetch(NOW), rupavahini.fetch(NOW)), ([], []))


if __name__ == "__main__":
    unittest.main()
