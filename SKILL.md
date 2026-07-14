---
name: imagegen
description: 使用火山方舟 Doubao Seedream 5.0 Lite 或 Pro 生成、编辑位图。适用于文生图、参考图生图、单图编辑、多图融合、Lite 组图/3K/4K/联网及时效图，以及 Pro 坐标点、圈选、涂鸦或草图交互编辑。需要联网且未指定模型时直接使用 Lite；联网与 Pro 冲突时使用 Claude Code AskUserQuestion 询问；不要用于 SVG/矢量图或适合用 HTML/CSS 确定性完成的视觉。
---

# Seedream 5.0 Pro / Lite

使用 `${CLAUDE_SKILL_DIR}/scripts/image_gen.py` 生成或编辑位图；默认从本 skill 根目录 `.env` 读取 Ark 配置。按用户意图选择 `generate` 或 `edit`，不要用参考图是否存在代替判断。所有真实请求均由该 CLI 发往 `POST <ARK_BASE_URL>/images/generations`；不得另写 SDK/HTTP 脚本或修改 CLI。

Claude Code 渲染本文件时使用官方字符串替换得到绝对路径。原生 Windows 有 PowerShell tool 时直接使用 PowerShell，否则使用 Bash/Git Bash；macOS、Linux 和 WSL 使用 Bash。不要询问、列举或解释 shell 选择。每次工具调用都重新初始化路径，不假设变量跨调用保留。

PowerShell：

```powershell
$skillDir = "${CLAUDE_SKILL_DIR}"
$projectDir = "${CLAUDE_PROJECT_DIR}"
```

Bash：

```bash
skill_dir="${CLAUDE_SKILL_DIR}"
project_dir="${CLAUDE_PROJECT_DIR}"
```

只使用加双引号的本地路径变量调用 bundled scripts 和传递项目路径。`references/` 作为普通文件读取。

## 模型选择

先判断是否需要模型原生联网，再检查用户是否已选择模型：

- 用户只明确选择 Lite 或 Pro，且没有与联网或模型能力冲突时直接使用，不询问也不替换。
- 用户或 prompt 明确要求联网、搜索、最新/实时信息，或任务依赖带有具体近期日期的新闻、天气、行情、赛程、现任人物、近期产品状态等时效事实时，视为需要联网。
- 需要联网且未指定模型时直接选择 Lite 并传 `--web-search`。
- 同时要求 Pro（或 Pro 专属能力）与联网时，用 `AskUserQuestion` 让用户二选一：`Lite 联网`，或 `Pro 生图能力（不使用模型原生联网）`。工具不可用时直接询问；选择前不得请求。
- 不需要联网且未指定模型，或同时提到 Lite 和 Pro 但未明确选择时，调用 `AskUserQuestion`。
- 只有准确选择 Pro 才传 `--model pro`；普通模型询问中的 Lite、取消、空答案、Other、自定义值或询问工具不可用时使用 `--model lite`。
- 能力冲突时本地报错并解释，不静默切换模型、降级规格或改写任务。

| 能力 | Lite | Pro |
|---|---|---|
| 分辨率 | 2K/3K/4K | 1K/2K |
| 参考图 | 最多 14 张 | 最多 10 张 |
| 组图 / stream / web_search | 支持 | 不支持 |
| 坐标点、圈选、涂鸦、草图编辑 | 支持普通标记 | 优先选择 |

只读取所选模型的 [Lite 规范](references/lite.md) 或 [Pro 规范](references/pro.md)。

## 任务判定

先分别判断用户意图和执行策略：

- 修改现有图片并保留未编辑内容时使用 `edit`。
- 图片只提供风格、构图、主体、材质或氛围参考时使用 `generate --image`。
- 没有输入图片时使用 `generate`。
- 多图融合通常使用 `generate --image`；只有以某张现有图为基础并保持其未编辑区域时才使用 `edit`。
- 单资产默认单图、非流式；Lite 组图只用于用户明确要求的一组连续图片，不要把不同资产塞入同一组图请求。
- `web_search`、stream 和组图只可用于 Lite。Pro 需要最新事实时，先由外部检索核实并写入 prompt，不得声称 Pro 原生联网。

每张输入图均按 `--image` 顺序标明角色：`编辑目标`、`内容来源`、`风格参考` 或 `交互标记图`；称为图一、图二……，不依赖文件名猜测角色。

用户没有提供或明确引用输入图片、prompt 文件时，按没有输入文件处理；不得用 Glob、Search、`find`、`ls` 或递归目录扫描寻找候选图片、旧 prompt 或临时文件。只有用户明确要求使用现有文件但未给路径时，才定向查找或询问。

## 执行流程

