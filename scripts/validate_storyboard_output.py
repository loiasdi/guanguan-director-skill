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
        sound = cells[6]
        if duration is None:
            errors.append(f"{path}: shot {shot_id}: invalid numeric time range")
            continue
        internal_labels = ("进入：", "过程：", "变化/反应：", "退出：")
        leaked = [label for label in internal_labels if label in content]
        if leaked:
            errors.append(f"{path}: shot {shot_id}: 画面内容泄露内部阶段标签 {','.join(leaked)}")
        sentence_units = [unit.strip() for unit in re.split(r"[。！？；;]+", content) if unit.strip()]
        minimum_sentences = 3 if duration >= 8 else 2 if duration >= 4 else 1
        if len(sentence_units) < minimum_sentences:
            errors.append(
                f"{path}: shot {shot_id}: {duration:g}秒镜头画面描述至少需要"
                f"{minimum_sentences}个按时间推进的自然句段"
            )
        if re.search(r"对白|\bOS\b|旁白|画外音|广播", sound) and not re.search(r"[：:\"“]", sound):
            errors.append(f"{path}: shot {shot_id}: 声音列只写了语言类别，没有保留具体原文")
        quoted_content = re.findall(r"[“\"]([^”\"]+)[”\"]", content)
        speech_verbs = re.search(r"说[：：“\"]|问[：：“\"]|回答|回应|低语|提起|谈到|告诉|宣布|开口道", content)
        visible_text_carrier = re.search(r"字幕|屏幕|显示器|信件|纸条|便签|标牌|招牌|广播文字", content)
        if (quoted_content or speech_verbs) and not visible_text_carrier:
            errors.append(f"{path}: shot {shot_id}: 语言内容写入了画面内容，应移到声音列")
        for quote in quoted_content:
            if quote and quote in sound and not visible_text_carrier:
                errors.append(f"{path}: shot {shot_id}: 台词在画面内容与声音列重复")

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
