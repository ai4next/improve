#!/usr/bin/env python3
"""IMPROVEMENTS.jsonl 追加式账本。

三条纪律由脚本强制，不靠自觉：

1. **无 note 不写** —— 没有一句裁断理由的记录等于意见，拒绝落盘
2. **keep 必须有证据** —— 要么有 paired 票数（`--votes`），要么有通过的 audit 闸门
3. **只追加，不修改** —— 要修正历史就再写一条 `status=amend`，原记录留着

用法::

    python3 scripts/ledger.py record --file IMPROVEMENTS.jsonl \\
        --skill craft --round 1 --status keep --dimension dim3 \\
        --note "补三段式失败表，dim3 8.5→10" \\
        --votes 3-0 --before old.md --after new.md \\
        --audit-before before.json --audit-after after.json
    python3 scripts/ledger.py show --file IMPROVEMENTS.jsonl [--skill craft]
    python3 scripts/ledger.py verify --file IMPROVEMENTS.jsonl

退出码：`0` 成功 ｜ `1` 记录被纪律拒绝 / `verify` 发现问题 ｜ `2` 用法或 IO 错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit  # noqa: E402  (同目录模块)

TOOL = "improve/ledger"
VERSION = "1.0.0"

STATUSES = ("baseline", "keep", "revert", "error", "skip", "amend")
EVAL_MODES = ("paired", "full_test", "dry_run", "none")
DIMENSIONS = tuple(f"dim{i}" for i in range(1, 10)) + ("-",)
REQUIRED_KEYS = ("ts", "skill", "round", "status", "dimension", "note")
VOTE_RE = r"^\d+-\d+$"


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def build_record(args: argparse.Namespace) -> dict[str, Any]:
    """组装一条记录；违反纪律时抛 `ValueError`。"""
    note = (args.note or "").strip()
    if not note:
        raise ValueError("拒绝写入：`--note` 为空。没有一句裁断理由的记录等于意见。")

    if args.status not in STATUSES:
        raise ValueError(f"拒绝写入：status 必须是 {STATUSES} 之一，收到 {args.status!r}")

    if args.dimension not in DIMENSIONS:
        raise ValueError(f"拒绝写入：dimension 必须是 {DIMENSIONS} 之一，收到 {args.dimension!r}")

    if args.eval_mode not in EVAL_MODES:
        raise ValueError(f"拒绝写入：eval_mode 必须是 {EVAL_MODES} 之一，收到 {args.eval_mode!r}")

    votes = (args.votes or "").strip()
    if votes and not __import__("re").fullmatch(VOTE_RE, votes):
        raise ValueError(f"拒绝写入：`--votes` 形如 `3-0`，收到 {votes!r}")

    if args.status == "keep" and not votes and not args.audit_after:
        raise ValueError(
            "拒绝写入：keep 必须带证据 —— 要么 `--votes N-M`（paired 多数决），"
            "要么 `--audit-after`（确定性闸门通过）。两条都没有 = 无证据的 keep。"
        )

    if args.round < 0:
        raise ValueError("拒绝写入：round 不能为负")

    record: dict[str, Any] = {
        "ts": datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool": f"{TOOL} v{VERSION}",
        "skill": args.skill,
        "round": args.round,
        "status": args.status,
        "dimension": args.dimension,
        "eval_mode": args.eval_mode,
        "votes": votes,
        "note": note,
    }

    hashes: dict[str, str] = {}
    if args.before:
        hashes["before"] = _sha256(args.before)
    if args.after:
        hashes["after"] = _sha256(args.after)
    if hashes:
        record["hashes"] = hashes

    if args.audit_before or args.audit_after:
        gate: dict[str, Any] = {}
        if args.audit_before and args.audit_after:
            diff = audit.diff_reports(_load_json(args.audit_before), _load_json(args.audit_after))
            gate = {
                "gate": diff["gate"],
                "new": len(diff["new"]),
                "resolved": len(diff["resolved"]),
                "structural": diff["structural"],
            }
        else:
            payload = _load_json(args.audit_before or args.audit_after)
            gate = {"gate": "snapshot", "stats": payload.get("stats"),
                    "structural": payload.get("structural", {}).get("score")}
        record["audit"] = gate

    return record


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------

def cmd_record(args: argparse.Namespace) -> int:
    try:
        record = build_record(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ledger: {exc}", file=sys.stderr)
        return 1

    line = json.dumps(record, ensure_ascii=False)
    if args.dry_run:
        print(line)
        print("（--dry-run：没有写盘）", file=sys.stderr)
        return 0

    path = args.file
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    print(f"已追加 1 条到 {path}")
    print(f"  {record['ts']} · {record['skill']} · round {record['round']} · "
          f"{record['status']} · {record['dimension']}")
    return 0


def read_records(path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"第 {number} 行不是合法 JSON：{exc}") from exc
    return records


def cmd_show(args: argparse.Namespace) -> int:
    try:
        records = read_records(args.file)
    except (OSError, ValueError) as exc:
        print(f"ledger: {exc}", file=sys.stderr)
        return 2

    if args.skill:
        records = [r for r in records if r.get("skill") == args.skill]

    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return 0

    if not records:
        print(f"（{args.file} 里没有匹配记录）")
        return 0

    print(f"{'TS':17} {'SKILL':14} {'R':>2} {'STATUS':9} {'DIM':5} {'VOTES':6} NOTE")
    for r in records:
        print(f"{r.get('ts', '?')[:16]:17} {str(r.get('skill', '?'))[:14]:14} "
              f"{r.get('round', 0):>2} {str(r.get('status', '?')):9} "
              f"{str(r.get('dimension', '-')):5} {str(r.get('votes', '') or '-'):6} "
              f"{str(r.get('note', ''))[:60]}")

    kept = sum(1 for r in records if r.get("status") == "keep")
    reverted = sum(1 for r in records if r.get("status") == "revert")
    print(f"\n合计 {len(records)} 条：keep {kept} · revert {reverted} · "
          f"keep 率 {kept / len(records) * 100:.0f}%")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        records = read_records(args.file)
    except (OSError, ValueError) as exc:
        print(f"ledger: {exc}", file=sys.stderr)
        return 2

    problems: list[str] = []
    last_ts = ""
    for number, record in enumerate(records, 1):
        for key in REQUIRED_KEYS:
            if key not in record:
                problems.append(f"第 {number} 行缺字段 `{key}`")
        if record.get("status") not in STATUSES:
            problems.append(f"第 {number} 行 status 非法：{record.get('status')!r}")
        if record.get("dimension") not in DIMENSIONS:
            problems.append(f"第 {number} 行 dimension 非法：{record.get('dimension')!r}")
        if not str(record.get("note", "")).strip():
            problems.append(f"第 {number} 行 note 为空 —— 违反「无 note 不写」")
        ts = str(record.get("ts", ""))
        if ts and last_ts and ts < last_ts:
            problems.append(f"第 {number} 行时间戳倒退：{last_ts} → {ts}")
        last_ts = ts or last_ts

    if problems:
        for problem in problems:
            print(f"  ✗ {problem}")
        print(f"\nverify 失败：{len(problems)} 个问题 / {len(records)} 条记录")
        return 1

    print(f"verify 通过：{len(records)} 条记录，字段完整、时间戳单调、无空 note")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ledger.py", description="IMPROVEMENTS.jsonl 追加式账本")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="追加一条记录")
    rec.add_argument("--file", default="IMPROVEMENTS.jsonl")
    rec.add_argument("--skill", required=True)
    rec.add_argument("--round", type=int, default=0)
    rec.add_argument("--status", required=True, choices=STATUSES)
    rec.add_argument("--dimension", default="-")
    rec.add_argument("--eval-mode", dest="eval_mode", default="none", choices=EVAL_MODES)
    rec.add_argument("--note", required=True)
    rec.add_argument("--votes", default="", help="paired 多数决票数，形如 3-0")
    rec.add_argument("--before", help="改前的 SKILL.md，用于记哈希")
    rec.add_argument("--after", help="改后的 SKILL.md，用于记哈希")
    rec.add_argument("--audit-before", dest="audit_before", help="改前的 audit JSON")
    rec.add_argument("--audit-after", dest="audit_after", help="改后的 audit JSON")
    rec.add_argument("--dry-run", dest="dry_run", action="store_true")
    rec.set_defaults(func=cmd_record)

    show = sub.add_parser("show", help="展示记录")
    show.add_argument("--file", default="IMPROVEMENTS.jsonl")
    show.add_argument("--skill")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)

    verify = sub.add_parser("verify", help="校验账本完整性")
    verify.add_argument("--file", default="IMPROVEMENTS.jsonl")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