1. 按上述规则确定 Lite、Pro 或先询问用户；不得擅自替换用户选择。
2. 按“任务判定”选择 `generate`/`edit`、单图/组图，并确认每张输入图角色。
3. 只读取当前决策需要的 reference：模型能力看所选模型规范；prompt、CLI、色键和视觉示例按需读取，不一次加载全部。
4. 收集用户主要目标、逐字文字、必须保持项、禁止项和交付位置，整理为短而明确的生产规格。
5. 每个请求选择一个分类 slug，并以 `任务类型：<slug>` 写入 prompt；具体请求只结构化，泛化请求只补充有助于结果的构图、用途、光影或材质。
6. 需要时按 `references/cli.md` 执行 dry-run，确认模型、参数、输入、输出和覆盖状态相容。
7. 首次真实请求可按已确认任务执行。第一次真实 POST 后的任何再次 POST，包括内容审核明确拒绝后改写 prompt、质量迭代、重生成或变体，都必须先取得用户授权。
8. 生成后实际查看每张图片，检查真实尺寸、格式、主体、构图、文字、参考一致性、编辑不变项和禁止项；报告最终模型、完整 prompt 与绝对输出路径。需要迭代时一次只改一个主要问题。

默认：2K、PNG、无水印、单图、非流式、不开联网。单资产默认单图；只有用户明确要求连续图片时使用 Lite 组图。不要把不同资产塞进同一组图请求。

## Prompt 与交付

- Prompt 跟随用户主要输入文本的语言；混合或不明确时沿用对话与用户语言习惯，逐字文字保持原文。完整编写规则见 [Prompt 与验收](references/prompting.md)，需要可复制结构时看 [Prompt 模板](references/sample-prompts.md)。
- 多行或含引号的 prompt 写入项目根目录 `.seedream-prompt-<random-id>.txt`；ID 使用 6–64 位 ASCII 字母、数字、`_` 或 `-`，不含 prompt 摘要。传 `--prompt-file --cleanup-prompt-file`，每次改写使用新文件。
- 始终根据项目根目录传入绝对 `--out` 或 `--out-dir`。单图默认保存到项目根目录，Lite 组图默认保存到 `images/`；默认名冲突时追加 `-v2`、`-v3`。显式目标不得覆盖，只有用户明确允许时使用 `--force`。
- `--dry-run` 不是默认步骤。只在组图、stream、多参考图、自定义尺寸、显式 `--allow-model-fallback`、已有输出或覆盖风险时先执行；普通 2K 单图、`--prompt-file`、`--cleanup-prompt-file` 和 `--web-search` 本身不要求 dry-run。
- 重要文字必须逐字核对；不合格时优先建议确定性后期排版。交付前用实际观察验收，不用 prompt 复述代替检查。

## 文件、状态与安全

- 真实请求结束后，CLI 清理本次显式标记的 agent prompt；dry-run 保留供后续真实请求使用。
- 只允许清理由 agent 创建且符合命名规则的 prompt 文件。不得删除用户输入、用户 prompt、生成原图、最终图片、显式输出目录内容或请求状态文件；色键源图只有在它是 agent 创建的工作副本且另有可恢复原件时才能清理。
- `pending` 或 `ambiguous` 必须停止并请用户核实输出与计费，不得自动重试、删除状态或仅凭用户同意绕过状态锁。即使 stderr 提到 HTTP 400、内容审核、敏感内容，只要状态仍为 `pending`/`ambiguous` 就不得认定未计费；只有 CLI 按明确拒绝 allowlist 删除状态后才可继续。
- 状态文件是唯一重试依据。超时、中断、断连或保存不确定时先检查输出和对应 `.seedream-request.json`；默认组图状态按 prompt 隔离，避免不同组图互相阻塞。
- 配置优先级为进程环境、skill-local `.env`、CLI 默认值；Model ID 覆盖不改变对应 Pro/Lite 的本地能力校验。不得要求用户在对话中提供 `ARK_API_KEY`，也不得打印密钥、Base64 输入图、签名 URL 或未经脱敏的 API 响应。
- 生成图片、`images/`、`output/`、缓存、`.env` 和请求状态文件不得提交 Git。

## 适用边界与资源

适用于写实图片、商品图、插画、概念图、UI mockup、信息图、教学图、广告创意、纹理、精灵图，以及需保留现有图片大部分内容的编辑。不适用于 SVG/矢量图标体系、可编辑源格式的小改动、确定性 HTML/CSS/canvas 图形、纯文字排版或必须像素级准确的表格/图表。

- [Prompt 与验收](references/prompting.md)：分类、结构、文字、参考图、编辑、透明背景与验收规则。
- [Prompt 模板](references/sample-prompts.md)：生成、编辑、标记、组图、联网和透明背景的结构化模板。
- [视觉示例](references/visual-examples.md)：四类可选视觉参考、完整 prompt 与引用限制。只有用户需要相应方向时读取；不得默认把 `assets/examples/` 注入请求或照搬主体、场景、构图和文字。
- [CLI 参考](references/cli.md)：配置、参数、输入输出、dry-run、保存与失败恢复。
- [色键参考](references/chroma-key.md)：色键参数、alpha 契约、停止条件与交付检查。模型不能稳定直接输出透明 alpha；毛发、玻璃、烟雾、液体、反光、软阴影或半透明主体不适合简单色键。
- `logo/` 仅用于项目品牌展示，不作为模型参考或生成结果。
