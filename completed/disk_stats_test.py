#!/usr/bin/env python3
"""
Verify a disk is visible to the OS and that its I/O stats update after
activity.

Copyright (c) 2016 Canonical Ltd.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License version 3,
as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Bugs fixed from the original shell script (disk_stats_test.sh):

  1. Line 56 — hdparm redirect: `hdparm -t "/dev/$DISK" 2&> /dev/null`
     is not valid bash. `2&>` is not a redirection operator; bash parses
     it as the literal argument "2" passed to hdparm followed by `&>`
     redirecting only stdout to /dev/null. stderr from hdparm was never
     suppressed, and hdparm received an unexpected argument. Fixed by
     passing stdout=DEVNULL, stderr=DEVNULL to subprocess.run.

  2. Lines 69-70 — missing /sys/block stat comparison: the second
     check_return_code call checks `$?` from the first check_return_code
     invocation, not from a comparison of SYS_STAT_BEGIN vs SYS_STAT_END.
     The `[[ "$SYS_STAT_BEGIN" != "$SYS_STAT_END" ]]` test was never
     executed, so a disk whose /sys/block stats did not change would
     silently pass. Fixed by explicitly comparing the two values.

Usage:
    disk_stats_test.py [DISK]

Parameters:
    DISK  Disk device name without /dev/, e.g. sda. Defaults to sda.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Verify disk visibility and stats activity."
    )
    parser.add_argument(
        "disk", nargs="?", default="sda",
        help="Disk name without /dev/ (default: sda)",
    )
    return parser.parse_args()


def record_error(errors, message, *details):
    print(f"ERROR: {message}", file=sys.stderr)
    for detail in details:
        print(f"output: {detail}", file=sys.stderr)
    errors.append(message)


def check_proc_partitions(disk, errors):
    found = any(
        disk in line and line.split()[-1] == disk
        for line in Path("/proc/partitions").read_text().splitlines()
    )
    if not found:
        record_error(errors, f"Disk {disk} not found in /proc/partitions")


def check_proc_diskstats(disk, errors):
    found = any(
        disk in line
        for line in Path("/proc/diskstats").read_text().splitlines()
        if line.split()[2] == disk
    )
    if not found:
        record_error(errors, f"Disk {disk} not found in /proc/diskstats")


def check_sys_block(disk, errors):
    matches = list(Path("/sys/block").glob(f"*{disk}*"))
    if not matches:
        record_error(errors, f"Disk {disk} not found in /sys/block")


def check_sys_block_stat(disk, errors):
    stat_path = Path(f"/sys/block/{disk}/stat")
    if not stat_path.exists() or stat_path.stat().st_size == 0:
        record_error(errors, f"stat is either empty or nonexistent in /sys/block/{disk}/")


def read_diskstats_line(disk):
    for line in Path("/proc/diskstats").read_text().splitlines():
        if line.split()[2] == disk:
            return line
    return ""


def read_sys_block_stat(disk):
    return Path(f"/sys/block/{disk}/stat").read_text().strip()


def generate_disk_activity(disk, errors):
    # Bug fix 1: original used `2&>` which is not a valid redirect operator.
    # "2" was passed as an argument to hdparm; only stdout was redirected.
    try:
        subprocess.run(
            ["hdparm", "-t", f"/dev/{disk}"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        record_error(errors, f"hdparm failed on /dev/{disk}")
    except FileNotFoundError:
        record_error(errors, "hdparm not found -- install hdparm")


def main():
    args = parse_args()
    disk = args.disk
    errors = []

    if "pmem" in disk:
        print(f"Disk {disk} appears to be an NVDIMM, skipping")
        sys.exit(0)

    check_proc_partitions(disk, errors)
    check_proc_diskstats(disk, errors)
    check_sys_block(disk, errors)
    check_sys_block_stat(disk, errors)

    if errors:
        sys.exit(1)

    proc_stat_begin = read_diskstats_line(disk)
    sys_stat_begin = read_sys_block_stat(disk)

    generate_disk_activity(disk, errors)

    # Wait for the stats files to catch up
    time.sleep(5)

    proc_stat_end = read_diskstats_line(disk)
    sys_stat_end = read_sys_block_stat(disk)

    if proc_stat_begin == proc_stat_end:
        record_error(
            errors,
            f"Stats in /proc/diskstats did not change",
            proc_stat_begin,
            proc_stat_end,
        )

    # Bug fix 2: original script re-used $? from the previous check_return_code
    # call here instead of actually comparing SYS_STAT_BEGIN vs SYS_STAT_END.
    # The /sys/block stat comparison was never performed.
    if sys_stat_begin == sys_stat_end:
        record_error(
            errors,
            f"Stats in /sys/block/{disk}/stat did not change",
            sys_stat_begin,
            sys_stat_end,
        )

    if not errors:
        print(f"PASS: Finished testing stats for {disk}")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
