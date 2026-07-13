---
name: imagegen
description: 使用火山方舟 Doubao Seedream 5.0 Lite 或 Pro 生成、编辑位图。适用于文生图、参考图生图、单图编辑、多图融合、Lite 组图/3K/4K/联网及时效图，以及 Pro 坐标点、圈选、涂鸦或草图交互编辑。用户未明确选择 Lite 或 Pro 时使用 Claude Code AskUserQuestion 询问；不要用于 SVG/矢量图或适合用 HTML/CSS 确定性完成的视觉。
---

# Seedream 5.0 Pro / Lite

使用 `scripts/image_gen.py` 生成或编辑位图；默认从本 skill 根目录 `.env` 读取 Ark 配置。本 skill 只有 `generate` 和 `edit` 两类任务：按用户意图选择，不要用参考图是否存在来代替判断。所有真实请求经该统一 CLI 发往 `POST <ARK_BASE_URL>/images/generations`；不得创建临时 SDK/HTTP 脚本或修改 CLI。

## 模型选择（保持此询问方式）

先检查用户是否已明确选择模型，不要按任务能力自动替用户选择：

- 用户只明确选择 Lite 或 Pro 时直接使用，不调用 `AskUserQuestion`。
- 用户未提到模型，或同时提到 Lite 和 Pro 但未明确选择时，调用 `AskUserQuestion`。
- 只有准确选择 `Seedream 5.0 Pro` 才传 `--model pro`。
- Lite、取消、空答案、Other、自定义值或 `AskUserQuestion` 不可用时传 `--model lite`。
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
- 联网、stream 与组图仅可在 Lite 中使用。Pro 的最新事实必须先由外部检索核实，再将事实写入 prompt，不能声称 Pro 原生联网。

每张输入图均按 CLI `--image` 顺序标明角色：`编辑目标`、`内容来源`、`风格参考` 或 `交互标记图`；称为「图一、图二……」，不依赖文件名猜测角色。

## 工作流

1. 按模型选择规则决定 Lite 或 Pro；只读取所选模型的 `references/lite.md` 或 `references/pro.md`。
2. 判断 `generate`/`edit`、单图/组图、预览/项目交付；收集 prompt、逐字文字、输入图角色、必须保持项、禁止项及输出位置。
3. 将请求整理为短而清晰的生产规格。用户 prompt 已具体时只结构化；较泛时仅补充有助于结果的构图、用途或材质细节。
4. 需要时读取 `references/prompting.md`，并按其分类、结构和验收规则编写 prompt；模板仅作为按需参考，见 `references/sample-prompts.md`。
5. 多行或含引号 prompt 写入当前项目 `tmp/seedream/` 下的 UTF-8 临时文件并使用 `--prompt-file --cleanup-prompt-file`，避免 shell 转义损坏逐字文本。只清理由 agent 创建的临时文件；不得删除用户提供的 prompt 文件或输入图。
6. 组图、stream、web_search、多参考图、自定义尺寸、未知模型 fallback、已有输出或覆盖风险，先执行 `--dry-run`；它只输出脱敏 payload、配置来源和预检结果，不提交或计费。参数细节见 `references/cli.md`。
7. 未传 `--out` 时，单图默认非破坏保存至运行 Claude Code 的当前项目根目录；用清理后的 prompt 作为文件名，冲突时自动追加 `-v2`、`-v3`。组图未传 `--out-dir` 时保存至当前项目 `images/`，以 `<提示词>-01.png`、`-02.png` 命名。显式输出路径或组图计划目标不得覆盖；仅用户明确允许时使用 `--force`，且它不会清理目录内其他文件。
8. 真实请求前确认规格、参数和输出路径与模型能力相容。生图会计费：首次请求按用户任务执行；任何质量迭代、重生成或变体在发起下一次付费请求前取得授权。
9. 生成后实际查看每张图片，检查真实尺寸、格式、主体、构图、文字、参考一致性、编辑不变项和禁止项；不要用 prompt 复述代替验收。
10. 需要迭代时一次只改一个主要问题，重复关键不变项；报告最终模型、完整 prompt 与绝对输出路径。

## 中间产物清理

仅在请求成功、最终图片已验证并保存后清理：agent 创建的 `tmp/seedream/` prompt 文件、色键处理的源图以及空的临时目录。不得删除最终交付图片、用户提供的输入文件、显式指定的输出目录内容，或 `pending`/`ambiguous` 状态文件。后者可能表示已计费但结果未知，必须保留用于核对。

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

模型不能稳定直接输出透明 alpha。简单、不含键色的实心主体可使用色键；复杂抠图不得承诺成功。

1. 在 prompt 中要求完全均匀的 `#00ff00` 背景；绿色主体改用 `#ff00ff`，禁止阴影、渐变、纹理、反射、地面和背景光照变化。
2. 生成后运行 `python scripts\remove_chroma_key.py --input <source> --out <final.png> --auto-key border --soft-matte --despill`。
3. 检查 alpha、边缘色溢、孔洞和主体颜色；确有白边时才小幅使用 `--edge-contract` 或 `--edge-feather`。
4. 毛发、玻璃、烟雾、液体、反光、软阴影或半透明材质，改用专业分割工具。

## 安全与配置

- skill-local `.env` 只覆盖当前 Python 进程的 `ARK_API_KEY` 和 `ARK_BASE_URL`；不得修改 Windows 环境或 `.env` 文件。
- 不要求用户在对话中提供 `ARK_API_KEY`，也不得打印密钥、Base64 输入图、签名 URL 或未经脱敏的 API 响应。
- 生图 POST 可能计费且不自动重试；超时、中断或断连后，先检查输出与对应的 `.seedream-request.json` 状态文件。默认组图状态按提示词隔离，避免不同组图互相阻塞。
- `--dry-run` 不提交请求，可报告输出冲突和未知请求状态；真实请求出现 `pending` 或 `ambiguous` 状态必须停止。
- `--force` 仅在用户明确授权覆盖时使用。

## 按需参考

- `references/prompting.md`：提示词结构、分类、文字、参考图、编辑、透明背景与验收。
- `references/sample-prompts.md`：可复制的生成、编辑、标记、组图和联网模板。
- `references/cli.md`：CLI、端点、配置、输入/输出、dry-run 与失败恢复。
- `references/lite.md`：Lite 能力、API payload、尺寸、组图、联网与 SSE。
- `references/pro.md`：Pro 能力、API payload、尺寸、输入与响应限制。
