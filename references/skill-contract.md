# Skill 契约与诊断码（canonical source）

> `SKILL.md` §「双轨评估」引用本文件。**36 条诊断码的判据、级别、维度归属，只有这一份定义。**
> 代码里的 `CATALOG`（`scripts/audit.py`）是它的镜像，`tests/test_selfcheck.py` 断言两者不漂移。

---

## 1. 为什么要有「契约」

一份 SKILL.md 是**给 agent 读的程序**，不是散文。程序有契约：入口、流程、分支、出口、边界。
散文没有，所以散文只能靠 LLM 打分，而 LLM 打分给的是抽样不是测量——同一份未改的文字换个
judge 能摆 ±8 分。

契约的价值在于**把「可判定的部分」从判断里摘出来**：

| | 可判定（契约） | 不可判定（判断） |
|---|---|---|
| 例子 | frontmatter 有没有 `name`；引用的文件在不在；有没有失败分支 | 工作流读起来顺不顺；跑了之后输出质量好不好 |
| 判据 | 确定性、可复现、零噪音 | 抽样、有噪音、需要人审 |
| 归属 | `scripts/audit.py` | 独立 judge + 回归测试 |

**本 skill 的全部设计都建立在这条分界线上**：可判定的一律交给脚本，脚本判不了的一律走证据闸门。

---

## 2. 契约条款

### 2.1 入口：frontmatter

```yaml
---
name: <小写短横线，1–64 字符，与目录名一致（目录名的 `-skill` 后缀可省）>
description: |
  <做什么> + <何时用> + <触发词> + <不适用>

  适用：用户说「…」「…」。
  不适用：<什么情况下不要用这个 skill>。
license: MIT
metadata:
  version: "1.0"
  author: <作者>
---
```

**两个最容易踩的坑**：

1. **块标量缩进**。`description: |` 之后所有内容必须**保持缩进**。顶格写一行
   `不适用：…` 会让它掉出 `description`，成为 frontmatter 里一个没人读的键——
   `FM009` 报的正是这个。（本机实测：`craft-skill` 的 `description` 就掉了一行。）
2. **1024 字符上限**。`description` 是 harness 选中 skill 的唯一依据，但它有长度上限。
   塞长尾关键词既撑爆长度，又抬高误触发率。

### 2.2 流程：编号步骤

流程必须**有序**，每步写清输入与产出。表格形式的 Phase 表（`| Phase | 做什么 | 产出 |`）同样
算编号步骤——`ST003` 认 `1.` / `P0` / `Step N` / `第 N 步` / `| 0 · … |` 五种写法。

### 2.3 分支：失败模式

只写正向流程的 skill 一遇异常就卡死。失败路径必须**编码成可查表的分支**，三段式：

| 触发条件 | 一线修复 | 仍失败兜底 |
|---------|---------|-----------|
| 具体到可识别的症状 | 先做什么 | 还不行怎么办 |

只有「症状 / 解法」两列不够——缺第三列时 agent 不知道第二次失败该停手还是继续试（`FL003`）。

### 2.4 出口：输出契约

写清交付时**报告哪几项**、**什么不许声称**。最常被违反的一条：
不得把非零退出码描述成成功，不得声称做过没做的检查。

### 2.5 边界：反例黑名单

只写「应该做 X」不够，必须写「**不要做 Y**」，并给出替代做法。
破坏性命令（`rm -rf` / `git reset --hard` / `push --force`）必须在黑名单里明文列禁（`SF001`）。

---

## 3. 诊断码目录

**级别**：`error` = 客观损坏，脚本退出码 1 ｜ `warn` = 明确缺陷 ｜ `info` = 建议。
**维度**：见 [`rubric.md`](rubric.md)。**评估轨**：`machine` = 脚本定分；`hybrid` = 脚本给上界、
judge 只能下修；`judge` = 只能实测。

### 3.1 Frontmatter（dim1，machine，11 条）

