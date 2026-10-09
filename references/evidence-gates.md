# 证据闸门协议（canonical source）

> `SKILL.md` §「证据闸门」引用本文件。**keep / revert 的判据、盲评协议、回归测试协议、
> 触发测试协议、代价表只有这一份。**

---

## 1. 为什么要闸门

改进 skill 有两个方向的错误，代价不对称：

| 错误 | 后果 |
|---|---|
| **假 keep**（退步却保留了） | 棘轮倒转，质量随时间**累积劣化**，且没人发现 |
| **假 revert**（真改进却回滚了） | 丢一次增益，下一轮还能再试 |

两者都坏，但**假 keep 更坏**：它不可见、会累积。所以闸门的设计目标是
**宁可多 revert 一次，也不放一个退步进来**——但也不能因为 judge 噪音把真实增益误杀。

解法是**两道闸门串联，顺序不可颠倒**：

```
改完
 ├─ 闸门 1（确定性）：audit.py --diff 有新增 error/warn 吗？
 │    有 → revert。到此为止，不需要 LLM。
 │    没有 ↓
 └─ 闸门 2（判断）：paired 奇数 N 多数决，判 better / worse / tie
      多数 worse → revert
      否则       → keep
```

**闸门 1 先跑**的意义：**任何 LLM 都判不了的事，不要让 LLM 判**。结构退化是确定性的，
一次 `--diff` 就定案，零成本、零噪音、零争议。

---

## 2. 闸门 1 · 确定性闸门（硬）

```bash
# 改之前
python3 scripts/audit.py <skill 目录> --out before.json
# 改之后
python3 scripts/audit.py <skill 目录> --out after.json
# 判定
python3 scripts/audit.py --diff before.json after.json
```

| 退出码 | 含义 | 动作 |
|---|---|---|
| `0` | `gate=pass`：没有新增 error/warn | 进入闸门 2 |
| `1` | `gate=fail`：新增了 error 或 warn | **直接 revert**，记 `status=revert`，note 写明新增的码 |

**比较口径**：按 `(文件, 诊断码)` 做多重集比较，**不把证据文本纳入键**。
同一诊断的措辞微调不该被算成「一消一增」的假退化。

**新增 `info` 不算退化**（`gate=pass`）——info 是建议不是缺陷。
但如果新增 info 的同时**没有消除任何**诊断，说明这一轮编辑没有产生净收益，
按 §5 的触顶规则处理。

---

## 3. 闸门 2 · paired 多数决（软）

### 3.1 协议

spawn **奇数 N 个独立 judge**（默认 3；出现 close call 时升到 5）。
**每个 judge 在同一次调用里同时读改前版与改后版**，然后回答：

```json
{"verdict": "better | worse | tie", "margin": "clear | slight", "reason": "一句话，必须指到具体位置"}
```

- **改前版**：`git show HEAD:<path>/SKILL.md`（上一个 kept 的提交）
- **改后版**：工作区当前的 `SKILL.md`
- **评分准则**：把 [`rubric.md`](rubric.md) 的九维表当**比较准则**交给 judge，
  不是让它各打一个绝对分

### 3.2 三条硬约束

1. **同一次调用内读两版**。分成两次调用会让 judge 用两把不同的尺
   （within-judge cancellation 就没了，等于退回绝对分）。
2. **judge 不复用**。下一轮换全新 judge，避免上一轮的结论锚定这一轮。
3. **judge 与改进者分离**。改 skill 的 agent 不得参与评判。
   SkillLens 实测 LLM 自评准确率 46.4%——**低于抛硬币**。

### 3.3 判据

```
better = 投 better 的 judge 数
worse  = 投 worse 的 judge 数

if worse > better:  status = revert
else:               status = keep      # 含 better == worse（tie 也算 keep）
```

**为什么 tie 算 keep**：闸门 1 已经保证结构没退化。在结构不退化的前提下，
judge 判 tie 意味着「看不出差别」——此时保留改动是安全的，回滚反而白干。
（若你更保守，可把 tie 判 revert；但要在账本里保持口径一致，不能一轮一个样。）

### 3.4 触顶规则（见好就收）

**连续 2 轮**满足「多数 judge 判 `margin=slight` 或 `tie`」→ **break**，进入 Phase 3。

触顶后继续硬改，产出的是「加废话让 judge 觉得更详细」，不是质量。
**+0.15 是停手信号，不是继续信号。**

---

## 4. 回归测试协议（dim8 的唯一来源）

dim8 权重 23，且**没有它就没有效果证据**。协议：

### 4.1 设计测试 prompt

