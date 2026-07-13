# Seedream CLI 参考

本文规定 `scripts/image_gen.py` 的调用、预检、保存和失败恢复。它不重新定义模型能力：Lite 见 `lite.md`，Pro 见 `pro.md`。所有真实请求都必须通过该脚本，不得临时编写 SDK/HTTP runner 或修改脚本。

## 快速开始

从任意工作目录调用 skill 脚本。先运行不计费的预检：

```powershell
python <SKILL_DIR>\scripts\image_gen.py generate --model lite `
  --prompt "极简陶瓷杯商品摄影" --size 2K `
  --out output\seedream\cup.png --dry-run
```

确认预检后移除 `--dry-run`。真实请求需要 `ARK_API_KEY` 和可访问的 Ark 服务；`--dry-run` 不需要网络或密钥。

## 配置与端点

- 脚本加载 skill 根目录 `.env`，只读取 `ARK_API_KEY`、`ARK_BASE_URL`；非空 `.env` 值仅覆盖当前 Python 进程。
- 未设置 `ARK_BASE_URL` 时使用 `https://ark.cn-beijing.volces.com/api/v3`；仅 localhost、`127.0.0.1`、`::1` 可使用 HTTP。
- 基础地址不得含认证信息、查询参数或片段。诊断只能显示配置来源（`skill-local .env`、`process environment`、`default`、`unset`），不能显示值。
- 请求为 `POST <ARK_BASE_URL>/images/generations`，使用 `Authorization: Bearer <ARK_API_KEY>` 和 JSON payload。
- 不要要求用户在聊天中粘贴密钥；请其在本机 `.env` 或环境变量中配置。

## 命令与模型路由

| 命令 | 用途 | 必要条件 |
|---|---|---|
| `generate` | 文生图、参考图生图、多图融合、Lite 组图 | `--prompt` 或 `--prompt-file` |
| `edit` | 基于现有图片的编辑或标记编辑 | 至少一个 `--image` |

- `--prompt` 与 UTF-8 `--prompt-file` 只能二选一；多行、含引号或逐字文字优先后者。
- `pro` 或精确 Pro Model ID 路由 Pro；`lite`、Lite Model ID、空值或未知值路由 Lite。未知值只产生警告，绝不进入 API payload。
- 仅按用户选择传入 `--model pro` 或 `--model lite`；模型能力冲突由本地校验报错，不静默切换。

## 参数与模式规则

通用参数：`--image`（可重复）、`--size`、`--seed`、`--guidance-scale`、`--output-format`、`--response-format`、`--watermark`/`--no-watermark`、`--out`、`--force`、`--timeout`、`--dry-run`。

`--cleanup-prompt-file` 仅可与 `--prompt-file` 使用：真实请求成功并完成保存后删除该文件；失败、超时或 `ambiguous` 状态保留文件以便诊断。只对 agent 自己在 `tmp/seedream/` 创建的 prompt 文件使用，绝不对用户提供的文件使用。

- 默认：Lite、2K、PNG、`url`、无水印、单图、非流式、不开联网、`--timeout 300`。`--watermark` 发送 JSON 布尔值 `true` 以启用水印，`--no-watermark` 发送 `false`；两者不影响文件命名或保存路径。
- `seed` 必须是 int32；`guidance_scale` 必须为有限的 `[1,10]` 数值。尺寸和功能组合由所选模型本地验证。
- Lite 单图发送 `sequential_image_generation="disabled"`；组图使用 `--sequential auto --max-images N`，可选 `--out-dir DIRECTORY`。
- 组图不能使用 `--out`；单图不能使用 `--out-dir` 或 `--max-images`。Pro 拒绝组图、`--stream`、`--web-search`。
- `--web-search` 仅 Lite；`--stream` 仅 Lite。二者不是普通生成的默认项。

## 输入、输出与保存

- `--image` 接受本地路径、公开 HTTP(S) URL 或 `data:image/<小写格式>;base64,...`。支持 jpeg、png、webp、bmp、tiff、gif、heic、heif。
- 每张输入图不超过 30 MB，宽高均大于 14 px，总像素不超过 36,000,000，宽高比在 `[1/16,16]`。脚本校验真实格式；HEIC/HEIF 才需 `pillow-heif`。
- 未传 `--out` 时，单图保存至运行 Claude Code 的当前项目根目录；文件名由 prompt 生成，清理 Windows 非法字符并最多保留 64 个字符。例如 `"极简陶瓷杯商品摄影"` 保存为 `极简陶瓷杯商品摄影.png`。
- 组图未传 `--out-dir` 时保存至当前项目 `images/`；文件名为 `<提示词>-01.png`、`<提示词>-02.png`……。显式 `--out-dir` 时仍使用 `image-01.ext`、`image-02.ext`……。
- 默认文件名或默认组图冲突时，自动追加 `-v2`、`-v3` 等版本名，不覆盖已有图片。显式 `--out` 用于单图，`--out-dir` 用于组图。
- 输出扩展名必须匹配 `--output-format`；默认 PNG，只有明确需要 JPEG 时使用 `.jpg`/`.jpeg` 与 `--output-format jpeg`。
- 显式 `--out` 或显式 `--out-dir` 的组图计划目标已存在时不会覆盖；仅获得明确授权才使用 `--force`。`--force` 只覆盖本次计划目标，不清理 `--out-dir` 的其他文件；默认自动命名不需要 `--force`。脚本以原子写入落盘并验证真实图片格式和尺寸。

## Dry-run、计费与恢复

`--dry-run` 只做本地校验，输出脱敏 payload、计划路径、配置来源和 preflight 诊断；不会调用 Ark 或计费。以下情况必须先预检：组图、stream、web_search、多参考图、自定义尺寸、未知模型 fallback、目标已存在或准备使用 `--force`。

- 单图状态文件为 `.<输出文件名>.seedream-request.json`。显式 `--out-dir` 的组图状态文件为 `<out-dir>/.seedream-request.json`；默认组图在 `images/` 内按提示词摘要使用独立状态文件，互不阻塞。
- 状态仅保存 payload hash、目标、时间、PID 和状态，不保存 prompt、图片、密钥或 URL。
- 成功及明确 HTTP 失败后删除状态；超时、中断、断流、响应异常或保存不确定时标记 `ambiguous`。
- 发现 `pending` 或 `ambiguous` 必须停止，先核实输出与计费；不得自动重试或删除状态文件来绕过保护。
- 流式模式只保存 `partial_succeeded` 最终图；`partial_image` 是预览。缺少 `completed` 事件时视为不确定。
- 成功后，CLI 会删除请求状态、原子写入临时文件和显式标记清理的 prompt 文件。不要删除最终图片、用户提供的输入图/提示词文件，或 `pending`/`ambiguous` 状态文件；后两者是计费与恢复证据。

## 典型命令

Pro 标记编辑：

```powershell
python <SKILL_DIR>\scripts\image_gen.py edit --model pro `
  --image C:\input\marked.png --prompt-file C:\input\edit-prompt.txt `
  --out output\seedream\edited.png --dry-run
```

Lite 组图：

```powershell
python <SKILL_DIR>\scripts\image_gen.py generate --model lite `
  --prompt-file C:\input\series.txt --size 4K `
  --sequential auto --max-images 4 --out-dir output\seedream\series --dry-run
```

Lite 联网流式单图：

```powershell
python <SKILL_DIR>\scripts\image_gen.py generate --model lite `
  --prompt "制作上海未来5日天气图" --web-search --stream `
  --out output\seedream\weather.png --dry-run
```
