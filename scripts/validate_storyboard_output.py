#!/usr/bin/env python3
"""Validate the public nine-column storyboard Markdown output."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TIME_RANGE = re.compile(r"^\s*(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\s*$")
REQUIRED_HEADER = ("镜号", "时长", "摄影角度", "景别", "画面内容", "场景", "声音", "备注", "叙事目的")


def seconds(value: str) -> int | None:
    match = TIME_RANGE.match(value)
    if not match:
        return None
    start_min, start_sec, end_min, end_sec = (int(item) for item in match.groups())
    return end_min * 60 + end_sec - (start_min * 60 + start_sec)


def validate(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    table_lines = [line for line in text.splitlines() if line.lstrip().startswith("|")]
    header_index = next(
        (index for index, line in enumerate(table_lines) if "画面内容" in line and "叙事目的" in line),
        None,
    )
    if header_index is None:
        return [f"{path}: no nine-column storyboard table found"]

    header = [cell.strip() for cell in table_lines[header_index].strip().strip("|").split("|")]
    if tuple(header[:9]) != REQUIRED_HEADER:
        errors.append(f"{path}: storyboard header must contain the nine required columns")

    row_number = 0
    for line in table_lines[header_index + 2 :]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 9 or not cells[0] or not cells[0].isdigit():
            continue
        row_number += 1
        shot_id = cells[0]
        duration = seconds(cells[1])
        content = cells[4]
        if duration is None:
            errors.append(f"{path}: shot {shot_id}: invalid numeric time range")
            continue
        required_labels = ("进入：", "过程：", "退出：")
        missing = [label for label in required_labels if label not in content]
        if missing:
            errors.append(f"{path}: shot {shot_id}: 画面内容 missing labels {','.join(missing)}")
        if duration >= 8 and "变化/反应：" not in content:
            errors.append(f"{path}: shot {shot_id}: shots >= 8 seconds require 变化/反应： in 画面内容")

    if row_number == 0:
        errors.append(f"{path}: no storyboard rows found")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    errors = validate(args.target)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"storyboard output valid: {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
