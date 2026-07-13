# Seedream Imagegen

![Seedream Imagegen](assets/imagegen.png)

面向 Claude Code 的 Doubao Seedream 5.0 Lite / Pro 生图 skill，通过火山方舟 Ark 生成和编辑位图。项目提供经过校验的 CLI、模型能力检查、免费预检、参考图工作流、Lite 组图以及可选的色键转透明处理。

英文文档：[README.md](README.md)

## 功能

- `generate`：文生图、参考图生图、多图融合和 Lite 组图。
- `edit`：在保留其他内容的前提下编辑现有图片。
- 严格校验 Lite/Pro 能力，不会静默替换用户选择的模型。
- 使用 `--dry-run` 查看脱敏请求预检，不提交也不计费。
- 防止输出覆盖，保留请求状态并提供失败恢复规则。
- `remove_chroma_key.py`：将简单的均匀色键背景转换为 alpha 透明。

## 先置条件

- 已安装支持 skill 的 Claude Code。
- Python 3.10+ 与 `pip`。
- 火山方舟账号、可访问 Seedream 5.0 Lite 或 Pro 的 Ark API Key。
- 能访问 Ark API 地址的网络环境。

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

## 安装 skill

推荐使用专门的 skill 安装方式：

```powershell
npx skills add YFan945/Seedream-Imagegen
```

如果当前 `skills` CLI 需要显式全局安装：

```powershell
npx skills add YFan945/Seedream-Imagegen -g
```

其他下载方式：

- ZIP：[下载 main 分支 ZIP](https://github.com/YFan945/Seedream-Imagegen/archive/refs/heads/main.zip)，解压到 Claude Code skills 目录。
- `npx`：`npx degit YFan945/Seedream-Imagegen ~/.claude/skills/imagegen`。
- Git：`git clone https://github.com/YFan945/Seedream-Imagegen.git ~/.claude/skills/imagegen`。

这里的 `npx` 用于下载/引导安装；本项目是 Python skill，不是 npm 生图运行时。

## 配置

在 skill 目录复制 `.env.example` 为 `.env`，填写：

```dotenv
ARK_API_KEY=你的_ark_api_key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

也可以只在当前进程环境变量中设置。CLI 不会修改 Windows 全局环境。不要提交 `.env`，不要在 prompt 或日志中暴露 API Key。

## 使用

先执行免费预检：

```powershell
python scripts\image_gen.py generate --model lite --prompt "一只坐在窗边的橘猫，柔和晨光" --out output\cat.png --dry-run
```

确认参数后再执行真实请求：

```powershell
python scripts\image_gen.py generate --model lite --prompt "一只坐在窗边的橘猫，柔和晨光" --out output\cat.png
```

编辑现有图片：

```powershell
python scripts\image_gen.py edit --model pro --image input\photo.png --prompt "只把背景改成深蓝色；保持人物、姿态和光线不变" --out output\edited.png --dry-run
```

详细的模型限制、提示词、参考图、组图和状态恢复规则见 [SKILL.md](SKILL.md) 及 [`references/`](references/)。

生图请求可能产生费用。每次真实请求前确认模型、prompt、参数和输出路径；遇到 `pending` 或 `ambiguous` 状态必须停止，不要自动重试。

## 开发测试

```powershell
python -m pytest -q
```

测试不会调用真实 Ark API。仓库协作规则见 [AGENTS.md](AGENTS.md)。

## 许可证

见 [LICENSE.txt](LICENSE.txt)。
