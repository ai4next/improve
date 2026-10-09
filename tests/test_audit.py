#!/usr/bin/env python3
"""audit.py 的单元测试：诊断码、抑制规则、打分、diff 闸门、CLI 退出码。"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402
from helpers import audit  # noqa: E402


class AuditTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="improve-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def build(self, skill_md=helpers.CLEAN_SKILL_MD, **kwargs):
        return helpers.make_skill(self.tmp, skill_md=skill_md, **kwargs)

    def run_audit(self, skill_md=helpers.CLEAN_SKILL_MD, **kwargs):
        return audit.run_audit(self.build(skill_md, **kwargs))

    def cli(self, argv: list[str]) -> tuple[int, str]:
        """跑 CLI 并捕获 stdout，返回 `(退出码, 输出)`。"""
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = audit.main(argv)
        return code, buffer.getvalue()


class TestCatalogIntegrity(AuditTestCase):
    def test_every_code_well_formed(self):
        for code, (severity, dim, what, fix) in audit.CATALOG.items():
            with self.subTest(code=code):
                self.assertRegex(code, r"^[A-Z]{2}\d{3}$")
                self.assertIn(severity, ("error", "warn", "info"))
                self.assertIn(dim, range(1, 10))
                self.assertTrue(what.strip(), "判据不能为空")
                self.assertTrue(fix.strip(), "修法指针不能为空")

    def test_finding_severity_and_dim_come_from_catalog(self):
        """调用点写错 severity/dim 也漂移不了 —— Finding 以 CATALOG 为准。"""
        finding = audit.Finding("FM003", "error", "dim9", "SKILL.md", 1, "x")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(finding.dim, "dim1")

    def test_dim_weights_sum_to_100(self):
        self.assertEqual(sum(audit.DIM_WEIGHTS.values()), 100)

    def test_every_dim_has_a_mode(self):
        self.assertEqual(set(audit.DIM_WEIGHTS), set(audit.DIM_MODE))

    def test_machine_dims_cover_more_than_half_the_weight(self):
        machine = sum(w for d, w in audit.DIM_WEIGHTS.items() if audit.DIM_MODE[d] != "judge")
        self.assertGreater(machine, 50)

    def test_list_codes_matches_catalog(self):
        out = audit.render_codes()
        for code in audit.CATALOG:
            self.assertIn(code, out)


class TestCleanSkill(AuditTestCase):
    def test_clean_skill_has_zero_findings(self):
        report = self.run_audit()
        self.assertEqual([], [f"{f.code}@{f.file}:{f.line} {f.message}" for f in report.findings])

    def test_clean_skill_scores_ten_on_machine_dims(self):
        report = self.run_audit()
        for key, dim in report.dims.items():
            if dim["mode"] != "judge":
                self.assertEqual(dim["score"], 10.0, f"{key} 应为满分")

    def test_structural_score_excludes_judge_dim(self):
        report = self.run_audit()
        self.assertEqual(report.structural["score"], 100.0)
        self.assertEqual(report.structural["measured_weight"], 77)
        self.assertEqual(report.structural["total_weight"], 100)

    def test_exit_code_zero(self):
        self.assertEqual(self.cli([self.build()])[0], 0)


class TestFrontmatter(AuditTestCase):
    def test_missing_frontmatter_is_error(self):
        report = self.run_audit("# 光秃秃\n")
        self.assertIn("FM001", helpers.codes(report))
        self.assertEqual(report.stats["error"], 1)

    def test_missing_name_and_description(self):
        report = self.run_audit("---\nlicense: MIT\n---\n# T\n")
        self.assertIn("FM002", helpers.codes(report))
        self.assertIn("FM003", helpers.codes(report))

    def test_bad_name_charset(self):
        report = self.run_audit("---\nname: Bad_Name\ndescription: 做 X。适用：说「X」。不适用：Y。\n---\n# T\n")
        self.assertIn("FM004", helpers.codes(report))

    def test_name_directory_mismatch_is_warn(self):
        report = self.run_audit(
            "---\nname: other\ndescription: 做 X。适用：说「X」。不适用：Y。\n---\n# T\n", name="demo")
        findings = {f.code: f for f in report.findings}
        self.assertIn("FM005", findings)
        self.assertEqual(findings["FM005"].severity, "warn")

    def test_name_may_drop_skill_suffix(self):
        report = self.run_audit(
            "---\nname: demo\ndescription: 做 X。适用：说「X」。不适用：Y。\n---\n# T\n", name="demo-skill")
        self.assertNotIn("FM005", helpers.codes(report))

    def test_long_description_is_error(self):
        report = self.run_audit(
            f"---\nname: demo\ndescription: {'做 X。适用：X。不适用：Y。' * 80}\n---\n# T\n")
        self.assertIn("FM006", helpers.codes(report))

    def test_empty_tail_phrase(self):
        report = self.run_audit(
            "---\nname: demo\ndescription: 做 X。适用：说「X」。不适用：Y。请灵活应用\n---\n# T\n")
        self.assertIn("FM008", helpers.codes(report))

    def test_no_trigger_words(self):
        report = self.run_audit("---\nname: demo\ndescription: 这是一个工具。\n---\n# T\n")
        self.assertIn("FM007", helpers.codes(report))

    def test_license_and_version_info(self):
        report = self.run_audit("---\nname: demo\ndescription: 做 X。适用：X。不适用：Y。\n---\n# T\n")
        self.assertIn("FM010", helpers.codes(report))
        self.assertIn("FM011", helpers.codes(report))


class TestStructure(AuditTestCase):
    def test_dangling_reference_in_routing_table_is_error(self):
        text = helpers.CLEAN_SKILL_MD.replace("`references/guide.md`", "`references/missing.md`")
        report = self.run_audit(text)
        findings = [f for f in report.findings if f.code == "ST004"]
        self.assertTrue(findings)
        self.assertEqual(findings[0].severity, "error")

    def test_product_directory_reference_is_not_dangling(self):
        """产物目录结构里的 references/ 不是本 skill 的资源，不该报。"""
        text = helpers.CLEAN_SKILL_MD.replace(
            "## §二 参考文件路由\n\n| 时机 | 读取 |\n|------|------|\n| 总是 | `references/guide.md` |\n",
            "## §二 产物模型\n\n```\n~/.claude/skills/<slug>-persona/\n├── SKILL.md\n└── references/AXIOMS.md\n```\n\n"
            "交付 `references/AXIOMS.md` 与 `SKILL.md`。\n",
        )
        report = self.run_audit(text)
        self.assertNotIn("ST004", helpers.codes(report))

    def test_placeholder_reference_skipped(self):
        text = helpers.CLEAN_SKILL_MD.replace("`references/guide.md`", "`references/0X-xxx.md`")
        report = self.run_audit(text)
        self.assertNotIn("ST004", helpers.codes(report))

    def test_descriptive_mention_without_read_verb_skipped(self):
        text = helpers.CLEAN_SKILL_MD + "\n产物包含 `references/nowhere.md` 这一项。\n"
        report = self.run_audit(text)
        self.assertNotIn("ST004", helpers.codes(report))

    def test_no_blacklist_section(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD.replace("## §六 反例黑名单", "## §六 注意事项"))
        self.assertIn("ST006", helpers.codes(report))

    def test_no_output_contract(self):
        text = (helpers.CLEAN_SKILL_MD
                .replace("## §七 输出契约", "## §七 其它")
                .replace("## §五 🔴 CHECKPOINT · 交付前确认", "## §五 🔴 CHECKPOINT · 写盘前"))
        report = self.run_audit(text)
        self.assertIn("ST007", helpers.codes(report))

    def test_oversized_file(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n补充行。\n" * 700)
        self.assertIn("ST009", helpers.codes(report))

    def test_workflow_table_phases_count_as_numbered_steps(self):
        """distill 那种「Phase 表」也是编号步骤，不该报 ST003。"""
        report = self.run_audit(helpers.CLEAN_SKILL_MD.replace(
            "## §三 执行流程\n\n1. 读 `references/guide.md`，确认输入格式\n2. 写产物到指定路径\n3. 跑校验\n",
            "## §三 执行流程\n\n| Phase | 做什么 | 产出 |\n|-------|--------|------|\n"
            "| 0 · 入口分流 | 判类型 | 决策 |\n| 1 · 提炼 | 抽骨架 | 底稿 |\n",
        ))
        self.assertNotIn("ST003", helpers.codes(report))


class TestFailureModes(AuditTestCase):
    MINIMAL = "---\nname: demo\ndescription: 做 X。适用：X。不适用：Y。\nlicense: MIT\n---\n# T\n\n1. 做事\n"

    def test_no_failure_wording(self):
        report = self.run_audit(self.MINIMAL)
        self.assertIn("FL001", helpers.codes(report))

    def test_failure_wording_without_table(self):
        text = helpers.CLEAN_SKILL_MD.replace(
            "| 触发条件 | 一线修复 | 仍失败兜底 |\n|---------|---------|-----------|\n"
            "| 输入文件不存在 | 让用户补路径 | 终止并如实报告 |\n"
            "| 校验报错 | 按 code 修 | 两轮不降就停手报告 |\n",
            "遇到异常时，按下面的顺序排查一下看看。\n")
        report = self.run_audit(text)
        self.assertIn("FL002", helpers.codes(report))

    def test_two_column_failure_table(self):
        text = helpers.CLEAN_SKILL_MD.replace(
            "| 触发条件 | 一线修复 | 仍失败兜底 |\n|---------|---------|-----------|\n"
            "| 输入文件不存在 | 让用户补路径 | 终止并如实报告 |\n"
            "| 校验报错 | 按 code 修 | 两轮不降就停手报告 |\n",
            "| 失败场景 | 处理动作 |\n|---------|--------|\n| 输入不存在 | 补路径 |\n")
        report = self.run_audit(text)
        self.assertIn("FL003", helpers.codes(report))


class TestCheckpoints(AuditTestCase):
    def test_confirmation_without_marker(self):
        text = helpers.CLEAN_SKILL_MD.replace("## §五 🔴 CHECKPOINT · 交付前确认", "## §五 交付前")
        report = self.run_audit(text)
        self.assertIn("CP001", helpers.codes(report))

    def test_no_checkpoint_at_all(self):
        text = (helpers.CLEAN_SKILL_MD
                .replace("## §五 🔴 CHECKPOINT · 交付前确认", "## §五 交付前")
                .replace("展示 diff 与校验摘要，等用户确认后再写盘。", "直接写盘即可。"))
        report = self.run_audit(text)
        self.assertIn("CP002", helpers.codes(report))


class TestSpecificity(AuditTestCase):
    def test_three_soft_words_is_warn(self):
        text = helpers.CLEAN_SKILL_MD + "\n建议先试一下，根据情况可以考虑调整，视情况而定。\n"
        report = self.run_audit(text)
        findings = [f for f in report.findings if f.code == "SP001"]
        self.assertTrue(findings)
        self.assertTrue(all(f.severity == "warn" for f in findings))

    def test_one_soft_word_is_info(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n建议先试一下。\n")
        findings = [f for f in report.findings if f.code == "SP001"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "info")

    def test_noun_yijian_is_not_soft_wording(self):
        """`行动建议` 是名词，不是软化措辞。"""
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n区分事实判断、价值判断、行动建议。\n")
        self.assertNotIn("SP001", helpers.codes(report))

    def test_soft_word_in_code_span_ignored(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n反例：`建议` `根据情况` `视情况而定`。\n")
        self.assertNotIn("SP001", helpers.codes(report))

    def test_no_code_block_and_no_table(self):
        report = self.run_audit("---\nname: demo\ndescription: 做 X。适用：X。不适用：Y。\n---\n# T\n\n1. 做\n")
        found = helpers.codes(report)
        self.assertIn("SP002", found)
        self.assertIn("SP003", found)


class TestRuntime(AuditTestCase):
    def test_red_light_phrase(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n本 skill 在 Claude Code 里使用。\n")
        self.assertIn("RT001", helpers.codes(report))

    def test_meta_statement_suppressed(self):
        text = helpers.CLEAN_SKILL_MD + "\n红灯措辞「在 Claude Code 里」属于必须修的项。\n"
        report = self.run_audit(text)
        self.assertNotIn("RT001", helpers.codes(report))
        self.assertTrue(report.suppressed)

    def test_code_fence_suppressed(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n```\n在 Claude Code 里运行\n```\n")
        self.assertNotIn("RT001", helpers.codes(report))

    def test_runtime_bound_name_is_exempt(self):
        report = self.run_audit(
            "---\nname: demo-codex\ndescription: 做 X。适用：X。不适用：Y。\n---\n"
            "# T\n\n本 skill 在 Claude Code 里使用。\n", name="demo-codex")
        self.assertTrue(report.runtime_exempt)
        self.assertNotIn("RT001", helpers.codes(report))

    def test_single_runtime_install_path(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n装到 `~/.claude/skills/demo/`。\n")
        self.assertIn("RT003", helpers.codes(report))

    def test_multi_runtime_path_table_is_ok(self):
        report = self.run_audit(
            helpers.CLEAN_SKILL_MD
            + "\n| runtime | 路径 |\n|---|---|\n"
              "| Claude Code | `~/.claude/skills/demo/` |\n"
              "| Codex | `~/.codex/skills/demo/` |\n")
        self.assertNotIn("RT003", helpers.codes(report))

    def test_readme_is_scanned_too(self):
        report = self.run_audit(readme="# demo\n\n在 Claude Code 里使用。\n")
        self.assertTrue([f for f in report.findings if f.code == "RT001" and f.file == "README.md"])


class TestSafety(AuditTestCase):
    def test_destructive_command_outside_blacklist(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n回滚时直接跑 `git reset --hard HEAD~1`。\n")
        self.assertIn("SF001", helpers.codes(report))

    def test_destructive_command_inside_blacklist_is_ok(self):
        report = self.run_audit()
        self.assertNotIn("SF001", helpers.codes(report))

    def test_network_skill_without_credential_rule(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n本 skill 会抓取网页内容。\n")
        self.assertIn("SF002", helpers.codes(report))

    def test_network_skill_with_credential_rule_is_ok(self):
        report = self.run_audit(helpers.CLEAN_SKILL_MD + "\n本 skill 会抓取网页，但绝不把密钥写进日志。\n")
        self.assertNotIn("SF002", helpers.codes(report))


class TestSize(AuditTestCase):
    def test_readme_not_mentioning_skill_name(self):
        report = self.run_audit(readme="# 别的标题\n")
        self.assertIn("SZ002", helpers.codes(report))

    def test_no_readme_no_finding(self):
        report = self.run_audit(readme=None)
        self.assertNotIn("SZ002", helpers.codes(report))


class TestDiffGate(AuditTestCase):
    def snapshot(self, skill_md):
        return audit.to_json(audit.run_audit(self.build(skill_md)))

    def test_identical_snapshots_pass(self):
        payload = self.snapshot(helpers.CLEAN_SKILL_MD)
        result = audit.diff_reports(payload, payload)
        self.assertEqual(result["gate"], "pass")
        self.assertEqual(result["new"], [])

    def test_new_warn_fails_gate(self):
        before = self.snapshot(helpers.CLEAN_SKILL_MD)
        after = self.snapshot(helpers.CLEAN_SKILL_MD + "\n建议先试，根据情况可以考虑，视情况而定。\n")
        result = audit.diff_reports(before, after)
        self.assertEqual(result["gate"], "fail")
        self.assertTrue(result["blocking"])

    def test_new_info_only_passes_gate(self):
        before = self.snapshot(helpers.CLEAN_SKILL_MD)
        after = self.snapshot(helpers.CLEAN_SKILL_MD.replace("license: MIT\n", ""))
        result = audit.diff_reports(before, after)
        self.assertEqual(result["gate"], "pass")
        self.assertEqual([f["code"] for f in result["new"]], ["FM010"])

    def test_resolved_findings_reported(self):
        before = self.snapshot(helpers.CLEAN_SKILL_MD.replace("license: MIT\n", ""))
        after = self.snapshot(helpers.CLEAN_SKILL_MD)
        result = audit.diff_reports(before, after)
        self.assertEqual([f["code"] for f in result["resolved"]], ["FM010"])
        self.assertGreater(result["structural"]["delta"], 0)

    def test_evidence_change_is_not_a_regression(self):
        """同一条诊断的证据文本变了，不该被算成「一消一增」。"""
        before = self.snapshot(helpers.CLEAN_SKILL_MD + "\n建议先试一下。\n")
        after = self.snapshot(helpers.CLEAN_SKILL_MD + "\n建议先试两下。\n")
        result = audit.diff_reports(before, after)
        self.assertEqual(result["gate"], "pass")
        self.assertEqual(result["new"], [])
        self.assertEqual(result["resolved"], [])

    def test_cli_diff_exit_codes(self):
        before = self.snapshot(helpers.CLEAN_SKILL_MD)
        after = self.snapshot(helpers.CLEAN_SKILL_MD.replace("license: MIT\n", ""))
        good = os.path.join(self.tmp, "good.json")
        bad = os.path.join(self.tmp, "bad.json")
        for path, payload in ((good, before), (bad, after)):
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
        self.assertEqual(self.cli(["--diff", good, good])[0], 0)
        self.assertEqual(self.cli(["--diff", good, bad])[0], 0)  # 只多了一条 info
        # 缺文件 = 用法/IO 错误
        self.assertEqual(self.cli(["--diff", good, os.path.join(self.tmp, "nope.json")])[0], 2)


class TestCli(AuditTestCase):
    def test_missing_target_returns_2(self):
        self.assertEqual(self.cli([os.path.join(self.tmp, "nope")])[0], 2)

    def test_directory_without_skill_md_returns_2(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        self.assertEqual(self.cli([empty])[0], 2)

    def test_error_severity_returns_1(self):
        self.assertEqual(self.cli([self.build("# 没有 frontmatter\n")])[0], 1)

    def test_strict_makes_warn_fail(self):
        target = self.build(helpers.CLEAN_SKILL_MD.replace("## §六 反例黑名单", "## §六 注意事项"))
        self.assertEqual(self.cli([target])[0], 0)
        self.assertEqual(self.cli([target, "--strict"])[0], 1)

    def test_json_output_is_valid(self):
        code, output = self.cli([self.build(), "--json"])
        payload = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(payload["tool"], "improve/audit")
        self.assertIn("dim1", payload["dims"])
        self.assertEqual(payload["unverified"], ["dim8"])

    def test_out_writes_file(self):
        out = os.path.join(self.tmp, "snap.json")
        self.cli([self.build(), "--out", out])
        with open(out, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["skill"], "demo")

    def test_list_codes_exit_zero(self):
        code, output = self.cli(["--list-codes"])
        self.assertEqual(code, 0)
        self.assertIn("FM001", output)

    def test_human_output_mentions_structural_score(self):
        code, output = self.cli([self.build()])
        self.assertEqual(code, 0)
        self.assertIn("结构分", output)

    def test_min_severity_filters_output(self):
        _, output = self.cli([self.build(helpers.CLEAN_SKILL_MD.replace("license: MIT\n", "")),
                              "--min-severity", "warn"])
        self.assertNotIn("FM010", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
