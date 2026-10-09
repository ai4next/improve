---
name: improve
version: 1.0.0
description: |
  改进优化 skill 的 skill：给一份 SKILL.md 做确定性体检，按证据改进，用两道闸门决定保留还是回滚。

  做法是**双轨评估**：可判定的部分（frontmatter、悬空引用、失败分支、检查点、软化措辞、runtime 中立性）
  交给零依赖脚本出可复现的诊断；判不了的部分（实测表现、整体架构）交给独立 judge 与回归测试。
  keep/revert 走**两道闸门**——结构退化直接回滚，其余用 paired 奇数多数决。

  触发词：「优化 skill」「改进 skill」「skill 质量」「skill 体检」「skill 打分」「skill review」
  「帮我改改 skill」「这个 skill 怎么样」「improve skill」「optimize skill」「audit skill」。

  适用：手上有一份 SKILL.md（自己的或别人的）想让它更好；给一批 skill 做质量体检；
  想知道某个 skill 为什么跑不好；想给 skill 建立可追溯的改进账本。

  不适用：从零造一个新 skill（那是铸造，不是改进）；纯文档润色且不涉及 skill 契约；
  没有 SKILL.md 的普通 markdown 文档。
license: MIT
metadata:
  version: "1.0"
  author: ai4next
---

# improve · 让 skill 只朝一个方向变

> 可判定的事交给脚本，判不了的事交给证据。**不用绝对分数当棘轮。**

**本文件是路由器，不是百科。** 判据只在 canonical source 定义一次，这里给指针；
读到与 canonical source 冲突的说法，**以 canonical source 为准**。

---

## §一 定位

给一份 SKILL.md 做**确定性体检**，按证据改进，用两道闸门决定 keep 还是 revert。

```
SKILL.md  →  审计（脚本，零噪音）  →  诊断排序  →  单维度改进  →  闸门 1 结构  →  闸门 2 paired  →  keep / revert
                                        ↑                                              ↑
                                   可判定的部分                                  判不了的部分
```

与「让 LLM 打分爬山」的区别只有一条，但它是根上的：**绝对分数不是测量，是抽样**。
同一份**未改**的文字换个 judge 评，总分能摆动 ±8；一次保守编辑的真实增益通常只有 +3~+8。
拿两个 judge 的绝对分相减，差值大半是**换尺**，不是质量变化。

所以本 skill 把 77% 的权重交给确定性判据，只留 23% 给 judge，并且**judge 只做比较、不做打分**。

---

## §二 四条铁律

| # | 铁律 | 它防的是什么 |
|---|------|-------------|
| 1 | **能算的不要问** | 结构退化是确定性的——一次 `--diff` 就定案，交给 LLM 判等于白送噪音 |
| 2 | **没有证据不 keep** | 无证据的 keep 会让棘轮倒转，质量随时间**累积劣化**且不可见 |
| 3 | **改的人不评** | 自评接近随机（实测 LLM 自评准确率 46.4%，低于抛硬币） |
| 4 | **触顶就停** | 连续 2 轮判 `margin=slight` 或 `tie` → 收工。硬凑轮次产出的是废话不是质量 |

**推论**：一轮只改一个维度（多变量同变则无法归因）· 只改「怎么写」不改「做什么」·
回滚一律用 `git revert` 建反向提交（保留可追溯链，不用破坏性重置）·
优化后体积超过原始 150% 时先精简再提交。

---

## §三 产物与数据契约

一次改进会话产生**三个**产物，都在**被改进的 skill 目录**下，不污染本 skill 目录。

| 产物 | 位置 | 谁写 | 用途 |
|------|------|------|------|
| **审计快照** | `.improve/before.json` · `.improve/after.json` | `scripts/audit.py` | 闸门 1 的输入；可复现、可归档 |
| **改进账本** | `IMPROVEMENTS.jsonl` | `scripts/ledger.py` | 追加式历史：每轮的判据、票数、哈希 |
| **测试 prompt** | `test-prompts.json` | 主 agent + 用户确认 | dim8 回归测试的题面 |

**账本只追加，不修改。** 要修正历史就再写一条 `status=amend`，原记录留着。
`ledger.py verify` 校验字段完整性、时间戳单调、无空 note。

**哈希纪律**：每轮 keep/revert 都把改前/改后的 `SKILL.md` 算 sha256 记进账本——
事后能验证「这条记录说的是哪一版」。

**git 前提**：在 git 仓库里跑，并先让工作区干净。不在 git 仓库时先问用户：
`git init`，还是退化成 `.bak.YYYYMMDD-HHMM` 文件备份（后者则用复制回滚代替 `git revert`）。

