"""
web/bridge/fotofixer_bridge.py: the Python the browser runs for the
Location and Date & Time tabs, driven with the same JSON the page sends.
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "web" / "bridge"))

import fotofixer_bridge as bridge  # noqa: E402


def photo(name, taken, offset=None, make="Canon", model="Canon EOS R8"):
    dates = {"DateTimeOriginal": taken, "CreateDate": taken, "ModifyDate": taken}
    if offset:
        dates["OffsetTimeOriginal"] = offset
    return {"name": name, "dates": dates, "make": make, "model": model}


PHOTOS = {
    "a": photo("IMG_1.CR3", "2026:10:03 09:14:02", "-06:00"),
    "b": photo("IMG_2.JPG", "2026:10:03 10:20:00", "-06:00"),
    "c": {"name": "scan.jpg", "dates": {}, "make": None, "model": None},
}


def state(**overrides):
    payload = {
        "photos": PHOTOS,
        "selected": ["a", "b", "c"],
        "mode": None,
        "reference": None,
        "typedReference": None,
        "setValue": None,
        "source": None,
        "sourceInfo": None,
        "zoneKey": None,
        "keepClock": False,
        "computerOffsetMinutes": -360,
        "now": "2026-10-13T08:00:00",
    }
    payload.update(overrides)
    return json.loads(bridge.dates("state", json.dumps(payload)))["result"]


class CoordinateTests(unittest.TestCase):
    def test_parse_ops(self) -> None:
        self.assertEqual(json.loads(bridge.parse("pair", "40.5, -111.6"))["result"], ["40.5", "-111.6"])
        self.assertEqual(json.loads(bridge.parse("manual", "40.5", "-111.6"))["result"], [40.5, -111.6])
        self.assertEqual(json.loads(bridge.parse("latitude", "91"))["ok"], False)


class DescribeTests(unittest.TestCase):
    def test_describe_photo(self) -> None:
        described = json.loads(bridge.dates("describe", json.dumps(PHOTOS["a"])))["result"]
        self.assertEqual(described, {
            "dateTaken": "2026-10-03T09:14:02",
            "dateText": "10/03/2026 9:14:02am",
            "offsetText": "MDT",
            "camera": "Canon EOS R8",
        })
        undated = json.loads(bridge.dates("describe", json.dumps(PHOTOS["c"])))["result"]
        self.assertEqual(undated, {"dateTaken": None, "dateText": "", "offsetText": "", "camera": None})


class DateStateTests(unittest.TestCase):
    def test_nothing_chosen_yet(self) -> None:
        result = state()
        self.assertEqual(result["title"], "3 Photos Selected")
        self.assertIn("Canon EOS R8, Unknown Camera", result["summary"])
        self.assertEqual(result["reference"], "a")
        self.assertEqual(result["referencePosition"], "1 of 2")
        self.assertFalse(result["canApply"])
        self.assertEqual(result["changes"], {})

    def test_shift_from_a_typed_correct_time(self) -> None:
        result = state(mode="shift", typedReference="2026-10-03T10:14:02")
        self.assertEqual(result["shiftSeconds"], 3600)
        self.assertEqual(result["shiftText"], "1 h later")
        self.assertTrue(result["canApply"])
        self.assertEqual(result["applyLabel"], "Shift 2 Photos")
        self.assertEqual(sorted(result["changes"]), ["a", "b"])
        tags = result["changes"]["a"]
        self.assertEqual(tags["DateTimeOriginal"], "2026:10:03 10:14:02")
        self.assertNotIn("FileModifyDate", tags)
        self.assertNotIn("OffsetTimeOriginal", tags, "no zone chosen: the offsets stay")
        # The CR3's QuickTime copies as UTC, from the photo's own zone (-06:00).
        self.assertEqual(tags["QuickTime:CreateDate"], "2026:10:03 16:14:02")
        self.assertNotIn("QuickTime:CreateDate", result["changes"]["b"])
        before = result["before"]["a"]
        self.assertEqual(before["DateTimeOriginal"], "2026:10:03 09:14:02")
        self.assertEqual(before["QuickTime:CreateDate"], "2026:10:03 15:14:02")
        self.assertIsNone(before["OffsetTime"])
        self.assertIn("1 photo without a date will be skipped", result["hint"])
        self.assertEqual(result["hintTone"], "warning")
        self.assertEqual([row["kind"] for row in result["rows"]], ["change", "change", "skipped"])

    def test_shift_from_a_source_photo(self) -> None:
        source = photo("phone.heic", "2026:10:03 09:44:02", "-06:00", "Apple", "iPhone 15 Pro")
        result = state(mode="shift", sourceInfo=source)
        self.assertEqual(result["shiftSeconds"], 1800)
        self.assertEqual(result["sourceCard"], {"title": "Time from phone.heic", "detail": "Apple iPhone 15 Pro · 10/03/2026 9:44:02am"})
        # A source in the list is left out of the change.
        in_list = state(mode="shift", selected=["a", "b"], source="b")
        self.assertTrue(in_list["sourceSelected"])
        self.assertEqual(list(in_list["changes"]), ["a"])
        self.assertEqual(in_list["shiftSeconds"], 3958)

    def test_set_and_its_default(self) -> None:
        result = state(mode="set", selected=["a", "c"])
        self.assertEqual(result["setValue"], "2026-10-03T09:14:02", "Set starts from the reference photo")
        chosen = state(mode="set", selected=["a", "c"], setValue="2026-10-05T12:00:00", zoneKey="central")
        self.assertEqual(sorted(chosen["changes"]), ["a", "c"])
        self.assertEqual(chosen["changes"]["c"]["OffsetTimeOriginal"], "-05:00")
        self.assertEqual(chosen["changes"]["a"]["QuickTime:CreateDate"], "2026:10:05 17:00:00", "UTC from the chosen zone")
        self.assertEqual(chosen["applyLabel"], "Set Date on 2 Photos")
        self.assertEqual(json.loads(bridge.dates("convert_set_value", json.dumps({"value": "2026-10-05T12:00:00", "fromKey": "mountain", "toKey": "central"})))["result"], "2026-10-05T13:00:00")

    def test_change_time_zone(self) -> None:
        result = state(mode="zone", selected=["a", "b"], zoneKey="central")
        self.assertEqual(result["applyLabel"], "Change Time Zone of 2 Photos")
        self.assertEqual(result["changes"]["a"]["DateTimeOriginal"], "2026:10:03 10:14:02")
        self.assertEqual(result["changes"]["a"]["OffsetTimeOriginal"], "-05:00")
        self.assertEqual(result["zoneName"], "Central Time (Chicago)")
        kept = state(mode="zone", selected=["a", "b"], zoneKey="central", keepClock=True)
        self.assertEqual(kept["changes"]["a"]["DateTimeOriginal"], "2026:10:03 09:14:02")
        same = state(mode="zone", selected=["a", "b"], zoneKey="mountain")
        self.assertFalse(same["canApply"])
        self.assertIn("already in this time zone", same["hint"])
        text = json.loads(bridge.dates("keep_clock_text", json.dumps({"photos": PHOTOS, "selected": ["a"], "zoneKey": "central"})))["result"]
        self.assertIn("9:14:02am MDT → 9:14:02am CDT", text)

    def test_errors_are_reported_not_raised(self) -> None:
        reply = json.loads(bridge.dates("state", "not json"))
        self.assertFalse(reply["ok"])
        self.assertIn("JSONDecodeError", reply["error"])


if __name__ == "__main__":
    unittest.main()
