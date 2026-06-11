#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a desktop notification for AJOS discovery")
    parser.add_argument("--title", default="AJOS Discovery")
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    if not shutil.which("notify-send"):
        print("notify-send not found; skipping desktop notification.", file=sys.stderr)
        return 1

    subprocess.run(
        ["notify-send", args.title, args.message],
        check=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
