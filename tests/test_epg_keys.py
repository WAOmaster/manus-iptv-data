"""T34/T35: guides are per feed (never another region's schedule); countries come from the feed, not the id suffix."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
from common import feed_countries
from epg import parse_ts
from publish import Merger, main_ids

IDS = {"MovieSphere.us@US", "MovieSphere.us@AU", "MovieSphere.us@CA", "MovieSphere.us@UK", "BBCNews.uk@SD", "Solo.us@HD"}
FEEDS = {("MovieSphere.us", "US"): {"is_main": True}, ("MovieSphere.us", "AU"): {"is_main": False},
         ("MovieSphere.us", "CA"): {"is_main": False}, ("MovieSphere.us", "UK"): {"is_main": False},
         ("BBCNews.uk", "SD"): {"is_main": True}, ("Solo.us", "HD"): {"is_main": False}}
RECS = [{"id": i, "base": i.partition("@")[0]} for i in sorted(IDS)]
P = lambda t: [[1, 2, t]]


class T(unittest.TestCase):
    def merger(self):
        return Merger(IDS, main_ids(RECS, FEEDS))

    def test_lionsgate_bug_each_feed_gets_its_own_guide(self):
        # the real bug: MovieSphere.us@UK (Plex UK: "Insidious") was published under the base id and shown on the US feed
        m = self.merger()
        m.add("mjh", {"MovieSphere.us@UK": P("Insidious: Chapter 2"), "MovieSphere.us@US": P("Divergent: Insurgent")})
        m.flush()
        out = m.published()
        self.assertEqual(out["MovieSphere.us@US"][0][2], "Divergent: Insurgent")
        self.assertEqual(out["MovieSphere.us@UK"][0][2], "Insidious: Chapter 2")
        self.assertNotIn("MovieSphere.us@AU", out)       # no guide of its own, not main: nothing, not another region's
        self.assertEqual(out["MovieSphere.us"][0][2], "Divergent: Insurgent")  # base alias = main feed

    def test_base_only_source_goes_to_main_feed_only(self):
        m = self.merger()
        m.add("share", {"MovieSphere.us": P("generic")})
        m.flush()
        self.assertEqual(set(m.merged), {"MovieSphere.us@US"})

    def test_base_fallback_never_beats_a_feed_guide(self):
        m = self.merger()
        m.add("extra", {"MovieSphere.us": P("fallback")})   # higher priority but feed-less
        m.add("mjh", {"MovieSphere.us@US": P("own")})
        m.flush()
        self.assertEqual(m.merged["MovieSphere.us@US"][0][2], "own")

    def test_explicit_feed_not_in_playlist_is_dropped_and_non_main_only_channel_gets_no_fallback(self):
        m = self.merger()
        m.add("grab", {"MovieSphere.us@BR": P("br"), "Solo.us": P("base")})
        m.flush()
        self.assertEqual(m.merged, {})
        self.assertEqual(m.missing_bases(), {"BBCNews.uk", "MovieSphere.us"})

    def test_no_alias_when_two_main_feeds(self):
        mains = {"X.us": ["X.us@A", "X.us@B"]}
        m = Merger({"X.us@A", "X.us@B"}, mains)
        m.add("s", {"X.us@A": P("a")})
        self.assertEqual(list(m.published()), ["X.us@A"])

    def test_timestamps_are_utc_epochs(self):
        self.assertEqual(parse_ts("20261024210000 -0400"), parse_ts("20261025010000 +0000"))
        self.assertEqual(parse_ts("20261025103000 +0530"), parse_ts("20261025050000 +0000"))
        self.assertEqual(parse_ts("20261025050000"), parse_ts("20261025050000 +0000"))  # no offset = UTC

    def test_feed_countries(self):
        # (area, languages, expected): 15 real feeds seen in the iptv-org data
        for area, lang, want in [
            (["c/BR"], ["por"], ["br"]),                                   # A&E Latin America Brazil (id .us)
            (["c/CA"], ["eng"], ["ca"]),                                   # 48 Hours CA
            (["c/UK"], ["eng"], ["uk"]),                                   # 5 Cops UK
            (["c/AR", "c/PY", "c/UY"], ["spa"], ["ar", "py", "uy"]),       # AMC Latin America
            (["c/CO", "c/PE", "c/EC", "c/BO"], ["spa"], ["co", "pe", "ec", "bo"]),
            (["c/MX"], ["spa"], ["mx"]),                                   # AXN Latin America Mexico
            (["r/LATAM"], ["spa"], ["latam"]),                             # Acapulco Shore
            (["r/HISPAM"], ["spa"], ["latam"]),                            # Canal Infantil
            (["r/CENAMER", "r/CARIB", "c/MX"], ["spa"], ["latam", "mx"]),
            (["c/ET"], ["amh", "eng"], ["et"]),                            # EBS HD (id .us)
            (["c/US"], ["amh"], ["et"]),                                   # EBS Cinema (id .us, Amharic)
            (["c/US"], ["eng"], ["us"]),                                   # MeTV
            (["ct/USNYC"], ["eng"], ["us"]),                               # Bloomberg Originals SD
            (["s/US-FL"], ["eng"], ["us"]),                                # Brevard Government Access TV
            (["r/WW"], ["eng"], []),                                       # DroneTV: unknown -> keep id suffix
            (["c/US", "c/CA"], ["eng"], ["us", "ca"]),                     # Red Bull TV US
            (["r/EMEA", "r/APAC"], ["eng"], []),
            (None, None, []),
        ]:
            self.assertEqual(feed_countries(area, lang), want, (area, lang))


if __name__ == "__main__":
    unittest.main()