| 码 | 级别 | 维度 | 判据 | 修法 |
|---|---|---|---|---|
| FM001 | error | dim1 | 文件未以独占一行的 `---` 开头，或 frontmatter 未闭合 | 补 frontmatter，见 §2.1 |
| FM002 | error | dim1 | frontmatter 缺 `name` | 补 `name: <skill 名>` |
| FM003 | error | dim1 | frontmatter 缺 `description` | 补 `description`，含做什么 + 何时用 + 触发词 |
| FM004 | error | dim1 | `name` 含非法字符或超长（只允许 `[a-z0-9-]`，1–64 字符） | 改为小写短横线命名 |
| FM005 | warn | dim1 | `name` 与 skill 目录名不一致（安装后对不上号） | 改 `name`，或去掉目录名的 `-skill` 后缀后对齐 |
| FM006 | error | dim1 | `description` 超过 1024 字符 | 压缩到 1024 字符内，砍长尾关键词 |
| FM007 | warn | dim1 | `description` 无触发词（harness 靠它选中 skill） | 补「触发词」「适用」「Use when」并列举用户真会说的话 |
| FM008 | warn | dim1 | `description` 结尾是空话尾巴 | 删尾巴，换成具体适用条件 |
| FM009 | warn | dim1 | `description` 无边界声明 | 补一行「不适用：…」 |
| FM010 | info | dim1 | frontmatter 缺 `license` | 补 `license: MIT` |
| FM011 | info | dim1 | frontmatter 缺 `metadata.version` | 补 `metadata: {version: "1.0"}` |

### 3.2 结构（dim2 / dim6 / dim7 / dim9，10 条）

| 码 | 级别 | 维度 | 判据 | 修法 |
|---|---|---|---|---|
| ST001 | warn | dim7 | 正文无 H1 标题 | 补一行 `# <skill 名> · <一句话>` |
| ST002 | warn | dim2 | 找不到流程章节，也找不到编号步骤 | 补「执行流程 / 工作流 / 快速路径」章节 |
| ST003 | warn | dim2 | 流程章节内无编号步骤 | 把流程写成有序步骤，每步写清输入与产出 |
| ST004 | error | dim6 | 正文引用的文件在 skill 目录里不存在（悬空引用） | 改路径，或补文件；删掉不存在的引用 |
| ST005 | info | dim6 | 有 `references/` 目录，但正文没有引用路由表 | 补一张「时机 → 读哪个文件」的表 |
| ST006 | warn | dim9 | 无「反例 / 禁令 / 反模式 / 不要做」章节 | 补一节黑名单 |
| ST007 | warn | dim7 | 无「输出契约 / 交付」章节 | 补一节：交付时报告哪几项 |
| ST008 | info | dim7 | 无「质量检查 / 验收清单」章节 | 补一份可勾选的验收 checklist |
| ST009 | warn | dim7 | SKILL.md 超过 600 行 | 细节下沉到 `references/` |
| ST010 | info | dim7 | 正文出现多个 H1（层级混乱） | 只保留一个 H1，其余降级为 H2 |

### 3.3 失败模式（dim3，3 条）

| 码 | 级别 | 维度 | 判据 | 修法 |
|---|---|---|---|---|
| FL001 | warn | dim3 | 全文无失败分支措辞 | 补失败模式章节，写出「如果 X 失败 → Y」 |
| FL002 | warn | dim3 | 有失败措辞但没有失败表，也没有 if-then 分支 | 把失败路径整理成表格 |
| FL003 | info | dim3 | 失败表缺少「仍失败兜底」一列 | 升级为三段式，见 §2.3 |

### 3.4 检查点（dim4，2 条）

| 码 | 级别 | 维度 | 判据 | 修法 |
|---|---|---|---|---|
| CP001 | warn | dim4 | 有「等用户确认」类措辞，但没有显性视觉标记 | 在关键决策前加 `🔴 CHECKPOINT` 或 `🛑 STOP` |
| CP002 | info | dim4 | 全文无任何显性检查点标记 | 若流程含不可逆动作，在动作前插入检查点 |

> **为什么非要视觉标记**：靠「必须征得同意」这类措辞不行。LLM 解析长文时扫描的是
> **视觉锚**——`🔴` / `🛑` / 全大写 `STOP`。实测 4 行标记撬动的分数远超重写一整段措辞。

### 3.5 具体性（dim5，3 条）

| 码 | 级别 | 维度 | 判据 | 修法 |
|---|---|---|---|---|
| SP001 | warn | dim5 | 软化措辞 ≥3 处（1–2 处降为 info） | 换成可执行的确定表述；见 [`playbook.md`](playbook.md) §P2 |
| SP002 | info | dim5 | 全文无代码块 / 命令行示例 | 给关键步骤补一条可复制的命令 |
| SP003 | info | dim5 | 全文无表格 | 把并列的判据/分支改成表格 |

