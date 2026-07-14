---
name: imagegen
description: 使用火山方舟 Doubao Seedream 5.0 Lite 或 Pro 生成、编辑位图。适用于文生图、参考图生图、单图编辑、多图融合、Lite 组图/3K/4K/联网及时效图，以及 Pro 坐标点、圈选、涂鸦或草图交互编辑。需要联网且未指定模型时直接使用 Lite；联网与 Pro 冲突时使用 Claude Code AskUserQuestion 询问；不要用于 SVG/矢量图或适合用 HTML/CSS 确定性完成的视觉。
---

# Seedream 5.0 Pro / Lite

使用 `${CLAUDE_SKILL_DIR}/scripts/image_gen.py` 生成或编辑位图；默认从本 skill 根目录 `.env` 读取 Ark 配置。本 skill 只有 `generate` 和 `edit` 两类任务：按用户意图选择，不要用参考图是否存在来代替判断。所有真实请求经该统一 CLI 发往 `POST <ARK_BASE_URL>/images/generations`；不得创建临时 SDK/HTTP 脚本或修改 CLI。

## 快速执行准则

每次任务按以下顺序处理，避免把能力选择、真实请求与迭代混在一起：

1. 先判定是否需要联网，再按「模型选择」决定 Lite、Pro 或向用户询问；不得擅自替换用户已选模型。
2. 再判定是 `generate` 还是 `edit`，为每张输入图标注角色，并收集逐字文字、不变项、禁止项和交付路径。
3. 只读取当前决策所需的参考：模型能力看 `references/lite.md` 或 `references/pro.md`；提示词规则看 `references/prompting.md`；命令与恢复细节看 `references/cli.md`；透明背景看 `references/chroma-key.md`。
4. 首次真实请求可按已确认任务执行；此后的任何 POST 都是新一次可能计费的请求，必须先取得用户授权。`pending` 或 `ambiguous` 一律停止，先由用户核实状态。
5. 交付前实际查看输出，确认尺寸、格式、主体、文字、编辑不变项和禁止项；报告模型、完整 prompt 与绝对输出路径。

## 资源与交付约定

- `assets/seedream-imagegen-logo.png` 是 README 横幅；`assets/seedream-imagegen-icon.png` 是无文字方形 skill 图标。两者仅用于项目品牌展示，不作为模型参考图或生成结果提交。
- 单张最终图默认保存到项目根目录；Lite 组图默认保存到项目 `images/`。生成图片、`images/`、`output/`、缓存、`.env` 和请求状态文件不得提交 Git。
- 生成或改写的多行 prompt 临时文件只能使用项目根目录 `.seedream-prompt-<random-id>.txt`，并遵循下文的清理与状态保护规则。

## 模型选择（保持此询问方式）

先判断是否需要模型原生联网，再检查用户是否已明确选择模型：

- 用户只明确选择 Lite 或 Pro，且没有与联网或模型能力冲突时直接使用，不调用 `AskUserQuestion`。
- 用户或其 prompt 明确要求联网、搜索、检索最新/实时信息，或任务明显依赖时效事实时，视为需要联网。带有具体近期日期的“世界局势、时局、新闻、天气、行情、赛程、现任人物或近期产品状态”等请求必须按联网需求处理，不能因为用户只写了 Pro 就判断为“不涉及联网”。任务没有明确要求但模型搜索能实质提高时效事实准确性时，也可按需要开启。
- 需要联网且未指定模型时直接选择 Lite 并传 `--web-search`，不调用 `AskUserQuestion`。
- 同时明确要求 Pro（或 Pro 专属能力）与联网时，调用 `AskUserQuestion`，只让用户二选一：`Lite 联网`，或 `Pro 生图能力（不使用模型原生联网）`。选择前不得提交请求；`AskUserQuestion` 不可用时停止并直接向用户请求选择，不得默认其一。
- 不需要联网时，用户未提到模型，或同时提到 Lite 和 Pro 但未明确选择，调用 `AskUserQuestion`。
- 只有准确选择 `Seedream 5.0 Pro` 才传 `--model pro`。
- 在不涉及能力冲突的普通模型询问中，Lite、取消、空答案、Other、自定义值或 `AskUserQuestion` 不可用时传 `--model lite`。
- 用户选择的模型与所需能力冲突时本地报错并解释冲突，不静默切换模型、降级规格或改写任务。

| 能力 | Lite | Pro |
|---|---|---|
| 分辨率 | 2K/3K/4K | 1K/2K |
| 参考图 | 最多 14 张 | 最多 10 张 |
| 组图 / stream / web_search | 支持 | 不支持 |
| 坐标点、圈选、涂鸦、草图编辑 | 支持普通标记 | 优先选择 |