---

## §四 参考文件路由

**按需读取，不要预先全读。**

| 触发时机 | 读取（canonical source） |
|---------|------------------------|
| **总是**（P1 之前） | [`references/skill-contract.md`](references/skill-contract.md) —— 36 条诊断码的判据、级别、维度归属、抑制规则 |
| 评分、加权短板、judge 只能下修的口径 | [`references/rubric.md`](references/rubric.md) —— 九维权重、评估轨、评分公式、实证基础 |
| **总是**（P4 之前） | [`references/evidence-gates.md`](references/evidence-gates.md) —— 两道闸门、paired 协议、回归测试、触发测试、代价表 |
| 具体怎么改某个诊断码 | [`references/playbook.md`](references/playbook.md) —— 诊断码→修法、优先级、高杠杆操作 |
| 有 `RT*` 命中，或要判假阳性 | [`references/runtime-neutrality.md`](references/runtime-neutrality.md) —— 红灯/绿灯对照、假阳性判别表 |

**工具**（全部零依赖，Python 3 标准库）：

```bash
python3 scripts/audit.py <skill 目录> --out .improve/before.json   # 审计 + 存快照
python3 scripts/audit.py --diff .improve/before.json .improve/after.json   # 闸门 1
python3 scripts/ledger.py record --file <skill 目录>/IMPROVEMENTS.jsonl ...  # 记一笔
python3 scripts/ledger.py verify --file <skill 目录>/IMPROVEMENTS.jsonl      # 校验账本
```

---

## §五 执行流程

```
P0 定范围 → P1 建基线 → P2 设计测试 prompt → P3 诊断排序
          → P4 单维度改进 → P5 🔴 两道闸门 → P6 回归 + 触发测试 → P7 汇总交付
```

### 代价表（**先看这个，再决定跑到哪一步**）

**开跑前把代价告诉用户**，不要默默 spawn 一堆 agent。

| 阶段 | spawn | 说明 |
|------|-------|------|
| P0–P3 定范围 / 基线 / 出题 / 排序 | **0** | 主 agent 跑脚本 + 写 prompt，纯确定性 |
| P4 单维度改进 | **0** | 主 agent 编辑 |
| **P5 闸门 1** | **0** | `audit.py --diff`，确定性，零成本 |
| **P5 闸门 2** | **3**（close call 升 5） | paired judge，奇数 N 多数决 |
| **P6 回归测试** | **2 × prompt 数 + 1** | 每条 prompt 两组 agent + 1 个盲评 judge |
| **P6 触发测试** | **1** | 只给所有 skill 的 `name` + `description` |
| **单轮合计** | **≈ 4 + 2 × prompt 数** | 3 条 prompt ≈ 10 个 agent |
| **单 skill 全流程（3 轮）** | **≈ 30** | 宁可报高，不要报低 |

**轻量模式（lite）**：跳过回归测试，dim8 记 `unverified`，单轮 ≈ 4 个 agent。
**lite 交付时必须标 `eval_mode=none`，且不得声称「效果已验证」。**

### P0 定范围

| 用户输入 | 路径 |
|---------|------|
| 指定了某个 skill | 单 skill 全流程 |
| 「优化所有 skill」/ 一批 | 先全量跑 P1 基线，按结构分升序，**从最低的 5 个开始** |
| 「只体检不改」 | 只跑 P0–P3，出报告，不进循环 |
| 「看看改进历史」 | 读 `IMPROVEMENTS.jsonl` 展示 |
| 目标目录没有 `SKILL.md` | 终止该目标，如实说明，不猜 |

### P1 建基线

```bash
python3 scripts/audit.py <skill 目录> --json --out <skill 目录>/.improve/before.json
```

按 [`rubric.md`](references/rubric.md) §3 算结构分（覆盖权重 77/100，dim8 未测）。
**结构分只用于排序，不用于 keep/revert。**

### P2 设计测试 prompt

读 SKILL.md 理解它做什么，写 2–3 条到 `test-prompts.json`：
覆盖**最常见的使用场景**（happy path）+ 一个稍复杂或有歧义的场景。
**设计完展示给用户确认再开跑**——题面错了，dim8 的方向就全错。

文件已存在时问用户「复用 / 重写 / 追加」三选一，不静默覆盖。

### P3 诊断排序

```
weighted_gap(dim) = weight(dim) × (10 − score(dim)) / 10
```

