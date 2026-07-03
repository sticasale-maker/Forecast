#!/usr/bin/env python3
"""
merge_ns.py  --  Build ns_hindcast.csv for the Swim Manly backtest tool.

Combines every NSW Nearshore Wave Tool hindcast export
(103218_hindcast_WaveTimeSeries*.csv) in a folder into ONE clean file:

    time, swell_height, swell_period, swell_dir, sea_height, sea_period, sea_dir

- de-dupes on the raw UTC timestamp (overlapping exports are safe)
- sorts chronologically
- converts the UTC column to Sydney local time (DST-aware) so hours line up
  with morning swim reports
- rounds values to 3 dp to keep the committed file small

USAGE
    python merge_ns.py                 # reads *.csv in the current folder
    python merge_ns.py C:\\path\\to\\folder
    python merge_ns.py <folder> -o ns_hindcast.csv --keep-utc

Then drop the resulting ns_hindcast.csv into the SAME GitHub directory as
newindex.html. The backtest ("Load bundled history" / auto-load on open) reads
it straight from there. Re-run this whenever you add more hindcast exports.
"""

import argparse
import csv
import glob
import os
import sys
from datetime import datetime, timezone, timedelta

# Sydney tz: prefer the real zoneinfo db (correct DST), fall back to a manual
# AEST/AEDT rule if the tz database is unavailable on the machine.
try:
    from zoneinfo import ZoneInfo
    SYD = ZoneInfo("Australia/Sydney")
    _HAVE_TZ = True
except Exception:  # pragma: no cover
    SYD = None
    _HAVE_TZ = False


def _nth_sunday_of_october(year):
    # NSW DST starts 1st Sunday of October (02:00), ends 1st Sunday of April.
    d = datetime(year, 10, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7)


def _first_sunday_of_april(year):
    d = datetime(year, 4, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7)


def utc_to_sydney(dt_utc):
    """dt_utc: naive datetime assumed UTC -> naive Sydney local datetime."""
    if _HAVE_TZ:
        return dt_utc.replace(tzinfo=timezone.utc).astimezone(SYD).replace(tzinfo=None)
    # Manual fallback: AEDT (+11) between Oct 1st-Sun and Apr 1st-Sun, else AEST (+10).
    y = dt_utc.year
    start = _nth_sunday_of_october(y).replace(hour=16)   # 02:00 AEDT == 16:00 UTC prev day-ish
    end = _first_sunday_of_april(y).replace(hour=16)
    is_dst = dt_utc >= start or dt_utc < end
    return dt_utc + timedelta(hours=11 if is_dst else 10)


def find_col(headers, *needles):
    """Return index of the first header containing all needle substrings (case-insensitive)."""
    for i, h in enumerate(headers):
        hl = h.strip().lower()
        if all(n in hl for n in needles):
            return i
    return -1


def parse_time(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def rnd(v):
    try:
        return round(float(v), 3)
    except (TypeError, ValueError):
        return ""


def main():
    ap = argparse.ArgumentParser(description="Merge NSW hindcast exports into ns_hindcast.csv")
    ap.add_argument("folder", nargs="?", default=".", help="folder with the hindcast CSVs (default: current)")
    ap.add_argument("-o", "--out", default="ns_hindcast.csv", help="output filename")
    ap.add_argument("--pattern", default="*WaveTimeSeries*.csv", help="glob pattern for input files")
    ap.add_argument("--keep-utc", action="store_true", help="keep UTC timestamps instead of converting to Sydney local")
    args = ap.parse_args()

    if not _HAVE_TZ and not args.keep_utc:
        print("  [warn] zoneinfo unavailable; using manual AEST/AEDT rule. "
              "Install tzdata (`pip install tzdata`) for exact DST, or use --keep-utc.")

    paths = sorted(glob.glob(os.path.join(args.folder, args.pattern)))
    if not paths:
        print("No files matching '%s' in %s" % (args.pattern, os.path.abspath(args.folder)))
        sys.exit(1)

    merged = {}   # raw-utc-string -> output row list
    total_read = 0
    for p in paths:
        with open(p, "r", encoding="utf-8-sig", newline="") as f:
            rdr = csv.reader(f)
            try:
                headers = next(rdr)
            except StopIteration:
                print("  [skip] %s (empty)" % os.path.basename(p))
                continue
            ci_time = find_col(headers, "utc") if find_col(headers, "utc") > -1 else 0
            ci_swh = find_col(headers, "swell", "height")
            ci_swp = find_col(headers, "swell", "period")
            ci_swd = find_col(headers, "swell", "direction")
            ci_seh = find_col(headers, "sea", "height")
            ci_sep = find_col(headers, "sea", "period")
            ci_sed = find_col(headers, "sea", "direction")
            if min(ci_swh, ci_swp, ci_swd, ci_seh, ci_sep, ci_sed) < 0:
                print("  [skip] %s (couldn't find sea/swell columns)" % os.path.basename(p))
                continue
            n = 0
            for row in rdr:
                if not row or len(row) <= max(ci_swh, ci_swp, ci_swd, ci_seh, ci_sep, ci_sed):
                    continue
                raw_t = row[ci_time].strip()
                if not raw_t:
                    continue
                dt = parse_time(raw_t)
                if dt is None:
                    continue
                if args.keep_utc:
                    tstr = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    tstr = utc_to_sydney(dt).strftime("%Y-%m-%d %H:%M")
                merged[raw_t] = (
                    dt, tstr,
                    rnd(row[ci_swh]), rnd(row[ci_swp]), rnd(row[ci_swd]),
                    rnd(row[ci_seh]), rnd(row[ci_sep]), rnd(row[ci_sed]),
                )
                n += 1
            total_read += n
            print("  %-48s %6d rows" % (os.path.basename(p), n))

    if not merged:
        print("No usable rows found.")
        sys.exit(1)

    rows = sorted(merged.values(), key=lambda r: r[0])
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "swell_height", "swell_period", "swell_dir",
                    "sea_height", "sea_period", "sea_dir"])
        for r in rows:
            w.writerow(list(r[1:]))

    first, last = rows[0][0], rows[-1][0]
    span_days = (last - first).total_seconds() / 86400.0
    dupes = total_read - len(rows)
    tz_label = "UTC" if args.keep_utc else ("Sydney local (zoneinfo)" if _HAVE_TZ else "Sydney local (manual DST)")
    print("-" * 60)
    print("  files merged : %d" % len(paths))
    print("  rows read    : %d  (deduped %d)" % (total_read, dupes))
    print("  rows written : %d" % len(rows))
    print("  UTC coverage : %s  ->  %s  (%.0f days)" % (
        first.strftime("%Y-%m-%d %H:%M"), last.strftime("%Y-%m-%d %H:%M"), span_days))
    print("  time column  : %s" % tz_label)
    print("  output       : %s" % os.path.abspath(args.out))
    print("  -> commit ns_hindcast.csv next to newindex.html on GitHub.")


if __name__ == "__main__":
    main()