## 适用边界

适用：写实图片、商品图、插画、概念图、UI mockup、信息图、教学图、广告创意、纹理、精灵图，以及需要保留现有图片大部分内容的编辑。

不适用：现有 SVG/矢量图标体系、可编辑源格式中的小改动、需要确定性 HTML/CSS/canvas 输出的图形、纯文字排版或必须像素级准确的表格/图表。

## 任务判定

先分别判断「意图」和「执行策略」。

意图：

- 修改现有图片并保留未编辑内容时使用 `edit`。
- 图片仅提供风格、构图、主体、材质或氛围参考时使用 `generate --image`。
- 没有输入图片时使用 `generate`。
- 多图融合通常使用 `generate --image`；只有以某张现有图为基础且需保留其未编辑区域时使用 `edit`。

执行策略：

- 单资产默认单图、非流式；Lite 组图仅用于明确要求一组连续图片。
- 不要把不同资产塞进同一组图请求；每项不同内容分别生成。
- `web_search`、stream 与组图仅可在 Lite 中使用。只要用户/prompt 明确要求联网就启用 `--web-search`；未明确要求时，仅在任务依赖最新事实且模型搜索有实际价值时按需启用。Pro 的最新事实必须先由外部检索核实，再将事实写入 prompt，不能声称 Pro 原生联网。

每张输入图均按 CLI `--image` 顺序标明角色：`编辑目标`、`内容来源`、`风格参考` 或 `交互标记图`；称为「图一、图二……」，不依赖文件名猜测角色。

## 工作流

1. 按模型选择规则决定 Lite 或 Pro；只读取所选模型的 `references/lite.md` 或 `references/pro.md`。
2. 判断 `generate`/`edit`、单图/组图、预览/项目交付；收集 prompt、逐字文字、输入图角色、必须保持项、禁止项及输出位置。
3. 将请求整理为短而清晰的生产规格。用户 prompt 已具体时只结构化；较泛时仅补充有助于结果的构图、用途或材质细节。
4. 需要时读取 `references/prompting.md`，并按其分类、结构和验收规则编写 prompt；模板仅作为按需参考，见 `references/sample-prompts.md`。
5. 多行或含引号 prompt 直接写入项目根目录 `${CLAUDE_PROJECT_DIR}/.seedream-prompt-<random-id>.txt`，使用不含 prompt 内容的随机 ASCII ID，并传 `--prompt-file --cleanup-prompt-file`，避免 shell 转义损坏逐字文本且不创建 `tmp/seedream`。每次改写 prompt 使用新的临时文件。只标记清理由 agent 创建且符合该命名的文件；不得删除用户提供的 prompt 文件或输入图。
6. `--dry-run` 不是默认步骤。仅在组图、stream、多参考图、自定义尺寸、显式 `--allow-model-fallback`、已有输出或覆盖风险时先执行；`--prompt-file`、`--cleanup-prompt-file`、普通 2K 单图和 `--web-search` 本身不要求 dry-run。它只输出脱敏 payload、配置来源和预检结果，不提交或计费。参数细节见 `references/cli.md`。
7. 始终根据 `${CLAUDE_PROJECT_DIR}` 传入绝对 `--out` 或 `--out-dir`：单图默认非破坏保存至项目根目录，组图默认保存至项目 `images/`。默认名冲突时追加 `-v2`、`-v3`；显式目标不得覆盖，仅用户明确允许时使用 `--force`。
8. 真实请求前确认规格、参数和输出路径与模型能力相容。生图会计费：首次请求按用户任务执行；第一次真实 POST 后的任何再次 POST——包括内容审核明确拒绝后改写 prompt、质量迭代、重生成或变体——都在发起前取得用户授权。`pending`/`ambiguous` 还必须先核实状态，不能仅凭用户同意绕过状态锁。
9. 生成后实际查看每张图片，检查真实尺寸、格式、主体、构图、文字、参考一致性、编辑不变项和禁止项；不要用 prompt 复述代替验收。
10. 需要迭代时一次只改一个主要问题，重复关键不变项；报告最终模型、完整 prompt 与绝对输出路径。

## 中间产物清理

真实生成调用只要结束，无论成功、明确拒绝、本地失败、超时或 `ambiguous`，CLI 都清理本次显式标记的项目根目录 `.seedream-prompt-<random-id>.txt`；dry-run 为了供后续真实请求复用而保留。每次生成或改写使用独立文件，因此失败版本也不会遗留。旧版 `${CLAUDE_PROJECT_DIR}/tmp/seedream/` 路径只保留 CLI 清理兼容，agent 不再新建。色键源图只有在它是 agent 明确创建且仍有其他可恢复原件的工作副本时才能清理。不得删除生成原图、最终交付图片、用户输入、显式输出目录内容或任何 `pending`/`ambiguous` 状态文件。

