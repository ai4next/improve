#!/usr/bin/env python3
"""自指测试：improve 必须能通过自己的审计，且文档与代码不漂移。

这是本仓库最该有的测试 —— 一个「改进 skill 的 skill」如果自己都过不了自己的门禁，
它的判据就没有说服力。
"""

from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402
from helpers import audit, skillmd  # noqa: E402

ROOT = helpers.ROOT
SKILL_MD = os.path.join(ROOT, "SKILL.md")
CONTRACT = os.path.join(ROOT, "references", "skill-contract.md")


class TestSelfAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit.run_audit(ROOT)

    def test_no_error_findings(self):
        errors = [f"{f.code} {f.file}:{f.line} {f.message}" for f in self.report.findings
                  if f.severity == "error"]
        self.assertEqual([], errors)

    def test_no_warn_findings(self):
        warns = [f"{f.code} {f.file}:{f.line} {f.message}" for f in self.report.findings
                 if f.severity == "warn"]
        self.assertEqual([], warns)

    def test_structural_score_is_full(self):
        self.assertEqual(self.report.structural["score"], 100.0)

    def test_cli_exit_zero(self):
        self.assertEqual(audit.main([ROOT]), 0)

    def test_cli_strict_exit_zero(self):
        self.assertEqual(audit.main([ROOT, "--strict"]), 0)


class TestDocsMatchCode(unittest.TestCase):
    def test_every_catalog_code_documented(self):
        with open(CONTRACT, encoding="utf-8") as handle:
            contract = handle.read()
        missing = [code for code in audit.CATALOG if code not in contract]
        self.assertEqual([], missing, f"这些诊断码没有写进 skill-contract.md：{missing}")

    def test_no_documented_code_absent_from_catalog(self):
        with open(CONTRACT, encoding="utf-8") as handle:
            contract = handle.read()
        documented = set(re.findall(r"^\|\s*`?([A-Z]{2}\d{3})`?\s*\|", contract, re.M))
        documented |= set(re.findall(r"^###\s+([A-Z]{2}\d{3})", contract, re.M))
        self.assertTrue(documented, "skill-contract.md 里没找到诊断码表格")
        self.assertEqual(set(), documented - set(audit.CATALOG),
                         "文档里有 CATALOG 中不存在的诊断码")

    def test_dimension_weights_match_rubric(self):
        rubric = os.path.join(ROOT, "references", "rubric.md")
        with open(rubric, encoding="utf-8") as handle:
            text = handle.read()
        for dim, weight in audit.DIM_WEIGHTS.items():
            with self.subTest(dim=dim):
                self.assertRegex(
                    text, rf"dim{dim}\b[^\n]*\b{weight}\b",
                    f"rubric.md 里没有 dim{dim} 权重 {weight} 的记录",
                )

    def test_rubric_weight_sum_matches_code(self):
        rubric = os.path.join(ROOT, "references", "rubric.md")
        with open(rubric, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(str(sum(audit.DIM_WEIGHTS.values())), text)


class TestSkillSelfConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SKILL_MD, encoding="utf-8") as handle:
            cls.text = handle.read()
        cls.fm = skillmd.load_frontmatter(cls.text)

    def test_frontmatter_name(self):
        self.assertEqual(self.fm["name"], "improve")

    def test_description_within_limit(self):
        self.assertLessEqual(len(self.fm["description"]), 1024)

    def test_every_referenced_file_exists(self):
        for rel in set(re.findall(r"`((?:references|scripts|tests)/[A-Za-z0-9_./-]+)`", self.text)):
            with self.subTest(path=rel):
                self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), f"{rel} 不存在")

    def test_every_reference_doc_is_routed(self):
        """references/ 下的每个文件都必须在 SKILL.md 的路由表里被指到。"""
        refs = sorted(os.listdir(os.path.join(ROOT, "references")))
        for name in refs:
            if not name.endswith(".md"):
                continue
            with self.subTest(ref=name):
                self.assertIn(name, self.text, f"references/{name} 没有被 SKILL.md 路由")

    def test_scripts_are_executable_python(self):
        for name in ("audit.py", "ledger.py", "skillmd.py"):
            path = os.path.join(ROOT, "scripts", name)
            with self.subTest(script=name):
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
                compile(source, path, "exec")

    def test_skill_md_has_all_required_sections(self):
        titles = " ".join(skillmd.section_titles(self.text))
        for marker in ("定位", "铁律", "参考文件路由", "执行流程", "证据闸门", "禁令", "输出契约"):
            with self.subTest(section=marker):
                self.assertIn(marker, titles)

    def test_no_self_referential_red_light_leak(self):
        """SKILL.md 讲红灯规则时必然写出红灯措辞 —— 那些行必须被判为元陈述而抑制。"""
        self.assertNotIn("RT001", [f.code for f in audit.run_audit(ROOT).findings])


if __name__ == "__main__":
    unittest.main(verbosity=2)