软化措辞清单（正则级判据，见 `audit.py` 的 `SOFT_WORDS`）：
建议 · 可以考虑 · 根据情况 · 灵活把握 · 视情况而定 · 酌情 · 尽量 · 如有必要 · 视需要 · 或许。

**`建议` 的例外**：`行动建议` / `价值判断` 里的「建议」是名词，不算。`audit.py` 用
负向后顾排除 `行动 / 价值 / 事实 / 评估 / 具体` 前缀与 `书 / 案` 后缀。

### 3.6 Runtime 中立性（dim7，3 条）

| 码 | 级别 | 维度 | 判据 | 修法 |
|---|---|---|---|---|
| RT001 | warn | dim7 | 命中单 runtime 红灯措辞（须人工确认非假阳性） | 改写为 runtime-neutral 措辞；见 [`runtime-neutrality.md`](runtime-neutrality.md) |
| RT002 | warn | dim7 | badge 钉死单一 runtime | 换成 Agent Skills Standard / skills.sh / Multi-Runtime |
| RT003 | warn | dim7 | 安装路径只给单一 runtime 的目录 | 补三层结构，见 [`runtime-neutrality.md`](runtime-neutrality.md) |

### 3.7 安全（dim9，2 条）

| 码 | 级别 | 维度 | 判据 | 修法 |
|---|---|---|---|---|
| SF001 | warn | dim9 | 出现破坏性命令，但未在禁令 / 反例章节登记 | 在黑名单里明文列禁，或改用可回滚的替代命令 |
| SF002 | info | dim9 | 涉及网络/凭证操作，但无凭证 / 密钥 / 隐私约束 | 补一行：不得把凭证写入产物或日志 |

### 3.8 体积与一致性（dim6 / dim7，2 条）

| 码 | 级别 | 维度 | 判据 | 修法 |
|---|---|---|---|---|
| SZ001 | info | dim7 | SKILL.md 超过 32KB | 下沉细节到 `references/` |
| SZ002 | info | dim6 | README.md 存在但从未提到本 skill 的 `name` | 让 README 与 frontmatter 对齐 |

---

## 4. 抑制规则（假阳性是怎么被挡住的）

确定性检查最大的风险是假阳性——报错了，但报得不对。**假阳性比漏报更伤**：它会让人不再相信工具。
以下抑制规则都有测试覆盖。

| 规则 | 挡住的假阳性 | 实现 |
|---|---|---|
| **代码块掩码** | 示例代码里的红灯措辞、软化词 | `skillmd.mask_code_fences` |
| **行内代码掩码** | `` `建议` `` 这种「举例说明软化词」 | `skillmd.mask_inline_code`（用于 SP001） |
| **元陈述抑制** | 讲解规则、列反例、贴扫描命令的行 | `is_meta_line`（`META_MARKERS`） |
| **产物语境抑制** | 描述**产物目录结构**时出现的 `references/AXIOMS.md` | 最内层章节含 `~/.claude/skills` / `人格目录` 等标记 |
| **读取动作门槛** | 只是「提到」某个路径，没让 agent 去读 | 读取动词必须紧贴反引号，或在参考文件路由章节内 |
| **占位符跳过** | `references/0X-xxx.md` 这类模板占位 | `PLACEHOLDER_RE` |
| **runtime 豁免** | `xxx-codex` 这类明确绑定单 runtime 的 skill | name 以 `-codex` / `-claude` 等结尾则跳过 RT 扫描 |
| **多 runtime 表格** | 已经列了 ≥2 个 runtime 的安装路径表 | `RUNTIME_DIR_RE` 命中 ≥2 个不同 runtime |

> **抑制必须留痕**：被抑制的 RT001 会出现在 JSON 的 `suppressed` 数组里，带
> `suppress_reason: meta_statement`。**抑制不等于删除**——人工复核时看得见。

---

## 5. 用法

```bash
python3 scripts/audit.py <skill 目录>                 # 人类可读
python3 scripts/audit.py <skill 目录> --json          # 机读
python3 scripts/audit.py <skill 目录> --out snap.json # 存快照，供 --diff 用
python3 scripts/audit.py <skill 目录> --strict        # warn 也算失败
python3 scripts/audit.py --diff before.json after.json  # 闸门 1：判定是否退化
python3 scripts/audit.py --list-codes                 # 打印本文件的诊断码表
```

退出码：`0` 无 error（`--diff` 时 = 未退化）｜ `1` 有 error（或判定退化）｜ `2` 用法 / IO 错误。