选 `weighted_gap` 最大的维度动手。**不要用「原始分最低」**——低权重维度会制造进步幻觉。
差距 ≤ 1.0 时按原始分升序。**dim2 / dim3 / dim4 是相关簇**，修其一时同时看另两个的短板。

### P4 单维度改进

按 [`playbook.md`](references/playbook.md) 的优先级与修法，**一轮只改一个维度**。
改完 `git commit`，message 写清改了哪个维度、消了哪条诊断。

### P5 🔴 CHECKPOINT · 两道闸门

**这是全流程最重要的检查点。** 先跑闸门 1（脚本），通过了才 spawn judge 跑闸门 2。
判据与协议见 [`evidence-gates.md`](references/evidence-gates.md) §2–§3。

**结构退化 → 直接 revert，不 spawn 任何 agent。**
**judge 判多数 worse → revert**；否则 keep。**账本必须记一笔**，keep 没证据会被 `ledger.py` 拒绝。

### P6 回归测试 + 触发测试

回归测试协议见 [`evidence-gates.md`](references/evidence-gates.md) §4：
每条 prompt 跑 `with_skill` 与 `baseline` 两组**互不可见**的 agent，再交给独立 judge **盲评**。
问两件事：哪份更好（paired）+ 带 skill 那份有没有引入**负面影响**。

触发测试见同文件 §5：**只给所有 skill 的 `name` + `description`**，让它判 5 句该命中的话术 +
5 句干扰——九维里**没有任何一维测「会不会被选中」**。

### P7 汇总交付

展示：结构分 before → after（分开写覆盖权重）· 消除/新增的诊断码 · 每轮票数 ·
实测表现（或 `unverified`）· 账本路径。**🔴 CHECKPOINT · 等用户确认后再收工。**

---

## §六 双轨评估

**可判定的部分（53 分）**：`scripts/audit.py` 出诊断，按
`penalty = error 4.0 / warn 1.5 / info 0.5`、`score = max(1.0, 10 − penalty)` 算维度分。

**判不了的部分（24 分，hybrid）**：脚本给**上界**，judge **只能下修**且必须带行号证据。
这一条把 LLM 的乐观偏差结构性掐掉了。

**只能实测的部分（23 分，dim8）**：独立 judge + 回归测试。**没有 full_test 就记 `unverified`**，
不参与总分，报告里显式列出——**不允许用干跑推演给 dim8 打分**，那等于编造 23% 的分数。

完整权重、评估轨、评分公式见 [`rubric.md`](references/rubric.md)。

---

## §七 证据闸门

```
改完
 ├─ 闸门 1（确定性，硬）：audit.py --diff 有新增 error/warn 吗？
 │     有 → revert。到此为止，不需要 LLM。
 │     没有 ↓
 └─ 闸门 2（判断，软）：paired 奇数 N 多数决
       多数 worse → revert
       否则       → keep
```

**闸门 1 必须排在前面**：任何 LLM 都判不了的事，不要让 LLM 判。

**闸门 2 的三条硬约束**（缺一条就退化成绝对分）：

1. **同一次调用内读改前 + 改后两版**——分成两次调用会让 judge 用两把不同的尺
2. **judge 不复用**——下一轮换全新 judge，避免锚定
3. **改的人不评**——spawn 出去的 judge 看不到本会话

比较口径按 `(文件, 诊断码)` 做多重集，**不把证据文本纳入键**——
同一诊断的措辞微调不该被算成「一消一增」的假退化。

完整协议、回归测试、触发测试、代价表见 [`evidence-gates.md`](references/evidence-gates.md)。

---

## §八 改进者禁令（反例黑名单）

**只列不能由四条铁律直接推导出来的条目**——它们依赖实测经验与工具行为。

