# team-timezone-overlap

Find the meeting slots that actually work for a globally distributed team —
and rotate the pain fairly. Declare each member's UTC offset and local work
hours; the tool enumerates every common window, shows per-member local times,
flags who takes the call off-hours, and proposes a rotation plan across the
best windows. Pure CLI, no accounts, no calendar access. If your standup
time was chosen by whoever complained loudest, this is for you; if your team
sits in one timezone, you don't need it.

## Problem

Distributed teams pick meeting times by trial and error, and the burden
lands on whoever is newest or most junior — the 6:30 AM person is rarely the
one who chose it. Calendar apps show *pairs* of timezones nicely; nothing
small and offline enumerates *all* common windows for the whole team,
counts how many people each option drags out of bed, and makes the rotation
explicit.

## How it works

1. **Declarations** — each member has a fixed UTC offset (`+05:30`, `-08:00`,
   `Z`) and local work hours (`work_start`/`work_end`, `HH:MM`; a window
   past midnight wraps). Offsets validated to ±14:00; `start == end` is
   rejected as ambiguous.
2. **Enumeration** — each member's window is shifted to UTC; the day is
   scanned in 30-minute slots (48/day). A slot is "covered" by the members
   whose UTC window contains it. Maximal runs of covered slots at least
   `duration_minutes` long become candidate windows (default 60 min,
   require all members; `min_members` relaxes this).
3. **Fairness** — every candidate window records `off_hours_members`:
   participants whose local start is outside 08:00–18:00. Windows are ranked
   by (coverage desc, burden asc) and the top windows are returned as a
   round-robin rotation plan, so the 6:30 AM slot is shared, not owned.

Exit 0 if at least one window satisfies the requirement, 1 if none
(suggest relaxing `min_members` or duration), 2 on input errors.

## Quickstart (~2 min)

```bash
# 30 s: London + India overlap (classic 09:30 UTC window)
cat > /tmp/team.json <<'EOF'
{"members": [
  {"name": "LDN", "utc_offset": "+00:00", "work_start": "09:00", "work_end": "17:00"},
  {"name": "BLR", "utc_offset": "+05:30", "work_start": "09:00", "work_end": "17:00"}]}
EOF
python team_timezone_overlap.py /tmp/team.json

# 30 s: hopeless pair (exit 1 shows you why)
python team_timezone_overlap.py hopeless.json

# 1 min: JSON + rotation for your team wiki
python team_timezone_overlap.py team.json --format json
```

## Why not X?

- **TimeZoneBuddy** (wiradifit): a polished client-side web app — overlap
  heatmap, best-time finder, share-by-URL, `.ics` calendar export, DST
  handling. It is the better *visualizer*; this tool is the better
  *committer*: a diffable JSON/CLI verdict you can paste into a team decision
  and re-run in CI, plus explicit off-hours burden and rotation, which the
  heatmap does not quantify.
- **World Time Buddy / timeanddate.com meeting planners**: web UIs, manual
  clicking, no machine-readable output, no fairness notion, no way to encode
  "we decided to rotate weekly" as a checkable artifact.
- **Calendar scheduling assistants (Calendly, Reclaim)**: they optimize
  against live calendars of consenting accounts. Overkill (and a data-share)
  for a one-off team-policy decision; they also can't express "count how
  many people are off-hours" as a first-class output.

## How this differs from TimeZoneBuddy

TimeZoneBuddy is a browser application (open `index.html`, no backend) with
a color-coded overlap heatmap, automatic best-window detection, shareable
URLs, `.ics` export, and real-time DST handling. This repo is a headless CLI
with a different value proposition: deterministic JSON/text verdicts for
automation, a declared-input model (fixed UTC offsets in a JSON file you can
version), quantified off-hours burden per window, and a fairness rotation
plan. The deliberate trade: we do **not** handle DST and offer no calendar
export — a policy tool that changes its answer twice a year silently would
be worse than one that says "fixed offsets, re-check in summer".

