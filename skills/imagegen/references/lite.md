# Seedream 5.0 Lite 规范

作用：选择 Lite 后，提供唯一的模型能力、API payload、尺寸、组图、联网和 SSE 约束。CLI 调用方式见 `cli.md`；不要同时读取 Pro 规范。

## 目录

- [固定能力](#固定能力)
- [输出尺寸](#输出尺寸)
- [Payload](#payload)
- [组图](#组图)
- [联网搜索](#联网搜索)
- [流式事件](#流式事件)
- [输入与响应](#输入与响应)

## 固定能力

- 默认 Payload Model ID：`doubao-seedream-5-0-260128`；可用 `ARK_LITE_MODEL` 覆盖，但不改变本页能力校验。
- CLI 兼容别名：`doubao-seedream-5-0-lite-260128`；发送前统一为首选 ID。
- 支持文生图、单/多图编辑和融合、组图、联网搜索、流式输出。
- 最多 14 张参考图；参考图数量 + 计划输出数量不超过 15。
- 支持 2K、3K、4K 或合法自定义尺寸；不支持 1K。
- API 端点为 `POST <ARK_BASE_URL>/images/generations`；请求和响应由 bundled `scripts/image_gen.py` CLI 处理，不要自行拼装第二套客户端。

## 输出尺寸

- 自定义总像素：3,686,400–16,777,216。
- 宽高比：`[1/16,16]`。

| 比例 | 2K | 3K | 4K |
|---|---:|---:|---:|
| 1:1 | 2048×2048 | 3072×3072 | 4096×4096 |
| 4:3 | 2304×1728 | 3456×2592 | 4704×3520 |
| 3:4 | 1728×2304 | 2592×3456 | 3520×4704 |
| 16:9 | 2848×1600 | 4096×2304 | 5504×3040 |
| 9:16 | 1600×2848 | 2304×4096 | 3040×5504 |
| 3:2 | 2496×1664 | 3744×2496 | 4992×3328 |
| 2:3 | 1664×2496 | 2496×3744 | 3328×4992 |
| 21:9 | 3136×1344 | 4704×2016 | 6240×2656 |

## Payload

通用字段：`model`、`prompt`、`image`、`size`、`response_format`、`output_format`、`watermark`。单图时 `image` 为字符串，多图时为按顺序传入的数组；prompt 必须说明图一、图二的角色。CLI 不发送 Seedream 5 不支持的 `seed` 或 `guidance_scale`。

单图显式发送 `"sequential_image_generation":"disabled"`。默认 `output_format` 为 PNG；单图可用 `url` 或 `b64_json`，非流式组图仅可用 `url`。不要发送 Pro 专属或未被脚本支持的字段。

## 组图

```json
{
  "sequential_image_generation": "auto",
  "sequential_image_generation_options": {"max_images": 3}
}
```

`1 <= max_images <= 15 - 参考图数量`。非流式响应可返回 1 到 `max_images` 张最终图片。

## 联网搜索

用户或 prompt 明确要求联网时发送 `{"tools":[{"type":"web_search"}]}`；未明确要求但任务明显依赖最新事实时也可按需发送。模型自行决定是否实际搜索，实际次数见 `usage.tool_usage.web_search`。搜索用于时效事实核实；仍须在成图后检查标题、日期、数字和文字，不能将模型搜索视为内容正确性的证明。单独使用 `--web-search` 不强制要求 dry-run。

## 流式事件

发送 `"stream":true` 并解析 SSE：

- `image_generation.partial_image`：预览，不保存。
- `image_generation.partial_succeeded`：最终图片，立即验证并原子保存。
- `image_generation.partial_failed`：记录安全错误并按错误码处理。
- `image_generation.completed`：完成并读取 usage。

断流、缺少 `completed` 或保存不确定时保留已完成图片，将状态标为 `ambiguous`，不得自动重试。预览 `partial_image` 不得作为交付文件。

## 输入与响应

通用输入格式、文件大小、尺寸、Base64/URL 和保存规则见 `cli.md`。Lite 单图响应必须恰好一项，组图不得超过计划上限；URL 仅保留 24 小时，必须立即下载并校验。输出或响应不确定时保留请求状态，停止而非重试。

官方依据：[Seedream 4.0-5.0 教程](https://docs.volcengine.com/docs/82379/1824121?lang=zh)与[图片生成 API](https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01)，复核日期 2026-07-14。Model ID、14 张输入和部分精确上限在当前公开页面中缺少可直接逐项定位的静态正文，属于可追溯性缺口；修改这些高风险常量前必须重新核对官方控制台/API 说明。
