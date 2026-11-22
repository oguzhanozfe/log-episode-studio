import json, unittest
from pathlib import Path
from pipeline import prepare, export


class EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads(Path(__file__).with_name("example.json").read_text())
        self.e = prepare(self.d)

    def test_dedup_and_time_gap_split(self):
        self.assertEqual(self.e["metrics"]["Repeat deliveries"], 1)
        self.assertEqual(len(self.e["candidates"]), 3)
        self.assertEqual(self.e["candidates"][0]["services"], ["inventory", "orders"])

    def test_export_retains_order_and_counts(self):
        out = export(self.d, self.e, self.e["candidates"][:1])
        rows = [json.loads(l) for l in out["incident-timeline.jsonl"].splitlines()]
        self.assertEqual([r["id"] for r in rows], ["evt-101", "evt-102"])
        self.assertEqual(rows[1]["deliveries"], 2)

    def test_reused_event_ids_must_be_consistent(self):
        self.d["events"][2]["message"] = "Different event"
        with self.assertRaises(ValueError):
            prepare(self.d)

    def test_naive_times_rejected_and_input_order_irrelevant(self):
        self.assertEqual(
            self.e, prepare(dict(self.d, events=list(reversed(self.d["events"]))))
        )
        self.d["events"][0]["timestamp"] = "2026-05-11T09:00:00"
        with self.assertRaises(ValueError):
            prepare(self.d)
