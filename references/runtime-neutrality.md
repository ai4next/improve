# Runtime 中立性审查（canonical source）

> `SKILL.md` 与 [`skill-contract.md`](skill-contract.md) §3.6 引用本文件。
> **红灯/绿灯对照表、假阳性判别表、扫描命令只有这一份。**

---

## 1. 为什么这是 gate 项

Agent Skills 是跨 runtime 的格式——Claude Code、Codex、Cursor、Gemini CLI、OpenCode、
以及各类 skills-compatible runtime 都读同一份 `SKILL.md`。

**一个被误判为「单一 runtime 绑定」的 skill，会被其他 agent 直接拒绝安装。**
实例：`nuwa-skill` 因 README 写「在 Claude Code 里使用」被另一个 agent 拒绝。

**适用范围**：除非 skill 名**明确声明**绑定单一 runtime（如 `xxx-codex`、`xxx-for-claude-code`），
所有 skill 都必须通过本审查。`audit.py` 对这类名字自动豁免 RT 扫描。

---

## 2. 红灯信号

| 红灯类型 | 典型表现 | 危害 |
|---|---|---|
| Badge 钉死 | `[![Claude Code Skill]]`、`[![Cursor Only]]` | 首屏定调，其他 runtime 用户直接退出 |
| 措辞钉死 | 「在 Claude Code 里」「Cursor 用户可以」「Codex 中使用」 | agent 解析时误判为「不是给我用的」 |
| 安装命令钉死 | 只给 `~/.claude/skills/` 路径、只给 `/plugin install` | 不知道这是哪个 runtime 的命令的 agent 会拒绝 |
| 工具调用钉死 | 工作流硬编码单一 runtime 的私有工具，且不给替代方案 | 其他 runtime 没这些工具 → 流程跑不通 |
| 路径硬编码 | `~/.claude/skills/xxx/` 作为唯一路径 | 其他 runtime 用 `~/.codex/skills/` 等 |

**自动检测**：`RT001`（措辞）、`RT002`（badge）、`RT003`（安装路径）。

---

## 3. 绿灯措辞（推荐改写）

| 红灯 | 绿灯 |
|---|---|
| 「在 Claude Code 里」 | 「在你的 agent 里」/「在任何 skills-compatible runtime 中」 |
| 「Claude Code skill」 | 「Agent Skill」 |
| 「Claude Code 用户」 | 「skills-aware agent 用户」 |
| 单一 badge 钉死 | `Agent Skills Standard` + `skills.sh Compatible` + `Multi-Runtime` |
| 只给一行 `npx skills add ...` | 三层：① 自动检测的一行命令 ② 各 runtime 手动路径表 ③ 「作为参考资料读进 context」兜底 |
| 硬编码工具名 | 「用一个 browser automation 工具（例如 Chrome MCP、Playwright 等）」 |

---

## 4. 例外清单（允许出现的痕迹）

不是所有 runtime 相关字符都要清除。以下是**正当出现**：

1. **frontmatter `description` 里的触发词**——这是入口，其他 runtime 解析 frontmatter 时同样匹配
2. **生态内部联动的 skill 名引用**——如「与 `darwin-skill` 配套」
3. **明确标注的 runtime-specific 章节**——标题写明「仅某 runtime 可用」并说明是 nice-to-have
4. **commit message、changelog、内部脚本**——不属于用户读到的 skill 内容
5. **引用 / 演示该模式本身**——讲解红灯规则、列反例、贴扫描命令时，必然要字面写出这些措辞

---

## 5. 假阳性判别表

**这是本审查最容易出错的地方**：讲解 runtime 中立性的 skill（包括本 skill）必然
字面写出红灯措辞，机械按 grep 命中数判定会让它**永远判自己红灯，陷入自审死循环**。

| | 真红灯（须修） | 假阳性（不修） |
|---|---|---|
| **性质** | 把单 runtime 当**指令**：「在 Claude Code 里运行 X」 | 把这些措辞当**被描述的对象** |
| **位置** | 工作流步骤、首屏定调、安装说明 | 扫描命令本身、反例清单里引用的反例、「『X』是红灯措辞」这类元陈述、对照表 |
| **处理** | 进 P0 修复 | 记入 `suppressed`，不改 |

`audit.py` 的自动判别：

- **代码块内**的命中 → 抑制（`skillmd.mask_code_fences`）
- **含元陈述标记的行** → 抑制，记 `suppress_reason: meta_statement`
  （标记见 `audit.py` 的 `META_MARKERS`：红灯 / 假阳性 / 反例 / 禁令 / 措辞 / 扫描 / 中立 / 适配…）

**抑制结果必须留痕**：JSON 输出里的 `suppressed` 数组列出每一处被抑制的命中。
**人工复核时看得见，而不是被静默吞掉。**

---

## 6. 扫描时机

| 阶段 | 动作 |
|---|---|
| **P1 建基线** | `audit.py` 自动跑 RT 扫描；命中数写进基线报告 |
| **P4 改进循环** | 有 RT 命中 → **第一轮强制定为 P0「runtime 修复」**，优先于其他维度 |
| **P7 汇总** | 单独一栏展示命中数 `X → 0` 的修复进度 |

---

## 7. 手动扫描命令

`audit.py` 之外，想快速人工过一遍时用：

```bash
grep -nE "(在 Claude Code|Claude Code skill|Claude Code 用户|Cursor only|Codex 中|^\[!\[Claude Code|~/\.claude/skills/[a-z]|/plugin install\b)" SKILL.md README.md 2>/dev/null
```

**输出非空不等于红灯**——必须**逐行读上下文**再定性（见 §5 判别表）。
禁止机械按命中行数判定。