| # | 不要做 | 为什么 | 替代做法 |
|---|--------|--------|---------|
| 1 | **拿绝对分数 delta 当棘轮** | 绝对分是抽样不是测量，跨 judge ±8 噪音淹没真实增益 | 闸门 1 + paired 多数决；绝对分只做 triage |
| 2 | **用 `git reset --hard` 回滚** | 会丢工作区未提交改动，历史断裂 | 用 `git revert` 建反向提交 |
| 3 | **同 context 自评自改** | 乐观偏差；自评准确率低于抛硬币 | spawn 独立 judge，改的人不评 |
| 4 | **无证据的 keep** | 假 keep 不可见且会累积，比假 revert 更坏 | `ledger.py` 强制 keep 带票数或 audit 快照 |
| 5 | **用干跑推演给 dim8 打分** | 一旦允许推演填分，就分不清哪部分测过 | dim8 记 `unverified`，不参与总分 |
| 6 | **一轮改多个维度** | 多变量同变，分数升降无法归因 | 一轮一个维度，相关簇一起看 |
| 7 | **跳过测试 prompt 直接评分** | dim8 权重 23，没有题面等于编造 | P2 强制设计 2–3 条并让用户确认 |
| 8 | **静默跳过异常** | 破坏棘轮完整性，事后无法追溯 | 异常先告知用户，再按 §九 规则处理 |
| 9 | **为凑分增冗余** | 触顶后硬改产出的是废话不是质量 | 连续 2 轮 `slight`/`tie` → 停手 |
| 10 | **机械按 grep 命中数判 runtime 红灯** | 讲解规则的 skill 会永远判自己红灯，陷入自审死循环 | 逐行读上下文，按假阳性判别表定性 |
| 11 | **只改「做什么」** | 那是在改用途，不是改进 | 只优化「怎么写」和「怎么执行」 |
| 12 | **交付时丢掉未测声明** | 声称没做过的事 = 编造证据 | 输出契约强制写清测过什么、没测过什么 |

---

## §九 硬故障表

**只列四条铁律与禁令都没覆盖的失败**——其余失败模式见末行。

| 触发条件 | 一线修复 | 仍失败兜底 |
|---------|---------|-----------|
| 不在 git 仓库 | 问用户：`git init` 还是文件备份 | 用户选备份 → 用 `.bak.YYYYMMDD-HHMM` 复制代替 revert |
| `git revert` 冲突或工作区脏 | 先 `git stash` 再重试 | 从上一条 commit 读出文件覆盖当前版，手动恢复 |
| 账本缺失或列数不符 | 缺失 → 建新文件写表头；损坏 → 备份为 `.bak` 后重建 | 备份保留原文件，告知用户哪一行坏了 |
| 连续 2 轮闸门 1 都 fail | 停下来，把两轮新增的诊断码摊给用户看 | 判定为「方向错了」，回 P3 重选维度 |
| 触顶（连续 2 轮 `slight`/`tie`） | break 进 P7 收工，**见好就收** | 用户要求继续 → 转一次探索性重写（征得同意后） |
| 优化后体积 > 原始 × 1.5 | 拒绝提交，回 P4 精简（删冗余、下沉 `references/`） | 仍超限 → 拆成两个 skill 或放弃该轮改动 |
| `SKILL.md` 找不到 | 该目标终止，账本记 `status=error` | 继续下一个目标，不中断整批 |
| 子 agent 不可用 | 跳过 P5 闸门 2 / P6，**只保留闸门 1** | 报告标 `eval_mode=none`，明说「结构已验、效果未验」 |

**原则**：异常先告知用户，再按规则处理；**绝不静默跳过或静默失败**。

---

## §十 输出契约

交付时报告：

1. **结构分**：`before → after`，**并写明覆盖权重**（如 `77/100`）
2. **诊断变化**：消除了哪些码、新增了哪些码（逐条列）
3. **每轮票数**：`3-0 better` 这类 paired 结果
4. **实测表现**：`full_test` 通过 / `unverified`（未测）
5. **触发测试**：命中 / 未跑
6. **账本路径**与记录条数

**不得**把非零退出码描述成成功；**不得**把 `lite` 或 `unverified` 说成「效果已验证」；
**不得**声称做过没做的检查；**不得**把结构分说成「质量提升了 N 分」——它是代理指标，不是质量真值。

---

## §十一 质量检查

- [ ] `python3 scripts/audit.py <目标>` 报 **0 error**
- [ ] 每轮 keep 都有证据（票数或 audit 快照），账本 `verify` 通过
- [ ] 每轮只改了一个维度，`git commit` message 写清了维度与诊断码
- [ ] dim8 要么有 `full_test`，要么在报告里明确标 `unverified`
- [ ] 交付报告里结构分与实测表现**分开写**，并写明覆盖权重
- [ ] 所有改动在 git 上可追溯，回滚用的是 `git revert`
- [ ] 本 skill 自身通过自审：`python3 -m unittest discover -s tests`

---

## §十二 最后

改进 skill 只有一件事要做对：**分清哪些是算得出来的，哪些是判出来的**。

算得出来的（悬空引用、缺字段、没有失败分支、软化措辞）**不该问 LLM**——问了就是白送噪音。
判得出来的（跑起来效果好不好）**不该自己判**——自己判接近抛硬币。

把这两件事分开，棘轮才真的只朝一个方向转。
