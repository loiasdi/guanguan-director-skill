#!/usr/bin/env python3
"""Validate shot-timing-v2 fields in director sequence Markdown files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


YAML_BLOCK = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)
SHOT_START = re.compile(r"(?m)^  - local_shot_id:\s*(\S+)\s*$")


def value(block: str, field: str) -> str | None:
    match = re.search(rf"(?m)^\s+{re.escape(field)}:\s*(.*?)\s*$", block)
    return match.group(1) if match else None


FAST_RATE_HINTS = ("抢着说", "快速说", "抢话", "打断")
SLOW_RATE_HINTS = ("缓慢说", "一字一顿")
PHASE_BOILERPLATE = (
    "形成镜头进入状态",
    "主要动作或信息被观众读取",
    "动作结果稳定并提供下一镜入口",
    "信息被观众读取",
    "提供下一镜入口",
)


def normalize_visible_action(action: str) -> str:
    for phrase in PHASE_BOILERPLATE:
        action = action.replace(phrase, "")
    return re.sub(r"[\s，。；、,:：;]", "", action)


def sequence_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            files.extend(sorted(target.glob("*.md")))
        elif target.is_file():
            files.append(target)
        else:
            raise FileNotFoundError(target)
    return files


def validate_shot(path: Path, shot_id: str, block: str) -> list[str]:
    errors: list[str] = []
    required = ("timing_mode", "timing_method", "duration_seconds", "duration_basis")
    for field in required:
        if value(block, field) in (None, "", "null"):
            errors.append(f"{path}: {shot_id}: missing {field}")

    basis = value(block, "duration_basis") or ""
    if "=" not in basis or ("→" not in basis and "->" not in basis):
        errors.append(f"{path}: {shot_id}: duration_basis must contain a reproducible equation and rounding result")

    timeline = "visual_timeline:" in block
    phase_lines = re.findall(r"(?m)^\s+-\s+(?:\{)?phase_id:.*$", block)
    phase_count = len(phase_lines) or len(re.findall(r"phase_id:\s*P?[\w.-]+", block))
    if not timeline or phase_count == 0:
        errors.append(f"{path}: {shot_id}: missing visual_timeline with ordered phases")
    else:
        timeline_start = block.find("visual_timeline:")
        timeline_text = block[timeline_start:]
        if "visible_action:" not in timeline_text or not re.search(r"(?<![A-Za-z_])source:", timeline_text):
            errors.append(f"{path}: {shot_id}: visual_timeline phases require visible_action and source")
        change_types = re.findall(r"change_type:\s*([a-z_]+)", timeline_text)
        if len(change_types) < phase_count:
            errors.append(f"{path}: {shot_id}: every visual_timeline phase requires change_type")
        actions = re.findall(r"(?m)^\s+visible_action:\s*(.*?)\s*$", timeline_text)
        if any(phrase in action for action in actions for phrase in PHASE_BOILERPLATE):
            errors.append(f"{path}: {shot_id}: visual_timeline uses non-visual phase boilerplate")
        normalized_actions = [normalize_visible_action(action) for action in actions]
        if len(normalized_actions) >= 2 and len(set(normalized_actions)) < len(normalized_actions):
            errors.append(f"{path}: {shot_id}: visual_timeline repeats the same visible event across phases")
        coverage = value(block, "visual_coverage") or ""
        covered_phase_ids = set(re.findall(r"P[\w.-]+", coverage))
        phase_ids = set(re.findall(r"phase_id:\s*(?:\{)?(P[\w.-]+)", timeline_text))
        if not coverage or not phase_ids.issubset(covered_phase_ids):
            errors.append(f"{path}: {shot_id}: visual_coverage must reference every visual_timeline phase")
        duration_raw = value(block, "duration_seconds") or ""
        duration_match = re.match(r"\s*(\d+(?:\.\d+)?)", duration_raw)
        if duration_match and float(duration_match.group(1)) >= 8:
            if phase_count < 2:
                errors.append(f"{path}: {shot_id}: shots >= 8 seconds require at least 2 visual_timeline phases")
            if len(set(change_types)) < 2:
                errors.append(f"{path}: {shot_id}: shots >= 8 seconds require at least 2 distinct change_type values")

    method = value(block, "timing_method")
    mode = value(block, "timing_mode")
    evidence = value(block, "timing_evidence")
    if method == "measured_audio" and evidence in (None, "", "null", "-"):
        errors.append(f"{path}: {shot_id}: measured_audio requires timing_evidence")

    if mode in ("dialogue", "voiceover", "mixed"):
        if "spoken_segments" not in block:
            errors.append(f"{path}: {shot_id}: dialogue timing missing spoken_segments")
        if method == "deterministic_fallback":
            for field in ("effective_char_count", "rate:", "pause_seconds", "subtotal_seconds"):
                if field not in block:
                    errors.append(f"{path}: {shot_id}: deterministic timing missing {field.rstrip(':')}")
            for segment in re.findall(r"(?m)^\s+-\s+\{speaker:.*$", block):
                char_count = re.search(r"effective_char_count:\s*(\d+)", segment)
                rate_match = re.search(r"\brate:\s*([0-9]+(?:\.[0-9]+)?)", segment)
                source_match = re.search(r"rate_source:\s*([^,}]+)", segment)
                if not char_count or not rate_match:
                    continue
                rate = float(rate_match.group(1))
                if rate not in (3.0, 5.0, 6.0):
                    errors.append(f"{path}: {shot_id}: Chinese deterministic rate must be 3.0, 5.0, or 6.0")
                    continue
                source = source_match.group(1) if source_match else ""
                if rate == 6.0 and not any(hint in source for hint in FAST_RATE_HINTS):
                    errors.append(f"{path}: {shot_id}: rate 6.0 requires fast/interruption rate_source")
                if rate == 3.0 and not any(hint in source for hint in SLOW_RATE_HINTS):
                    errors.append(f"{path}: {shot_id}: rate 3.0 requires slow rate_source")
                if rate == 5.0 and any(hint in source for hint in FAST_RATE_HINTS + SLOW_RATE_HINTS):
                    errors.append(f"{path}: {shot_id}: explicit fast/slow rate_source cannot use default 5.0")
        if method == "measured_audio" and "measured_seconds" not in block:
            errors.append(f"{path}: {shot_id}: measured_audio missing measured_seconds")

    for event_line in re.findall(r"(?m)^\s+- \{event:.*$", block):
        if "event_source:" not in event_line:
            errors.append(f"{path}: {shot_id}: timed event missing event_source")

    viewer_reads = value(block, "viewer_reads")
    if mode in ("empty", "static_empty"):
        if viewer_reads in (None, "", "null", "-"):
            errors.append(f"{path}: {shot_id}: static empty shot missing viewer_reads")
        if value(block, "exit_condition") in (None, "", "null", "-"):
            errors.append(f"{path}: {shot_id}: static empty shot missing exit_condition")
    return errors


def validate_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    blocks = [block for block in YAML_BLOCK.findall(text) if "shots:" in block]
    if not blocks:
        return [f"{path}: no YAML sequence block containing shots"]

    for block in blocks:
        if not re.search(r"(?m)^timing_schema:\s*shot-timing-v2\s*$", block):
            errors.append(f"{path}: missing timing_schema: shot-timing-v2")
        if "duration_budget_seconds" in block:
            errors.append(f"{path}: forbidden legacy duration_budget_seconds")

        required_match = re.search(r"(?m)^required_content_ids:\s*\[(.*?)\]\s*$", block)
        if not required_match:
            errors.append(f"{path}: missing required_content_ids source inventory")
        else:
            required_ids = {item.strip() for item in required_match.group(1).split(",") if item.strip()}
            covered_ids: set[str] = set()
            for content_ids in re.findall(r"(?m)^\s+source_content_ids:\s*\[(.*?)\]\s*$", block):
                covered_ids.update(item.strip() for item in content_ids.split(",") if item.strip())
            missing_ids = sorted(required_ids - covered_ids)
            if missing_ids:
                errors.append(f"{path}: required content not assigned to shots: {','.join(missing_ids)}")

        matches = list(SHOT_START.finditer(block))
        if not matches:
            errors.append(f"{path}: no shots found")
            continue
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
            errors.extend(validate_shot(path, match.group(1), block[match.start():end]))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="+", type=Path, help="Sequence Markdown files or directories")
    args = parser.parse_args()

    try:
        files = sequence_files(args.targets)
    except FileNotFoundError as error:
        print(f"not found: {error}", file=sys.stderr)
        return 2

    errors: list[str] = []
    for path in files:
        errors.extend(validate_file(path))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"shot-timing-v2 valid: {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
