# Seedream CLI 参考

本文规定 bundled `scripts/image_gen.py` CLI 的调用、预检、保存和失败恢复。它不重新定义模型能力：Lite 见 `lite.md`，Pro 见 `pro.md`。所有真实请求都必须通过该脚本，不得临时编写 SDK/HTTP runner 或修改脚本。

## Shell 约定

本文命令以 PowerShell 展示，依赖 `SKILL.md` 已渲染并初始化的 `$skillDir` / `$projectDir`；必须把初始化与命令放在同一次 PowerShell 调用中。Bash 使用同处定义的 `skill_dir` / `project_dir` 和 POSIX 路径。

## 快速开始

从任意工作目录调用 skill 脚本。以下示例依赖 `SKILL.md` 已渲染出的 `$skillDir` / `$projectDir` 初始化行；必须把初始化与命令放在同一次 PowerShell 调用中。以下是普通单图真实请求；可能计费：

```powershell
python "$skillDir\scripts\image_gen.py" generate --model lite `
  --prompt "极简陶瓷杯商品摄影" --size 2K `
  --project-dir "$projectDir" --out "$projectDir\output\seedream\cup.png"
```

只有显式加入 `--dry-run` 才会执行不计费的本地预检。CLI 不会自动开启它；真实请求需要 `ARK_API_KEY` 和可访问的 Ark 服务，dry-run 不需要网络或密钥。

## 配置与端点

- `run()` 惰性加载 skill 根目录 `.env`，只读取 `ARK_API_KEY`、`ARK_BASE_URL`、`ARK_PRO_MODEL`、`ARK_LITE_MODEL`；支持有或无 BOM 的 UTF-8，不修改 `os.environ`。
- 配置优先级为进程环境、skill-local `.env`、内置默认值。未设置 `ARK_BASE_URL` 时使用 `https://ark.cn-beijing.volces.com/api/v3`；Pro/Lite Model ID 也使用内置值。`.env` 中无需重复配置默认值。仅 localhost、`127.0.0.1`、`::1` 可使用 HTTP。
- `ARK_PRO_MODEL` 与 `ARK_LITE_MODEL` 仅覆盖对应层级发送到 payload 的 Model ID，不改变 Pro/Lite 的本地能力、尺寸和参数校验规则。
- 基础地址不得含认证信息、查询参数或片段。诊断只能显示配置来源（`skill-local .env`、`process environment`、`default`、`unset`），不能显示值。
- 请求为 `POST <ARK_BASE_URL>/images/generations`，使用 `Authorization: Bearer <ARK_API_KEY>` 和 JSON payload。
- 不要要求用户在聊天中粘贴密钥；请其在本机 `.env` 或环境变量中配置。

## 命令与模型路由

| 命令 | 用途 | 必要条件 |
|---|---|---|
| `generate` | 文生图、参考图生图、多图融合、Lite 组图 | `--prompt` 或 `--prompt-file` |
| `edit` | 基于现有图片的编辑或标记编辑 | 至少一个 `--image` |

- `--prompt` 与 UTF-8 `--prompt-file` 只能二选一；多行、含引号或逐字文字优先后者。
- `pro` 或精确 Pro Model ID 路由 Pro；`lite`、Lite Model ID 或空值路由 Lite。未知值默认失败；只有显式 `--allow-model-fallback` 才兼容回退 Lite，并必须先检查 `--dry-run` warning。
- 仅按 `SKILL.md` 的模型决策传入 `--model pro` 或 `--model lite`。CLI 会拒绝 Pro 与 `--web-search` 的冲突，不静默切换。

## 参数与模式规则

通用参数：`--image`（可重复）、`--size`、`--output-format`、`--response-format`、`--watermark`/`--no-watermark`、`--project-dir`、`--out`、`--force`、`--private-filenames`、`--timeout`、`--dry-run`。Seedream 5.0 Pro/Lite 不接受 `--seed` 或 `--guidance-scale`。

`--cleanup-prompt-file` 仅可与 `--prompt-file` 使用。agent 在项目根目录创建 `.seedream-prompt-<random-id>.txt`：ID 使用 6–64 位 ASCII 字母、数字、`_` 或 `-`，首字符须为字母或数字，不得包含 prompt 摘要。文件必须是普通非 symlink/junction 文件，且不与输入、输出或状态路径冲突。真实生成调用结束后无论成功或失败都删除；dry-run 保留，供后续真实请求复用。

- 默认：Lite、2K、PNG、`url`、无水印、单图、非流式、不开联网、`--timeout 300`。timeout 是单次网络/socket operation 上限，不是整次生成总 deadline。`--watermark` 发送 JSON 布尔值 `true`，`--no-watermark` 发送 `false`。
- Pro 自定义 `WIDTHxHEIGHT` 的宽、高均须为 16 的倍数。尺寸和功能组合由所选模型本地验证。
- Lite 单图发送 `sequential_image_generation="disabled"`；组图使用 `--sequential auto --max-images N`，可选 `--out-dir DIRECTORY`。
- 组图不能使用 `--out`；单图不能使用 `--out-dir` 或 `--max-images`。Pro 拒绝组图、`--stream`、`--web-search`。组图默认必须保存满 `--max-images`；只有明确接受缺图时才传 `--allow-partial-group`。
- `--web-search` 和 `--stream` 仅 Lite。开启搜索工具后由模型决定是否实际搜索，CLI 只报告 usage，不能将其当作可引用或已核验的信息。

## 输入、输出与保存

