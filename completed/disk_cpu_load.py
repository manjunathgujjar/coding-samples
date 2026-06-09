#!/usr/bin/env python3
"""
Test CPU load imposed by a simple disk read operation.

Copyright (c) 2016 Canonical Ltd.

Authors:
    Rod Smith <rod.smith@canonical.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License version 3,
as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import argparse
import os
import stat as stat_mod
import subprocess
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test CPU load imposed by a simple disk read operation."
    )
    parser.add_argument(
        "--max-load", type=int, default=30, metavar="LOAD",
        help="Maximum acceptable CPU load percentage (default: 30)",
    )
    parser.add_argument(
        "--xfer", type=int, default=4096, metavar="MEBIBYTES",
        help="Amount of data to read in MiB (default: 4096)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Produce more verbose output",
    )
    parser.add_argument(
        "device", nargs="?", default="/dev/sda",
        help="Block device filename (default: /dev/sda)",
    )
    return parser.parse_args()


def normalize_device(device):
    if not device.startswith("/dev/"):
        device = "/dev/" + device
    return device


def validate_block_device(device):
    try:
        mode = os.stat(device).st_mode
    except FileNotFoundError:
        sys.exit(f"Unknown block device \"{device}\"")
    except PermissionError:
        sys.exit(f"Permission denied accessing \"{device}\" -- try running as root")
    if not stat_mod.S_ISBLK(mode):
        sys.exit(f"\"{device}\" is not a block device")


def read_cpu_stats():
    with open("/proc/stat") as f:
        for line in f:
            if line.startswith("cpu "):
                return [int(v) for v in line.split()[1:]]
    raise RuntimeError("Could not read CPU stats from /proc/stat")


def compute_cpu_load(start_stats, end_stats, verbose=False):
    # field index 3 is idle time; subtract from total to get active CPU time
    diff_idle = end_stats[3] - start_stats[3]
    diff_total = sum(end_stats) - sum(start_stats)
    diff_used = diff_total - diff_idle

    if verbose:
        print(f"Start CPU time = {sum(start_stats)}")
        print(f"End CPU time = {sum(end_stats)}")
        print(f"CPU time used = {diff_used}")
        print(f"Total elapsed = {diff_total}")

    if diff_total == 0:
        return 0
    return (diff_used * 100) // diff_total


def read_disk(device, mebibytes, verbose=False):
    if verbose:
        print("Beginning disk read....")
    try:
        subprocess.run(
            ["dd", f"if={device}", "of=/dev/null", "bs=1048576", f"count={mebibytes}"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        sys.exit(f"Error reading from {device}: {e.stderr.decode().strip()}")
    if verbose:
        print("Disk read complete!")


def main():
    args = parse_args()
    device = normalize_device(args.device)
    validate_block_device(device)

    print(f"Testing CPU load when reading {args.xfer} MiB from {device}")
    print(f"Maximum acceptable CPU load is {args.max_load}%")

    try:
        subprocess.run(
            ["blockdev", "--flushbufs", device],
            check=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        sys.exit(f"Failed to flush buffers for {device}: {e.stderr.decode().strip()}")

    start_stats = read_cpu_stats()
    read_disk(device, args.xfer, verbose=args.verbose)
    end_stats = read_cpu_stats()

    cpu_load = compute_cpu_load(start_stats, end_stats, verbose=args.verbose)
    print(f"Detected disk read CPU load is {cpu_load}%")

    if cpu_load > args.max_load:
        print("*** DISK CPU LOAD TEST HAS FAILED! ***")
        sys.exit(1)


if __name__ == "__main__":
    main()
