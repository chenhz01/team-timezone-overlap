# -*- coding: utf-8 -*-
"""team-timezone-overlap — enumerate common working windows across timezones.

Pure standard library. Input: JSON member list with UTC offsets and local
work hours. Output: all common windows (UTC + per-member local times),
coverage counts, off-hours burden, and a fairness rotation plan.
No DST handling: offsets are fixed UTC offsets as declared.
Exit codes: 0 = at least one common window, 1 = no window satisfies the
requirement, 2 = input error.
"""
import argparse
import json
import re
import sys

SLOT_MINUTES = 30
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES  # 48
COMFORT_START = 8.0   # local hours considered comfortable
COMFORT_END = 18.0

_OFFSET = re.compile(r"^([+-])(\d{2}):?(\d{2})$|^Z$", re.IGNORECASE)
_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_offset(text):
    """Return offset in minutes east of UTC, or raise ValueError."""
    if text in ("Z", "z"):
        return 0
    m = _OFFSET.match(str(text).strip())
    if not m or m.group(1) is None:
        raise ValueError("invalid UTC offset %r (use +HH:MM / -HH:MM / Z)" % text)
    sign = -1 if m.group(1) == "-" else 1
    hh, mm = int(m.group(2)), int(m.group(3))
    if hh > 14 or mm > 59:
        raise ValueError("offset %r out of range (|offset| <= 14:00)" % text)
    return sign * (hh * 60 + mm)


def parse_time(text):
    """Return local hour as float, or raise ValueError."""
    m = _TIME.match(str(text).strip())
    if not m:
        raise ValueError("invalid time %r (use HH:MM)" % text)
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 24 or mi > 59 or (h == 24 and mi != 0):
        raise ValueError("time %r out of range" % text)
    return h + mi / 60.0


def _mod24(x):
    return x % 24.0


def member_utc_window(member, off_minutes):
    """Return (utc_start, utc_end) in hours; end may exceed 24 (no wrap yet)."""
    off = off_minutes / 60.0
    s = parse_time(member["work_start"]) - off
    e = parse_time(member["work_end"]) - off
    if e <= s:
        e += 24.0
    return s, e


def _covers(window, hour_float):
    s, e = window
    h = hour_float
    if h < s:
        h += 24.0
    return s <= h < e


def validate_member(m, index):
    if not isinstance(m, dict):
        raise ValueError("member #%d must be an object" % index)
    if not isinstance(m.get("name"), str) or not m["name"].strip():
        raise ValueError("member #%d needs a non-empty 'name'" % index)
    parse_offset(m.get("utc_offset", ""))
    parse_time(m.get("work_start", ""))
    parse_time(m.get("work_end", ""))
    if parse_time(m["work_start"]) == parse_time(m["work_end"]):
        raise ValueError("member %r: work_start == work_end (empty or 24h day?)" % m["name"])
    return m


def analyze(doc):
    if not isinstance(doc, dict):
        raise ValueError("top-level JSON must be an object")
    members = doc.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("need a non-empty 'members' array")
    parsed = []
    for i, m in enumerate(members):
        validate_member(m, i)
        off = parse_offset(m["utc_offset"])
        s, e = member_utc_window(m, off)
        parsed.append({"name": m["name"], "off": off,
                       "window": (s, e)})

    n = len(parsed)
    min_members = doc.get("min_members", n)
    duration_h = doc.get("duration_minutes", 60) / 60.0
    if isinstance(min_members, bool) or not isinstance(min_members, int) \
            or min_members < 1 or min_members > n:
        raise ValueError("min_members must be an integer in [1, %d]" % n)
    if not isinstance(doc.get("duration_minutes", 60), int) or duration_h <= 0 \
            or duration_h > 24:
        raise ValueError("duration_minutes must be an integer in [1, 1440]")

    slots_needed = int(-(-duration_h * 60 // SLOT_MINUTES))  # ceil
    coverage = [sum(1 for p in parsed if _covers(p["window"], k * SLOT_MINUTES / 60.0))
                for k in range(SLOTS_PER_DAY)]

    # maximal runs of slots meeting min_members with length >= slots_needed
    windows = []
    k = 0
    while k < SLOTS_PER_DAY:
        if coverage[k] >= min_members:
            j = k
            while j < SLOTS_PER_DAY and coverage[j] >= min_members:
                j += 1
            run_len = j - k
            if run_len >= slots_needed:
                start_h = k * SLOT_MINUTES / 60.0
                end_h = start_h + run_len * SLOT_MINUTES / 60.0
                participants = [p for p in parsed
                                if all(_covers(p["window"], hh)
                                       for hh in (start_h + x * SLOT_MINUTES / 60.0
                                                  for x in range(run_len)))]
                off_hours = []
                for p in parsed:
                    local = _mod24(start_h + p["off"])
                    if p in participants and not (COMFORT_START <= local < COMFORT_END):
                        off_hours.append(p["name"])
                windows.append({
                    "utc_start": "%02d:%02d" % (int(start_h), round((start_h % 1) * 60)),
                    "utc_end": "%02d:%02d" % (int(end_h) % 24, round((end_h % 1) * 60)),
                    "coverage": len(participants),
                    "participants": [p["name"] for p in participants],
                    "off_hours_members": off_hours,
                })
            k = j
        else:
            k += 1

    windows.sort(key=lambda w: (-w["coverage"], len(w["off_hours_members"]),
                                w["utc_start"]))
    rotation = [w["utc_start"] for w in windows[:5]]
    report = {
        "tool": "team-timezone-overlap",
        "summary": {"members": n, "min_members": min_members,
                    "duration_minutes": doc.get("duration_minutes", 60),
                    "windows_found": len(windows),
                    "best_coverage": windows[0]["coverage"] if windows else 0},
        "windows": windows,
        "fairness_rotation": (rotation if len(windows) > 1 else []),
        "verdict": ("%d common window(s); rotate among top %d to share off-hours burden"
                    % (len(windows), min(5, len(windows)))
                    if windows else
                    "no common window: relax min_members or duration"),
    }
    return report


def render_text(report):
    lines = ["team-timezone-overlap report", "=" * 30]
    for w in report["windows"][:20]:
        lines.append("UTC %s-%s  coverage=%d  off-hours=%s  %s"
                     % (w["utc_start"], w["utc_end"], w["coverage"],
                        ",".join(w["off_hours_members"]) or "-", ",".join(w["participants"])))
    if report["fairness_rotation"]:
        lines.append("fairness rotation: %s" % " -> ".join(report["fairness_rotation"]))
    s = report["summary"]
    lines.append("summary: %d members, need %d, duration %d min, %d window(s), best coverage %d"
                 % (s["members"], s["min_members"], s["duration_minutes"],
                    s["windows_found"], s["best_coverage"]))
    lines.append("verdict: %s" % report["verdict"])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="team-timezone-overlap",
        description="Enumerate common working windows across team timezones (fixed offsets, no DST).")
    parser.add_argument("file", help="team JSON path")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print("error: invalid JSON in %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    try:
        report = analyze(doc)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0 if report["summary"]["windows_found"] else 1


if __name__ == "__main__":
    sys.exit(main())
