#!/usr/bin/env python3
"""ledger.py 的单元测试：三条纪律、追加语义、verify。"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402
from helpers import ledger  # noqa: E402


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="improve-ledger-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.file = os.path.join(self.tmp, "IMPROVEMENTS.jsonl")

    def cli(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = ledger.main(argv)
        except SystemExit as exc:  # argparse 用 SystemExit 报用法错误
            code = int(exc.code or 0)
        return code, out.getvalue(), err.getvalue()

    def record(self, *extra: str) -> tuple[int, str, str]:
        return self.cli(["record", "--file", self.file, *extra])

    def lines(self) -> list[str]:
        if not os.path.exists(self.file):
            return []
        with open(self.file, encoding="utf-8") as handle:
            return [l for l in handle.read().splitlines() if l.strip()]


class TestDiscipline(LedgerTestCase):
    def test_empty_note_refused(self):
        code, _, err = self.record("--skill", "demo", "--status", "baseline", "--note", "  ")
        self.assertEqual(code, 1)
        self.assertIn("note", err)
        self.assertEqual(self.lines(), [])

    def test_keep_without_evidence_refused(self):
        code, _, err = self.record("--skill", "demo", "--status", "keep", "--note", "我改了")
        self.assertEqual(code, 1)
        self.assertIn("keep 必须带证据", err)
        self.assertEqual(self.lines(), [])

    def test_keep_with_votes_allowed(self):
        code, _, _ = self.record("--skill", "demo", "--status", "keep", "--note", "补失败表", "--votes", "3-0")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.lines()), 1)

    def test_keep_with_audit_after_allowed(self):
        snapshot = os.path.join(self.tmp, "a.json")
        with open(snapshot, "w", encoding="utf-8") as handle:
            json.dump({"stats": {"error": 0}, "structural": {"score": 90.0}}, handle)
        code, _, _ = self.record("--skill", "demo", "--status", "keep", "--note", "消了 2 条",
                                 "--audit-after", snapshot)
        self.assertEqual(code, 0)

    def test_bad_status_refused(self):
        code, _, err = self.record("--skill", "demo", "--status", "maybe", "--note", "x")
        self.assertEqual(code, 2)  # argparse choices 拦截
        self.assertNotEqual(err, "")

    def test_bad_votes_format_refused(self):
        code, _, err = self.record("--skill", "demo", "--status", "keep", "--note", "x", "--votes", "三比零")
        self.assertEqual(code, 1)
        self.assertIn("votes", err)

    def test_bad_dimension_refused(self):
        code, _, err = self.record("--skill", "demo", "--status", "baseline", "--note", "x",
                                   "--dimension", "dim99")
        self.assertEqual(code, 1)
        self.assertIn("dimension", err)

    def test_negative_round_refused(self):
        code, _, err = self.record("--skill", "demo", "--status", "baseline", "--note", "x", "--round", "-1")
        self.assertEqual(code, 1)
        self.assertIn("round", err)

    def test_dry_run_writes_nothing(self):
        code, out, _ = self.record("--skill", "demo", "--status", "baseline", "--note", "初始", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(self.lines(), [])
        self.assertIn("demo", out)


class TestRecord(LedgerTestCase):
    def test_append_only(self):
        self.record("--skill", "demo", "--status", "baseline", "--note", "初始评估")
        self.record("--skill", "demo", "--round", "1", "--status", "revert", "--note", "软化措辞变多",
                    "--votes", "0-3")
        self.assertEqual(len(self.lines()), 2)
        first = json.loads(self.lines()[0])
        self.assertEqual(first["status"], "baseline")
        self.assertEqual(json.loads(self.lines()[1])["status"], "revert")

    def test_required_fields_present(self):
        self.record("--skill", "demo", "--status", "baseline", "--note", "初始", "--dimension", "dim3")
        record = json.loads(self.lines()[0])
        for key in ledger.REQUIRED_KEYS:
            self.assertIn(key, record)
        self.assertEqual(record["dimension"], "dim3")
        self.assertIn("tool", record)

    def test_hashes_recorded(self):
        before = os.path.join(self.tmp, "b.md")
        after = os.path.join(self.tmp, "a.md")
        for path, body in ((before, "甲"), (after, "乙")):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
        self.record("--skill", "demo", "--status", "keep", "--note", "x", "--votes", "3-0",
                    "--before", before, "--after", after)
        record = json.loads(self.lines()[0])
        self.assertTrue(record["hashes"]["before"].startswith("sha256:"))
        self.assertNotEqual(record["hashes"]["before"], record["hashes"]["after"])

    def test_audit_diff_summary_recorded(self):
        import audit as audit_mod
        target = helpers.make_skill(self.tmp, name="demo")
        before = os.path.join(self.tmp, "before.json")
        after = os.path.join(self.tmp, "after.json")
        with open(before, "w", encoding="utf-8") as handle:
            json.dump(audit_mod.to_json(audit_mod.run_audit(target)), handle)
        with open(target + ".bak", "w", encoding="utf-8") as handle:
            handle.write(helpers.CLEAN_SKILL_MD)
        with open(os.path.join(target, "SKILL.md"), "a", encoding="utf-8") as handle:
            handle.write("\n建议先试，根据情况可以考虑，视情况而定。\n")
        with open(after, "w", encoding="utf-8") as handle:
            json.dump(audit_mod.to_json(audit_mod.run_audit(target)), handle)

        self.record("--skill", "demo", "--status", "revert", "--note", "退化",
                    "--audit-before", before, "--audit-after", after)
        gate = json.loads(self.lines()[0])["audit"]
        self.assertEqual(gate["gate"], "fail")
        self.assertGreater(gate["new"], 0)


class TestShowAndVerify(LedgerTestCase):
    def seed(self):
        self.record("--skill", "demo", "--status", "baseline", "--note", "初始评估")
        self.record("--skill", "demo", "--round", "1", "--status", "keep", "--note", "补失败表", "--votes", "3-0")
        self.record("--skill", "other", "--round", "1", "--status", "revert", "--note", "退化", "--votes", "0-3")

    def test_show_all(self):
        self.seed()
        code, out, _ = self.cli(["show", "--file", self.file])
        self.assertEqual(code, 0)
        self.assertIn("keep 率 33%", out)
        self.assertIn("demo", out)
        self.assertIn("other", out)

    def test_show_filtered_by_skill(self):
        self.seed()
        code, out, _ = self.cli(["show", "--file", self.file, "--skill", "demo"])
        self.assertEqual(code, 0)
        self.assertNotIn("other", out)

    def test_show_json(self):
        self.seed()
        code, out, _ = self.cli(["show", "--file", self.file, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)), 3)

    def test_show_missing_file_is_io_error(self):
        code, _, _ = self.cli(["show", "--file", os.path.join(self.tmp, "nope.jsonl")])
        self.assertEqual(code, 2)

    def test_verify_clean(self):
        self.seed()
        code, out, _ = self.cli(["verify", "--file", self.file])
        self.assertEqual(code, 0)
        self.assertIn("verify 通过", out)

    def test_verify_detects_missing_field(self):
        with open(self.file, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": "2026-01-01T00:00:00+0800", "skill": "x",
                                     "status": "keep", "note": "n"}, ensure_ascii=False) + "\n")
        code, out, _ = self.cli(["verify", "--file", self.file])
        self.assertEqual(code, 1)
        self.assertIn("round", out)

    def test_verify_detects_bad_status(self):
        with open(self.file, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": "2026-01-01T00:00:00+0800", "skill": "x", "round": 0,
                                     "status": "maybe", "dimension": "-", "note": "n"},
                                    ensure_ascii=False) + "\n")
        code, out, _ = self.cli(["verify", "--file", self.file])
        self.assertEqual(code, 1)
        self.assertIn("status 非法", out)

    def test_verify_detects_empty_note(self):
        with open(self.file, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": "2026-01-01T00:00:00+0800", "skill": "x", "round": 0,
                                     "status": "keep", "dimension": "-", "note": "  "},
                                    ensure_ascii=False) + "\n")
        code, out, _ = self.cli(["verify", "--file", self.file])
        self.assertEqual(code, 1)
        self.assertIn("note 为空", out)

    def test_verify_detects_time_regression(self):
        rows = [
            {"ts": "2026-02-01T00:00:00+0800", "skill": "x", "round": 1, "status": "keep",
             "dimension": "-", "note": "a"},
            {"ts": "2026-01-01T00:00:00+0800", "skill": "x", "round": 2, "status": "keep",
             "dimension": "-", "note": "b"},
        ]
        with open(self.file, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        code, out, _ = self.cli(["verify", "--file", self.file])
        self.assertEqual(code, 1)
        self.assertIn("时间戳倒退", out)

    def test_verify_detects_broken_json(self):
        with open(self.file, "w", encoding="utf-8") as handle:
            handle.write("{不是 json}\n")
        code, _, err = self.cli(["verify", "--file", self.file])
        self.assertEqual(code, 2)
        self.assertIn("不是合法 JSON", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
