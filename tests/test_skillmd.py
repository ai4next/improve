#!/usr/bin/env python3
"""skillmd.py 解析原语的单元测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402
from helpers import skillmd  # noqa: E402


class TestSplitFrontmatter(unittest.TestCase):
    def test_basic(self):
        raw, body = skillmd.split_frontmatter("---\nname: x\n---\n# T\n")
        self.assertEqual(raw, "name: x")
        self.assertEqual(body, "# T")

    def test_dots_terminator(self):
        raw, body = skillmd.split_frontmatter("---\nname: x\n...\nbody")
        self.assertEqual(raw, "name: x")
        self.assertEqual(body, "body")

    def test_leading_blank_lines_and_bom(self):
        raw, _ = skillmd.split_frontmatter("\n\n\ufeff---\nname: x\n---\n")
        self.assertEqual(raw, "name: x")

    def test_missing_raises(self):
        with self.assertRaises(skillmd.FrontmatterError):
            skillmd.split_frontmatter("# 没有 frontmatter\n")

    def test_unclosed_raises(self):
        with self.assertRaises(skillmd.FrontmatterError):
            skillmd.split_frontmatter("---\nname: x\n# 没有结束标记\n")


class TestYamlSubset(unittest.TestCase):
    def test_scalars_and_quotes(self):
        parsed = skillmd.parse_yaml_subset('name: craft\nversion: "1.0"\ntag: \'a\'\n')
        self.assertEqual(parsed, {"name": "craft", "version": "1.0", "tag": "a"})

    def test_block_scalar_keeps_blank_lines(self):
        text = "description: |\n  第一段\n\n  第二段\nlicense: MIT\n"
        parsed = skillmd.parse_yaml_subset(text)
        self.assertEqual(parsed["description"], "第一段\n\n第二段")
        self.assertEqual(parsed["license"], "MIT")

    def test_block_scalar_ends_on_dedent(self):
        """craft-skill 的真实 bug：`不适用` 顶格写，就掉出 description 了。"""
        text = "description: |\n  正文\n\n不适用：纯静态图片。\nlicense: MIT\n"
        parsed = skillmd.parse_yaml_subset(text)
        self.assertEqual(parsed["description"], "正文")
        self.assertNotIn("不适用", parsed["description"])
        self.assertEqual(parsed["license"], "MIT")

    def test_folded_scalar(self):
        parsed = skillmd.parse_yaml_subset("d: >\n  甲\n  乙\n")
        self.assertEqual(parsed["d"], "甲 乙")

    def test_nested_map(self):
        parsed = skillmd.parse_yaml_subset('metadata:\n  version: "1.0"\n  author: ai4next\nname: x\n')
        self.assertEqual(parsed["metadata"], {"version": "1.0", "author": "ai4next"})
        self.assertEqual(parsed["name"], "x")

    def test_indented_list(self):
        parsed = skillmd.parse_yaml_subset("tags:\n  - a\n  - b\nname: x\n")
        self.assertEqual(parsed["tags"], ["a", "b"])

    def test_inline_list(self):
        self.assertEqual(skillmd.parse_yaml_subset("tags: [a, b]\n")["tags"], ["a", "b"])

    def test_comments_ignored(self):
        parsed = skillmd.parse_yaml_subset("# 注释\nname: x  # 行尾\n")
        self.assertEqual(parsed["name"], "x")

    def test_load_frontmatter_end_to_end(self):
        fm = skillmd.load_frontmatter(helpers.CLEAN_SKILL_MD)
        self.assertEqual(fm["name"], "demo")
        self.assertIn("把 A 变成 B", fm["description"])
        self.assertEqual(fm["metadata"]["author"], "ai4next")


class TestMasking(unittest.TestCase):
    def test_code_fences_masked_and_line_count_kept(self):
        text = "前\n```bash\n在 Claude Code 里\n```\n后\n"
        masked = skillmd.mask_code_fences(text)
        self.assertEqual(len(masked.splitlines()), len(text.splitlines()))
        self.assertNotIn("Claude Code", masked)
        self.assertIn("前", masked)

    def test_tilde_fence(self):
        masked = skillmd.mask_code_fences("~~~\nsecret\n~~~\n")
        self.assertNotIn("secret", masked)

    def test_unclosed_fence_masks_to_eof(self):
        masked = skillmd.mask_code_fences("前\n```\nsecret\n")
        self.assertNotIn("secret", masked)

    def test_inline_code_length_preserved(self):
        line = "用 `references/a.md` 就行"
        masked = skillmd.mask_inline_code(line)
        self.assertEqual(len(masked), len(line))
        self.assertNotIn("references/a.md", masked)

    def test_mask_all(self):
        masked = skillmd.mask_all("`建议` 与\n```\n建议\n```\n")
        self.assertNotIn("建议", masked)


class TestSections(unittest.TestCase):
    TEXT = "# A\n\n## B\n\n### C\n\n## D\n\n# E\n"

    def test_titles_and_levels(self):
        heads = skillmd.sections(self.TEXT)
        self.assertEqual([h["title"] for h in heads], ["A", "B", "C", "D", "E"])
        self.assertEqual([h["level"] for h in heads], [1, 2, 3, 2, 1])

    def test_end_line_stops_at_same_or_higher_level(self):
        heads = skillmd.sections(self.TEXT)
        by_title = {h["title"]: h for h in heads}
        self.assertEqual(by_title["B"]["end_line"], by_title["D"]["line"] - 1)
        self.assertEqual(by_title["C"]["end_line"], by_title["D"]["line"] - 1)
        self.assertEqual(by_title["A"]["end_line"], by_title["E"]["line"] - 1)

    def test_headings_inside_fence_ignored(self):
        heads = skillmd.sections("# A\n\n```\n# 不是标题\n```\n")
        self.assertEqual([h["title"] for h in heads], ["A"])

    def test_find_section(self):
        self.assertIsNotNone(skillmd.find_section(self.TEXT, "D"))
        self.assertIsNone(skillmd.find_section(self.TEXT, "Z"))

    def test_find_section_level_filter(self):
        self.assertIsNone(skillmd.find_section("# A\n\n## A\n", "a", level=3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
