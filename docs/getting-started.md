# code-harness 快速入门

本指南面向使用 code-harness 的个人开发者，覆盖获取安装、为目标仓库配置策略、日常运行、
存量告警处置，以及「每个代码任务结束后运行门禁」这一持续门禁场景。

code-harness 是只读的解析型工程策略门禁：任何运行模式都不修改、暂存、还原、删除或重写源
文件，也不改动 Git 配置。命令、策略示例和契约原文保持英文原文，说明文字使用中文。

## Installation

### 前置条件

- Python 3.12 或更高版本。
- 建议使用 `uv` 管理独立的工具环境；`uv` 自身的获取方式与仓库开发命令见
  [README 的 Run 节](../README.md#run)。

### 获取源码

获取 code-harness 源码检出（clone 仓库，或解压拿到的源码包）。下文统一用
`/path/to/code-harness` 指代该检出目录。检出中同时包含工具源码、`examples/` 下的样例策略，
以及 `.agents/skills/code-harness/` skill。

### 本地安装

从该检出目录本地安装命令行：

```sh
uv tool install /path/to/code-harness
```

不使用 uv 时，pip 等价安装：

```sh
python -m pip install /path/to/code-harness
```

安装把 `code-harness` 放到用户级可执行目录（例如 `~/.local/bin`），请确认该目录在 `PATH`
中。若已存在同名的 uv 工具安装，需要替换时给 `uv tool install` 加 `--force`。

### 验证

```sh
code-harness --help
code-harness --root /path/to/project --all
```

第一条确认命令可用，并列出实际支持的选项：`--root`（默认 `.`）、`--config`
（默认 `.codeharness/code-harness.json`）、`--format`（`text` 或 `json`），以及必选互斥的
`--all` / `--staged` / `--base`。第二条对目标仓库执行一次全量审计；若目标仓库还没有按
[Configuration](#configuration) 建立策略，该命令以 exit 2 报告找不到策略文件，这属于预期
行为，先完成配置再回来验证。

### 容器方式

需要以容器方式运行（只读挂载目标仓库）时，见
[README 的 Integration 节](../README.md#integration)。

### skill 获取

agent 使用的 skill 与工具来自同一份源码检出：把检出中的 `.agents/skills/code-harness/`
复制到消费项目的 skill 位置即可，接入路径见 [Agent integration](#agent-integration)。

## Configuration

### 建立仓库策略

每个目标仓库自己持有并提交一份 `.codeharness/code-harness.json`（策略路径相对 `--root`
解析，Git 模式同样如此）。工具没有生成或初始化策略的命令，文件由使用者手写并提交：
工具自身定义的选项只有 `--all`、`--staged`、`--base`、`--root`、`--config` 与 `--format`，
另有自动提供的 `-h, --help` 帮助选项。

起步方式有两种。可以把 [样例策略](../examples/.codeharness/code-harness.json) 复制到目标仓库的
`.codeharness/code-harness.json`，再按该仓库的结构调整；也可以直接手写一份最小可用策略，
其中 `checkers` 为空对象（或省略该键）时，全部 checker 保持默认启用：

```json
{"version": 2, "include": ["src/*"], "exclude": [], "checkers": {}}
```

策略里可以按需补上的内容：

- `include` / `exclude`：决定哪些文件参与全部检查；大小写敏感、`*` 可跨 `/`、路径相对
  仓库根。
- `architecture.owner` 的 `owners`：为每个被选中的文件声明唯一责任归属。
- `architecture.import` 的 `boundaries`：声明禁止的依赖方向。
- `function_size`：函数行数、语句数、复杂度、嵌套与参数上限。

从最小策略起步时，按下面的顺序逐步建立，每一步都先拿到读数再决定下一步：

1. 用 `include` / `exclude` 圈定参与审计的文件范围；
2. 首次执行 `code-harness --all` 取得基线读数——存量仓库通常返回 exit 1，属预期，见
   [存量仓库的首次全量审计](#存量仓库的首次全量审计)；若范围内没有任何受支持源文件，则按配置
   错误返回 exit 2，需要先修正 `include`；
3. 为被选中的文件补 `architecture.owner` 的 `owners`；
4. 声明 `architecture.import` 的 `boundaries`；
5. 按仓库实际情况调整 `function_size` 阈值，或补 `type.broad` 的 `encoding` 声明。

上面每一步都可能改动策略：阈值、排除项与 owner/boundary 的调整按下一节的纪律另行全量审计与
复审，不用来消除既有告警。

### 变更策略的纪律

策略变更（调整阈值、增加排除、改动 owner/boundary）是架构决策，不是消除告警的手段。
bootstrap 首版和每次修订都需要另行执行全量审计 `--all` 并复审。`--staged` 一旦发现 index
中的策略变更就直接以 exit 2 拒绝，直到全量审计通过并提交。

全部选项、版本 2 的结构、各语言覆盖范围以及实现限制见
[Checker configuration](checker-configuration.md)。

## Running

三种模式必须显式给出其中之一，`--all` / `--staged` / `--base <commit>` 互斥：

- `--all`：审计所有被策略选中的工作树文件，**包括**被 Git 忽略的文件；会暴露全部存量债务。
- `--base <commit>`：比较给定 commit 与工作树，**包含**未跟踪的新文件（新文件按全量审计）。
- `--staged`：只读 index 中的 blob 与 index 里的策略，看不到未暂存的内容。

规范命令：

```sh
code-harness --all
code-harness --staged
code-harness --base <commit>
code-harness --root /path/to/project --all
code-harness --all --format json
```

`--root` 默认当前目录（Git 模式必须是仓库根），`--config` 默认
`.codeharness/code-harness.json`；两者可以组合成
`code-harness --root /path/to/project --config .codeharness/code-harness.json --all`。

退出码：

| 退出码 | 含义 |
|---|---|
| `0` | 无 error 级 finding（warning 不影响） |
| `1` | 存在 error 级 finding |
| `2` | 配置/编码/文件系统/Git 失败（含 staged 下策略变更，直到另行 `--all` 全量审计通过并提交） |

变更模式（`--base` / `--staged`）完整解析快照，但报告的是**受影响定义与模块语句**：函数内
的编辑扩展到整个函数（含装饰器与签名），类头编辑选中整个类，模块语句编辑选中该语句；纯删除
保留附近的行锚；未跟踪文件做全量审计。归属与放置约束仍作用于每个被改动的文件。报告用
`scope` 区分 `full_files` 与 `affected_definitions_and_statements`。

其余语义：空的全量审计按配置错误处理（exit 2）；空的变更审计报告 0 个文件；语法错误只在
stderr 给出 warning，不改变退出码，其余检查在恢复的语法树上继续，因此结果可能不准确；
warning 不影响 exit 0。

`--format json` 输出当前报告结构：`scope`、`findings`（每项带 `severity`）、`usage_files`、
`disabled_checkers`，以及模式与文件计数。该结构按当前实现交付，未承诺作为对外稳定 ABI，
升级时请以实际输出为准。

所有模式全程只读：不修复、不 stash、不 stage、不 restore、不删除、不重写源文件。

## Triage

### 三条处置路径

1. **修复优先**：告警是策略违规的证据，默认动作是改代码。
2. **逐行抑制（全部受支持语言）**：Python、Go、Java 与 JavaScript 家族都允许对单个精确
   rule id 使用下一行抑制注释，注释使用该语言自己的行注释标记——Python 为 `#`，Go、Java 与
   JavaScript 家族为 `//`；但该机制仅可用于**事先获得明确（人工）批准的例外**——批准先于且
   独立于理由，理由只是记录该批准，并非安全性证明，代码用途变化时须重新审议该例外。块注释
   形态、通配符、列表、`type.suppression` 自身与缺少理由都报 `type.suppression` 错误，滥用
   抑制本身就是错误。语法与校验规则见 [逐行诊断抑制](comment-suppressions.md)。
3. **策略修订**：阈值、排除项或 owner 调整属于策略变更，必须另行 `--all` 全量审计与复审，
   不得用放宽策略制造绿色。

### 债务语义

`--all` 暴露全部存量债务，`--base` 只报告受影响定义与模块语句，两种读数不能互相替代。

- `0`：本次范围内没有 error 级 finding，warning 可以存在。
- `1`：本次范围内存在 error 级 finding，需要逐项处置。
- `2`：门禁给不出结论（配置、编码、文件系统或 Git 失败），先修好输入，再谈是否通过。

### 存量仓库的首次全量审计

已有债务的仓库 bootstrap 首版策略后，第一次 `--all` 通常返回 exit 1，这是预期的读数，
不是门禁故障：

1. 逐项阅读 finding，先修真实违规。
2. 对确属历史债务、或与仓库现状不符的规则，有意识地调整策略（阈值、排除、owner），
   然后重新执行 `--all` 并复审。
3. 记录哪些告警被修复、哪些通过策略变更被接受，以及复审结论。

## Per-task gating

这是面向 agent 的持续门禁场景：每个代码任务结束、在报告任务完成之前运行一次门禁，并如实
报告模式、退出码和 findings。人工开发时按同样口径执行。

| 情形 | 命令 | 说明 |
|---|---|---|
| 任务改动未提交（工作树，含 staged/unstaged/untracked） | `code-harness --base HEAD` | 对比 HEAD 与工作树、含 untracked（新文件全量审计） |
| 任务已产生 commit | `code-harness --base <任务起始 commit>`（任务首个 commit 的父） | 干净树上 `--base HEAD` = 0 文件、exit 0 的**静默假通过**，必须避免 |
| 起始 commit 不可知 | `code-harness --all`，并明示“本次为全量审计，可能含存量债务” | 宁可过报不可漏报 |
| `--staged` | 不用于任务后门禁 | 只读 index blob，与 agent 工作流边界不匹配 |

政策原文（对 agent 的约束，逐字引用）：

1. `After completing a code task, run the code-harness gate before reporting the task done, and report the mode, exit code and findings truthfully.`
2. `Never claim the gate passed when it was not run, failed with exit code 2, or the tool is not installed; state the reason explicitly instead.`
3. `Do not add suppressions or weaken the policy to make the gate appear green; policy changes require a separate full audit and review.`

配套指令：

1. 报告末行形如 `Architecture base: N files`。若 N=0 而任务确有代码改动，说明 base 选错了，
   必须重选，不能当作通过——干净树上 `--base HEAD` 会得到 0 文件、exit 0 的静默假通过。
2. 任务中改动过策略文件，不得仅凭 `--base` 判定通过，需另行 `--all` 并复审。
3. 任务开始前已存在的无关脏改动会被 `--base HEAD` 一并纳入，如实列出，不做静默过滤。

报告格式约定：写明运行的模式、退出码和 findings（error/warning 计数与关键项）。exit 2 或
未运行门禁时必须明说原因，绝不能宣称通过。

## Agent integration

skill 目录来自源码检出中的 `.agents/skills/code-harness/`（含 `SKILL.md` 与 `references/`）。
三条接入路径：

1. **原生 skills 目录**：消费项目符合 skills 目录约定时，把检出中的
   `.agents/skills/code-harness/` 复制到该项目（或用户级）的 skills 位置，agent 便可按 skill
   描述路由加载。
2. **agent 专属目录适配**：agent 只从自己的目录读取指令时，接入形态由目标目录的位置决定。
   仓库内（`--root` 之内）**禁用目录 symlink 接入**：门禁在 include/exclude 筛选之前就会拒绝
   遍历任何目录 symlink（exit 2），`exclude` 不能绕过。仓库内接入以**复制为主形态**，并接受
   副本漂移（源更新后需要重新复制，否则两处内容会分叉）；symlink 只适用于 `--root` **之外**
   的目录（如用户级 skills 目录），单一真相的收益也在那里。
   破坏面：仓库内留有目录 symlink 时，`--all`（bootstrap 首跑、策略复审、起始 commit 不可知
   时的回退）与带真实改动的 `--base`（其 usage 证据同样走全盘磁盘枚举）都会 exit 2。唯一仍
   能静默通过的是 0 文件退化形态，即 Per-task gating 一节配套指令 1 已要求识别的假通过（files=0
   而任务确有改动时必须重选 base）；`--staged` 不走磁盘枚举，但不用于任务后门禁。实际影响在
   第一个真实任务处即暴露。
3. **AGENTS.md 指针片段**：以 `AGENTS.md` 作为指令入口的 agent，把下面的片段加进它的指令
   文件。v1 为手动粘贴，不自动改写 AGENTS.md（它属于用户自己的政策资产）：

```markdown
<!-- code-harness skill pointer -->
When adopting, configuring, or running code-harness, or triaging its findings,
first read `.agents/skills/code-harness/SKILL.md` and follow it.
```

通用接入路径与限制见
[载体接入说明](../.agents/skills/code-harness/references/agent-integration.md)。