## Performance

[Measured] Windows 10, Python 3.13, 2026-10-13: computing overlaps for 40
members across 14 offset zones took **2.8 ms** in-process (median of 50
runs). Cost is O(members × 48) slot scans plus output rendering — flat at
any realistic team size.

Reproduce:

```bash
python - <<'EOF'
import io, json, time, contextlib, tempfile, os
import team_timezone_overlap as m
members=[{"name":"M%02d"%i,"utc_offset":"+%02d:00"%(i%14),
          "work_start":"08:00","work_end":"18:00"} for i in range(40)]
p=os.path.join(tempfile.mkdtemp(),"t.json")
json.dump({"members":members,"min_members":2},open(p,"w",encoding="utf-8",newline=""))
t=time.perf_counter()
for _ in range(50):
    with contextlib.redirect_stdout(io.StringIO()):
        m.main([p,"--format","json"])
print("warm_ms=%.1f"%((time.perf_counter()-t)/50*1000))
EOF
```

## Minimal Fallback

No Python? The core is one table: write each member's UTC window on paper
(local hours minus offset), scan 00–24 in half-hour rows, and count members
per row. Ten minutes for a six-person team. The CLI adds repeatability and
the rotation bookkeeping — not new math.

## Design Trade-offs

Priority order: **honesty about DST > convenience > richness**. We accept
fixed offsets only, and the README says so twice, because silent DST
transitions are the #1 source of "the standup moved" incidents; a tool that
auto-adjusts invites decisions made in winter that break in summer.
The 30-minute slot grid is the second trade: windows are quantized to the
grid, so a 09:10–09:40 availability reads as 09:00–09:30. Slot-level
precision was rejected — scheduling on calendars is already 15/30-minute
quantized in practice.

## Limits & Second-order Effects

- No DST: members in DST-observing zones must re-declare offsets after
  transitions, or automation must rewrite the JSON twice a year.
- Fixed 08:00–18:00 "comfort" boundary is a Western-office default; night
  teams should adjust `COMFORT_START/END` in source.
- If the rotation is enforced rigidly, teams may declare narrower work
  windows to avoid being counted off-hours — treat the plan as a
  conversation artifact reviewed quarterly, not a cron job.

## FAQ

**Q: Can I model "Alice is fine until 22:00 but Bob sleeps at 21:00"?**
A: Yes — set their `work_end` accordingly; the comfort boundary only drives
the off-hours flag, not window validity.

**Q: Why 30-minute slots?**
A: Calendars quantize there anyway. Set `duration_minutes` to any multiple
of 30; sub-30 precision is false precision.

**Q: When NOT to use this?**
A: One-off 1:1 scheduling (use any calendar tool), or teams where DST
matters weekly — re-declaring offsets will annoy you more than the tool
helps. Also skip it if you need calendar invites; it outputs decisions,
not events.

## [Core Assumptions]

1. Team members can state a single fixed UTC offset and stable work hours;
   per-day variance (part-time, split shifts) is out of scope.
2. Fairness means rotating the off-hours burden across top windows, not
   equalizing it within a window.
3. 08:00–18:00 local is a reasonable comfort default; it is a constant, not
   a policy.
4. Half-hour granularity matches real-world meeting scheduling conventions.

Confidence: **High (≥80%)** for the window enumeration arithmetic — it is
elementary interval math over declared data. **Medium (60–79%)** that the
off-hours fairness rotation improves team satisfaction; it makes burden
visible, but whether visible burden changes decisions is a human question.

*Data and measurements as of 2026-10-13.*

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 105 purpose-built AI-engineering tools across neglected niches.

Related tools: [invoice-field-validator](https://github.com/chenhz01/invoice-field-validator) · [code-ownership-map](https://github.com/chenhz01/code-ownership-map) · [health-endpoint-spec](https://github.com/chenhz01/health-endpoint-spec)
