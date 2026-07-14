# Seedream 5.0 Pro 规范

作用：选择 Pro 后，提供唯一的模型能力、API payload、尺寸和输入/响应约束。CLI 调用方式见 `cli.md`；不要同时读取 Lite 规范。

## 固定能力

- 默认 Model ID：`doubao-seedream-5-0-pro-260628`；可用 `ARK_PRO_MODEL` 覆盖 payload Model ID，但不改变本页能力校验。
- 支持文生图、单图编辑、多图融合和坐标点、圈选、涂鸦、草图等标记交互编辑。
- 仅单图输出；最多 10 张参考图。
- 支持 1K、2K 或合法自定义尺寸；不支持 3K/4K。
- 不支持组图、`stream` 或模型原生 `web_search`。
- API 端点为 `POST <ARK_BASE_URL>/images/generations`；请求和响应由 bundled `scripts/image_gen.py` CLI 处理，不要自行拼装第二套客户端。

## 输出尺寸

- 自定义总像素：921,600–4,624,220。
- 宽高比：`[1/16,16]`。
- 档位模式在 prompt 描述比例或用途，由模型映射尺寸。

| 比例 | 1K | 2K |
|---|---:|---:|
| 1:1 | 1024×1024 | 2048×2048 |
| 4:3 | 1152×864 | 2368×1776 |
| 3:4 | 864×1152 | 1776×2368 |
| 16:9 | 1424×800 | 2816×1584 |
| 9:16 | 800×1424 | 1584×2816 |
| 3:2 | 1248×832 | 2496×1664 |
| 2:3 | 832×1248 | 1664×2496 |
| 21:9 | 1568×672 | 3136×1344 |

## Payload 约束

通用字段：`model`、`prompt`、`image`、`size`、`seed`、`guidance_scale`、`response_format`、`output_format`、`watermark`。单图时 `image` 为字符串，多图时为按顺序传入的数组；prompt 必须标明图一、图二的角色及编辑不变项。

默认 `output_format` 为 PNG；`response_format` 为 `url` 或 `b64_json`。不得出现 `sequential_image_generation`、`sequential_image_generation_options`、`stream` 或 `tools`。最新事实由 Claude 外部检索后写入 prompt，不得声称 Pro 原生联网。

## 输入与响应

- 输入格式：jpeg、png、webp、bmp、tiff、gif、heic、heif。
- 单张不超过 30,000,000 字节；宽高均大于 14 px；总像素不超过 36,000,000；比例 `[1/16,16]`。
- Base64 使用 `data:image/<小写格式>;base64,<数据>`；远程 URL 必须可访问。
- 响应必须恰好一张图；`response_format` 支持 `url`/`b64_json`，`output_format` 支持 png/jpeg，默认 PNG。
- URL 仅保留 24 小时，应立即保存并验证真实格式、尺寸与输出数量。超时、中断、响应或保存不确定时保留请求状态，停止而非自动重试。

官方依据：[Seedream 4.0-5.0 教程](https://docs.volcengine.com/docs/82379/1824121?lang=zh)与[图片生成 API](https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01)，复核日期 2026-07-14。Pro Model ID、10 张输入、精确尺寸和交互能力边界在当前公开页面中缺少可直接逐项定位的静态正文，属于可追溯性缺口；修改这些高风险常量前必须重新核对官方控制台/API 说明。