- `--image` 接受本地路径、公开 HTTP(S) URL 或 `data:image/<小写格式>;base64,...`。支持 jpeg、png、webp、bmp、tiff、gif、heic、heif。
- 每张输入图不超过 30 MB，宽高均大于 14 px，总像素不超过 36,000,000，宽高比在 `[1/16,16]`。本地/data URI 输入还受 120,000,000 bytes 聚合上限和 170,000,000 bytes 预计完整请求体上限约束；在大量 Base64 编码前预检。HEIC/HEIF 需要 `pillow-heif`。
- 未传 `--out` 时，单图固定保存至 `<project-dir>/`；默认名由 prompt 生成内容相关 slug，例如 `极简陶瓷杯商品摄影.png`。
- 组图未传 `--out-dir` 时固定保存至 `<project-dir>/images/`；文件名为 `<提示词>-01.png`、`-02.png`……。显式 `--out-dir` 时仍使用 `image-01.ext`、`image-02.ext`……。
- 默认文件名或默认组图冲突时，自动追加 `-v2`、`-v3` 等版本名，不覆盖已有图片。显式 `--out` 用于单图，`--out-dir` 用于组图。
- 默认落盘目录与内容相关文件名是固定产品规则。`--private-filenames` 默认关闭，且仅在用户或 prompt 明确要求隐藏内容时使用；它改用 `seedream-<prompt hash>`，不是随机命名。
- 任一路径组件中的 Windows 保留名/非法字符、尾随空格/句点、超过 255 UTF-8 bytes 的名称，以及超过 240 字符的非可移植目标路径都会在 POST 前失败。
- 输出扩展名必须匹配 `--output-format`；默认 PNG，只有明确需要 JPEG 时使用 `.jpg`/`.jpeg` 与 `--output-format jpeg`。
- 显式 `--out` 或显式 `--out-dir` 的组图计划目标已存在时不会覆盖；仅获得明确授权才使用 `--force`。`--force` 只覆盖本次计划目标，不清理 `--out-dir` 的其他文件；默认自动命名不需要 `--force`。脚本以原子写入落盘并验证真实图片格式和尺寸。

## Dry-run、计费与恢复

`--dry-run` 只在命令显式包含该参数时生效，只做本地校验，输出递归脱敏 payload（prompt、Base64、远程 URL 均隐藏）、计划路径、配置来源和 preflight 诊断；不会调用 Ark 或计费。以下情况必须先预检：组图、stream、多参考图、自定义尺寸、显式 model fallback、目标已存在或准备使用 `--force`。`--prompt-file`、`--cleanup-prompt-file`、普通 2K 单图及 `--web-search` 本身不触发也不强制要求 dry-run。

- 状态文件按 payload 指纹存于 `<project-dir>/.seedream-requests/<hash>.json`；变更输出路径不能绕过请求锁。用 `python "$skillDir\scripts\image_gen.py" state --project-dir "$projectDir"` 只读查看状态；同步请求不能安全续传。
- 状态仅保存 payload hash、目标、时间、PID 和状态，不保存 prompt、图片、密钥或 URL。
- 成功时先将状态标为 `completed` 再尝试删除；清理失败只告警，不把已落盘图片误报为失败，`completed` 状态不会阻止后续请求。白名单中能够证明提交前拒绝的 HTTP/Ark code 组合也会删除状态；408、429、5xx、未知业务码、超时、中断、断流、响应异常或保存不确定时标记 `ambiguous`。
- 发现 `pending` 或 `ambiguous` 必须停止，先核实输出与计费；不得自动重试或删除状态文件来绕过保护。
- HTTP 400、内容审核或敏感内容提示本身不能覆盖状态分类。只要状态文件仍为 `pending`/`ambiguous`，agent 不得自行认定“未计费”、手动删除状态或换 prompt 重试；只有 CLI 根据明确拒绝 allowlist 自动删除状态后才能继续。
- 第一次真实 POST 后，即使 CLI 已把内容审核结果明确分类为 rejected 并自动删除状态，改写 prompt 后的下一次 POST 仍属于可能计费的迭代，必须先取得用户授权。
- 流式模式只保存 `partial_succeeded` 最终图；`partial_image` 是预览。缺少 `completed` 事件时视为不确定。
- 真实生成尝试结束后，CLI 清理显式标记的 agent prompt；dry-run 保留它。成功时 CLI 删除请求状态和原子写入临时文件；失败时按分类保留或删除状态。不要删除最终图片、用户提供的输入图/提示词文件，或 `pending`/`ambiguous` 状态文件；后两者是计费与恢复证据。

## 典型命令

Pro 标记编辑：

```powershell
python "$skillDir\scripts\image_gen.py" edit --model pro `
  --image C:\input\marked.png --prompt-file C:\input\edit-prompt.txt `
  --out "$projectDir\output\seedream\edited.png" --dry-run
```

Lite 组图：

```powershell
python "$skillDir\scripts\image_gen.py" generate --model lite `
  --prompt-file C:\input\series.txt --size 4K `
  --sequential auto --max-images 4 `
  --out-dir "$projectDir\output\seedream\series" --dry-run
```

Lite 联网单图（以下为真实请求，可能计费；仅 `--web-search` 不要求 dry-run）：

```powershell
python "$skillDir\scripts\image_gen.py" generate --model lite `
  --prompt "联网搜索并制作上海未来5日天气图" --web-search `
  --out "$projectDir\output\seedream\weather.png"
```