默认：2K、PNG、无水印、单图、非流式、不开联网。重要文字必须逐字核对；不合格时优先建议确定性后期排版。

## Prompt 规范

每个请求归入一个分类 slug，保持与参考模板一致。

生成：`photorealistic-natural`、`product-mockup`、`ui-mockup`、`infographic-diagram`、`scientific-educational`、`ads-marketing`、`productivity-visual`、`logo-brand`、`illustration-story`、`stylized-concept`、`historical-scene`。

编辑：`text-localization`、`identity-preserve`、`precise-object-edit`、`lighting-weather`、`background-extraction`、`style-transfer`、`compositing`、`sketch-to-render`。

按需使用以下短标签，不要机械填满：

```text
用途：<落地页主视觉 / 商品页 / 教学图等>
任务类型：<分类 slug>
核心请求：<用户的主要目标>
输入图片：<图一：角色；图二：角色>（可选）
场景/背景：<视觉环境>
主体：<主要对象和动作>
风格/媒介：<摄影 / 插画 / 3D 等>
构图/景别：<镜头、视角、主体位置、留白>
光线/氛围：<光照和情绪>
色彩/材质：<必要的色彩和表面细节>
文字（逐字）："<准确文字>"
必须保持：<身份、布局、比例等>
禁止：<不应出现的内容>
```

- 具体请求只规范化，不加角色、道具、品牌、配色、标语或叙事。
- 泛化请求可补充构图、用途、合理的场景具体度；没有版式依据时不要强加左右位置。
- 编辑必须写成「只改 X；保持 Y 不变」，每轮迭代重复不变项。
- 文字用引号逐字写出，并指定层级、位置与样式；不要让模型补文案。
- 多图明确说明如何交互，例如「把图二服装用于图一人物」。

## 透明背景

模型不能稳定直接输出透明 alpha。简单、不含键色色相族的实心主体可使用色键；完整模板只保存在 `references/sample-prompts.md`，参数、格式、停止条件与三项交付检查见 `references/chroma-key.md`。

生成后显式传入实际键色；背景通过 auto-key 四角共识时才允许自动取色。毛发、玻璃、烟雾、液体、反光、软阴影、半透明或主体包含候选键色色相族时，停止简单色键方案并说明限制。

## 安全与配置

- 配置优先级为进程环境、skill-local `.env`、CLI 内置默认值；`ARK_BASE_URL`、`ARK_PRO_MODEL`、`ARK_LITE_MODEL` 仅在自定义 endpoint 或 Model ID 时配置。Model ID 覆盖不改变对应 Pro/Lite 的本地能力校验。skill-local `.env` 只进入本次 CLI 配置对象，不修改 `os.environ`、Windows 环境或 `.env` 文件。
- 不要求用户在对话中提供 `ARK_API_KEY`，也不得打印密钥、Base64 输入图、签名 URL 或未经脱敏的 API 响应。
- 生图 POST 可能计费且不自动重试；超时、中断或断连后，先检查输出与对应的 `.seedream-request.json` 状态文件。默认组图状态按提示词隔离，避免不同组图互相阻塞。
- `--dry-run` 仅在命令显式包含该参数时生效，不提交请求，可报告输出冲突和未知请求状态；CLI 不会根据 prompt、输出路径或 `--web-search` 隐式开启。真实请求出现 `pending` 或 `ambiguous` 状态必须停止。
- 状态文件是唯一重试依据。即使 stderr 提到 HTTP 400、内容审核、敏感内容或 agent 主观判断“未生成/不会计费”，只要状态文件为 `pending` 或 `ambiguous`，就不得删除状态、改写 prompt 后重试或自行宣称不计费；必须停止并请用户核实。只有 CLI 自己按明确拒绝 allowlist 删除状态后，才可继续当前流程。
- `--force` 仅在用户明确授权覆盖时使用。

## 按需参考

- `references/prompting.md`：提示词结构、分类、文字、参考图、编辑、透明背景与验收。
- `references/sample-prompts.md`：可复制的生成、编辑、标记、组图和联网模板。
- `references/cli.md`：CLI、端点、配置、输入/输出、dry-run 与失败恢复。
- `references/chroma-key.md`：色键 CLI、alpha、格式、失败恢复和轻量交付检查。
- `references/lite.md`：Lite 能力、API payload、尺寸、组图、联网与 SSE。
- `references/pro.md`：Pro 能力、API payload、尺寸、输入与响应限制。