每个 skill 在 `test-prompts.json` 里放 2–3 条：

```json
[
  {"id": 1, "prompt": "用户真会说的话", "expected": "期望输出的简短描述"},
  {"id": 2, "prompt": "稍复杂或有歧义的场景", "expected": "..."}
]
```

**必须是最常见的使用场景，不是边缘 case**——边缘 case 测不出 skill 的日常价值。
设计完**展示给用户确认**再开跑。

### 4.2 跑对照

对每条 prompt，spawn 两个**独立** agent：

| 组 | 拿到什么 |
|---|---|
| `with_skill` | SKILL.md 全文 + prompt |
| `baseline` | 只有 prompt |

两个 agent **互不可见**，都不知道对方存在。

### 4.3 盲评

spawn 独立 judge，**只给两份输出（打乱顺序、隐去来源）**，让它回答：

1. 哪一份更好地完成了用户意图？（paired，不是绝对分）
2. 带 skill 的那份有没有引入**负面影响**（过度冗余、跑偏、格式奇怪）？

第 2 问对应 SkillLens 的 negative transfer 发现：**25% 的案例加 skill 比不加还差**。

### 4.4 无 full_test 怎么办

**dim8 记 `unverified`，不参与总分**，报告里显式列出未测维度。
**不允许**用干跑推演给 dim8 打分——那等于凭空编造 23% 的分数。

> 与 darwin 的差异：darwin 允许 `dry_run` 打分并设 30% 比例上限。
> 本 skill 更严格：**dry_run 只记不评**。理由：一旦允许用推演填分，
> 分数就再也分不清哪部分是测出来的、哪部分是编的。

---

## 5. 触发测试协议

**skill 的全部价值依赖「harness 会选中它」，而选中完全取决于 `description`。**

而九维里**没有任何一维测这件事**——dim1 测的是 description 的格式是否合格，
不是它**在真实竞争里会不会被选中**。所以触发测试单独做：

1. spawn 1 个 agent，**只给它所有 skill 的 `name` + `description`**，不给正文
2. 让它对 5 句**该命中的话术** + 5 句**干扰话术**逐句判断会选中谁

| 结果 | 修法 |
|---|---|
| 漏命中 | 补 `description` 的**独有锚点**（专有名词 / 用户真会说的原话） |
| 误触发 | 删掉 `description` 里的通用词 |
| 与别的 skill 抢同一句 | 保留长词，删短词 |

**不要靠堆长尾关键词**——它既撑爆 1024 字符上限，又抬高误触发率。

---

## 6. 代价表

**开跑前把代价告诉用户**，不要默默 spawn 一堆 agent。

| 阶段 | spawn | 说明 |
|---|---|---|
| P0 定范围 / P1 建基线 | 0 | 主 agent 跑 `audit.py`，纯脚本 |
| P2 设计测试 prompt | 0 | 主 agent 写 + 用户确认 |
| P3 诊断排序 | 0 | 纯脚本 |
| P4 单轮改进 | 0 | 主 agent 编辑 |
| **P5 闸门 1** | **0** | `audit.py --diff`，确定性 |
| **P5 闸门 2** | **3**（close call 升 5） | paired judge，奇数 N |
| **P6 回归测试** | **2 × prompt 数 + 1** | 每条 prompt 两组 agent + 1 个盲评 judge |
| **P6 触发测试** | **1** | 只给 name + description |
| **单轮合计** | **≈ 4 + 2×prompt 数** | 3 条 prompt ≈ 10 个 agent |
| **单 skill 全流程（3 轮）** | **≈ 30** | 宁可报高，不要报低 |

**轻量模式（lite）**：跳过回归测试，dim8 记 `unverified`，单轮 ≈ 4 个 agent。
**lite 交付时必须标注 `eval_mode=none`，且不得声称「效果已验证」。**

---

## 7. 账本纪律

每次判定后追加一条记录（`scripts/ledger.py`）：

```bash
python3 scripts/ledger.py record \
  --file <skill 目录>/IMPROVEMENTS.jsonl \
  --skill craft --round 1 --status keep --dimension dim3 \
  --eval-mode paired --votes 3-0 \
  --note "补三段式失败表，FL002→0" \
  --before before.md --after after.md \
  --audit-before before.json --audit-after after.json
```

脚本强制的三条纪律：

1. **无 `note` 不写**——没有一句裁断理由的记录等于意见
2. **keep 必须有证据**——要么 `--votes`，要么 `--audit-after`
3. **只追加，不修改**——要修正历史就再写一条 `status=amend`

`ledger.py verify` 会校验字段完整性、时间戳单调、无空 note。
