# 能力来源清单

此文件是 Lite/Pro 本地约束的发布复核入口，不是运行时网络依赖。最后复核：2026-07-18。

| 范围 | 官方来源 | 本地执行策略 |
|---|---|---|
| Seedream 5 指南 | https://docs.volcengine.com/docs/82379/1829186?lang=zh | Lite/Pro 能力差异以 `lite.md`、`pro.md` 为准；改动前需核对官方页。 |
| ImageGenerations API | https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01 | payload 字段、响应与错误处理变更前需复核。 |

发布前要求：记录复核日期和 URL；为每个新增/移除字段、尺寸限制或模型能力补充 CLI 校验与单元测试。官方文档存在冲突或不可定位时，采用更保守的本地限制，并在 release note 中说明。
