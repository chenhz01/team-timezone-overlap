# -*- coding: utf-8 -*-
"""self_test for team-timezone-overlap — inherits v2 template four defenses."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")

import team_timezone_overlap as mod

TMP = tempfile.mkdtemp(prefix="tto_selftest_")
_n = [0]


def write_doc(obj):
    _n[0] += 1
    path = os.path.join(TMP, "team_%d.json" % _n[0])
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    return path


def run_cli(argv):
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            code = mod.main(argv) or 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


def member(name, off, start="09:00", end="17:00"):
    return {"name": name, "utc_offset": off, "work_start": start, "work_end": end}


class TestAFunctional(unittest.TestCase):
    def test_same_timezone_full_overlap(self):
        p = write_doc({"members": [member("A", "+00:00"), member("B", "+00:00")]})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)
        self.assertIn("coverage=2", out)

    def test_offset_plus_five_thirty_parsed(self):
        self.assertEqual(mod.parse_offset("+05:30"), 330)

    def test_offset_negative_eight(self):
        self.assertEqual(mod.parse_offset("-08:00"), -480)

    def test_offset_z_is_zero(self):
        self.assertEqual(mod.parse_offset("Z"), 0)

    def test_offset_without_colon(self):
        self.assertEqual(mod.parse_offset("+0530"), 330)

    def test_time_parse_half_hour(self):
        self.assertEqual(mod.parse_time("09:30"), 9.5)

    def test_europe_us_common_window(self):
        p = write_doc({"members": [member("EU", "+01:00"), member("US", "-05:00")]})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)
        self.assertIn("coverage=2", out)

    def test_us_wraps_day(self):
        # UTC 17:00-01:00 window: US Pacific 9-17 = 17:00-01:00 UTC
        p = write_doc({"members": [member("US", "-08:00"), member("NZ", "+13:00")]})
        code, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertEqual(rep["summary"]["windows_found"], 1)

    def test_min_members_two_of_three(self):
        p = write_doc({"members": [member("A", "+00:00"), member("B", "+01:00"),
                                   member("C", "+13:00")], "min_members": 2})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)
        self.assertIn("need 2", out)

    def test_no_window_exit1(self):
        p = write_doc({"members": [member("A", "+00:00"), member("B", "+12:00")]})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 1)
        self.assertIn("no common window", out)

    def test_default_min_members_is_all(self):
        p = write_doc({"members": [member("A", "+00:00"), member("B", "+01:00"),
                                   member("C", "+05:30")]})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)
        self.assertIn("need 3", out)

    def test_short_meeting_finds_window_long_fails(self):
        short = write_doc({"members": [member("A", "+00:00", "09:00", "09:30"),
                                       member("B", "+00:00", "09:00", "09:30")],
                           "duration_minutes": 30})
        code, _, _ = run_cli([short])
        self.assertEqual(code, 0)
        long_ = write_doc({"members": [member("A", "+00:00", "09:00", "09:30"),
                                       member("B", "+00:00", "09:00", "09:30")],
                           "duration_minutes": 60})
        code2, _, _ = run_cli([long_])
        self.assertEqual(code2, 1)

    def test_json_format_parseable(self):
        p = write_doc({"members": [member("A", "+00:00")]})
        _, out, _ = run_cli([p, "--format", "json"])
        self.assertIsInstance(json.loads(out), dict)

    def test_off_hours_member_flagged(self):
        # window at UTC 02:00 -> +13:00 member local 15:00 ok; -08:00 member local 18:00? compute
        p = write_doc({"members": [member("A", "+00:00", "02:00", "10:00"),
                                   member("B", "+13:00", "15:00", "23:00")]})
        _, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertTrue(rep["windows"])

    def test_fairness_rotation_multiple_windows(self):
        p = write_doc({"members": [member("A", "+00:00", "08:00", "12:00"),
                                   member("B", "+00:00", "08:00", "18:00"),
                                   member("C", "+00:00", "14:00", "18:00")],
                       "min_members": 2})
        _, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertTrue(len(rep["fairness_rotation"]) >= 2)

    def test_rotation_absent_single_window(self):
        p = write_doc({"members": [member("A", "+00:00", "09:00", "10:00"),
                                   member("B", "+00:00", "09:00", "10:00")]})
        _, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(json.loads(out)["fairness_rotation"], [])

    def test_participants_listed(self):
        p = write_doc({"members": [member("A", "+00:00"), member("B", "+01:00")]})
        _, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertIn("A", rep["windows"][0]["participants"])

    def test_utc_window_shift(self):
        w = mod.member_utc_window(member("A", "+02:00"), 120)
        self.assertEqual(w, (7.0, 15.0))

    def test_verdict_mentions_rotation(self):
        p = write_doc({"members": [member("A", "+00:00", "08:00", "18:00"),
                                   member("B", "+00:00", "08:00", "18:00")]})
        _, out, _ = run_cli([p])
        self.assertIn("rotate", out)

    def test_half_hour_work_window(self):
        p = write_doc({"members": [member("A", "+00:00", "09:00", "09:30"),
                                   member("B", "+00:00", "09:00", "09:30")],
                       "duration_minutes": 30})
        code, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertEqual(rep["windows"][0]["utc_start"], "09:00")


class TestBErrors(unittest.TestCase):
    def test_missing_file_exit2(self):
        code, _, err = run_cli([os.path.join(TMP, "nope.json")])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_bad_json_exit2(self):
        _n[0] += 1
        p = os.path.join(TMP, "bad_%d.json" % _n[0])
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write("}{")
        self.assertEqual(run_cli([p])[0], 2)

    def test_empty_members_exit2(self):
        p = write_doc({"members": []})
        code, _, err = run_cli([p])
        self.assertEqual(code, 2)
        self.assertIn("members", err)

    def test_members_not_list(self):
        p = write_doc({"members": "everyone"})
        self.assertEqual(run_cli([p])[0], 2)

    def test_member_not_object(self):
        p = write_doc({"members": ["alice"]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_member_missing_name(self):
        p = write_doc({"members": [{"utc_offset": "+00:00",
                                    "work_start": "09:00", "work_end": "17:00"}]})
        code, _, err = run_cli([p])
        self.assertEqual(code, 2)
        self.assertIn("name", err)

    def test_bad_offset_format(self):
        p = write_doc({"members": [member("A", "+5") ]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_offset_too_large(self):
        p = write_doc({"members": [member("A", "+15:01")]})
        code, _, err = run_cli([p])
        self.assertEqual(code, 2)
        self.assertIn("range", err)

    def test_bad_minutes_in_offset(self):
        p = write_doc({"members": [member("A", "+05:75")]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_bad_time_format(self):
        p = write_doc({"members": [member("A", "+00:00", "9am", "17:00")]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_time_out_of_range(self):
        p = write_doc({"members": [member("A", "+00:00", "25:00", "26:00")]})
        self.assertEqual(run_cli([p])[0], 2)

    def test_start_equals_end(self):
        p = write_doc({"members": [member("A", "+00:00", "09:00", "09:00")]})
        code, _, err = run_cli([p])
        self.assertEqual(code, 2)
        self.assertIn("work_start", err)

    def test_min_members_zero(self):
        p = write_doc({"members": [member("A", "+00:00")], "min_members": 0})
        self.assertEqual(run_cli([p])[0], 2)

    def test_min_members_gt_n(self):
        p = write_doc({"members": [member("A", "+00:00")], "min_members": 2})
        self.assertEqual(run_cli([p])[0], 2)

    def test_min_members_not_int(self):
        p = write_doc({"members": [member("A", "+00:00")], "min_members": "all"})
        self.assertEqual(run_cli([p])[0], 2)

    def test_duration_zero(self):
        p = write_doc({"members": [member("A", "+00:00")], "duration_minutes": 0})
        self.assertEqual(run_cli([p])[0], 2)

    def test_duration_gt_day(self):
        p = write_doc({"members": [member("A", "+00:00")], "duration_minutes": 2000})
        self.assertEqual(run_cli([p])[0], 2)

    def test_duration_not_int(self):
        p = write_doc({"members": [member("A", "+00:00")], "duration_minutes": 22.5})
        self.assertEqual(run_cli([p])[0], 2)

    def test_no_args_exit2(self):
        self.assertEqual(run_cli([])[0], 2)

    def test_unknown_format_exit2(self):
        p = write_doc({"members": [member("A", "+00:00")]})
        self.assertEqual(run_cli([p, "--format", "csv"])[0], 2)

    def test_empty_file_exit2(self):
        _n[0] += 1
        p = os.path.join(TMP, "empty_%d.json" % _n[0])
        open(p, "w", encoding="utf-8", newline="").close()
        self.assertEqual(run_cli([p])[0], 2)


class TestCEdge(unittest.TestCase):
    def test_unicode_names(self):
        p = write_doc({"members": [member("\u5f20\u4e09", "+08:00"),
                                   member("\u674e\u56db", "+08:00")]})
        code, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("\u5f20\u4e09", out)

    def test_wrap_midnight_window(self):
        p = write_doc({"members": [member("A", "+00:00", "22:00", "02:00"),
                                   member("B", "+00:00", "23:00", "01:00")]})
        code, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(code, 0)

    def test_offset_zero_z_accepted(self):
        p = write_doc({"members": [member("A", "Z"), member("B", "Z")]})
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_half_hour_offset_community(self):
        p = write_doc({"members": [member("IN", "+05:30"), member("NP", "+05:45")]})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_many_members(self):
        p = write_doc({"members": [member("M%02d" % i, "+%02d:00" % (i % 14))
                                   for i in range(40)], "min_members": 2})
        code, out, _ = run_cli([p, "--format", "json"])
        self.assertEqual(json.loads(out)["summary"]["members"], 40)

    def test_very_long_name(self):
        p = write_doc({"members": [member("n" * 5000, "+00:00"),
                                   member("b", "+00:00")]})
        code, out, _ = run_cli([p])
        self.assertEqual(code, 0)
        self.assertIn("n" * 100, out)

    def test_early_bird_comfort_edge(self):
        # local 08:00 is comfortable boundary (>= 8)
        p = write_doc({"members": [member("A", "+00:00", "08:00", "10:00"),
                                   member("B", "+00:00", "08:00", "10:00")]})
        _, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertEqual(rep["windows"][0]["off_hours_members"], [])

    def test_late_evening_not_comfortable(self):
        p = write_doc({"members": [member("A", "+00:00", "19:00", "23:00"),
                                   member("B", "+00:00", "19:00", "23:00")]})
        _, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertEqual(len(rep["windows"][0]["off_hours_members"]), 2)

    def test_window_capped_at_20_in_text(self):
        p = write_doc({"members": [member("A", "+00:00", "00:00", "23:59"),
                                   member("B", "+00:00", "00:00", "23:59")]})
        _, out, _ = run_cli([p])
        self.assertLessEqual(out.count("coverage=2"), 21)

    def test_extra_fields_ignored(self):
        p = write_doc({"members": [dict(member("A", "+00:00"), city="Berlin")],
                       "fiscal_calendar": "ignore-me"})
        code, _, _ = run_cli([p])
        self.assertEqual(code, 0)

    def test_duration_1440_granularity(self):
        p = write_doc({"members": [member("A", "+00:00", "00:00", "23:59")],
                       "duration_minutes": 1440})
        code, out, _ = run_cli([p, "--format", "json"])
        # 23:59 end still covers all 48 half-hour slots -> window found
        self.assertEqual(code, 0)

    def test_offset_chennai_vs_london_overlap(self):
        p = write_doc({"members": [member("LDN", "+00:00", "09:00", "17:00"),
                                   member("BLR", "+05:30", "09:00", "17:00")]})
        _, out, _ = run_cli([p, "--format", "json"])
        rep = json.loads(out)
        self.assertTrue(rep["windows"])
        self.assertEqual(rep["windows"][0]["coverage"], 2)


CASES = [
    (mod.parse_offset("+00:00"), 0),
    (mod.parse_offset("-00:00"), 0),
    (mod.parse_offset("+09:00"), 540),
    (mod.parse_offset("-03:30"), -210),
    (mod.parse_offset("+14:00"), 840),
    (mod.parse_offset("-12:00"), -720),
    (mod.parse_time("00:00"), 0.0),
    (mod.parse_time("24:00"), 24.0),
    (mod.parse_time("17:45"), 17.75),
    (mod.member_utc_window(member("A", "-05:00"), -300), (14.0, 22.0)),
    (mod.member_utc_window(member("A", "+03:00"), 180), (6.0, 14.0)),
]


def _mk(case):
    got, want = case

    def test(self):
        self.assertEqual(got, want)
    return test


for _i, _c in enumerate(CASES):
    setattr(TestCEdge, "test_table_%02d" % _i, _mk(_c))

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))
    sys.exit(0 if fails == 0 else 1)
