# Seedream Imagegen 缺陷审计与修改计划

> 审计日期：2026-07-14
> 审计对象：本仓库 `imagegen` skill；参考实现路径为 `C:\Users\28603\.codex\skills\.system\imagegen`，仅对照算法与说明
> 审计性质：只读代码、文档、测试和本地非计费验证；未发起真实 Ark 请求
> 行号基于审计时工作区，后续修改后可能变化

## 1. 执行结论

本项目已经具备一套相当扎实的主 CLI 安全骨架：模型能力分支、输入格式/尺寸检查、输出冲突检查、请求状态文件、响应图片验证、原子保存、脱敏和 mock 测试均已存在。它不是需要推倒重写的项目。

本项目按轻型 Claude Code skill 定位实施：修复重点是请求安全、路径可靠、色键算法正确和文档可执行。生成完成后的图片保留一次轻量底线检查，但不建设复杂质量评分、多轮审图、自动美学评价或重型 QA 流程。

但当前版本不建议按现有文档直接发布为“可靠的透明背景工作流”，也不建议在修复请求状态判定前鼓励无人值守的真实生成。共有 5 项发布阻断问题：

1. `soft matte` 对白色/浅色抗锯齿边缘的 alpha 估计在数学上错误，会把边缘整段删除，并在相邻输入值之间从 0 跳到 255。
2. `despill` 会修改 fully opaque 主体颜色；实测 `(20,220,20,255)` 被改成 `(20,20,20,255)`。
3. `edge feather` 会把透明黑重新扩散为可见黑边，并破坏输入已有 alpha。
4. 主 CLI 把所有 `HTTPError` 都判为 `ambiguous=False`，随后删除请求状态；对于 408、5xx 或未有“请求一定未执行”证据的错误，这会留下重复付费重试风险。
5. skill 的标准命令使用 `scripts/...` 项目相对路径；Claude 从用户项目运行时会寻找用户项目中的脚本，而不是已安装 skill 中的脚本。

当前色键脚本只可认为对“完全平坦、颜色精确、实心轮廓、hard key、无需 feather/despill”的简单图形有基础可用性。文档当前推荐的组合：

```powershell
--auto-key border --soft-matte --despill
```

恰好会同时触发三个核心缺陷。在核心算法修复前，应暂时停止把这组参数作为默认方案。

## 2. 审计范围、方法与限制

本次覆盖：

- `scripts/remove_chroma_key.py` 的 matte、despill、alpha、auto-key、I/O、原子写入和性能。
- `scripts/image_gen.py` 的配置读取、模型/尺寸校验、输入编码、请求状态、错误分类、输出保存和资源上限。
- `SKILL.md`、两个 README、`references/`、测试、依赖、忽略规则和 assets。
- 仅参考另一 `imagegen` 的色键脚本、透明背景提示词和 bundled script 路径；其平台专属 metadata、图标规范和产品特性不在范围内。
- Claude Code skill 发现规则、`npx skills` 安装语义及火山方舟公开资料的交叉检查。

已执行的非计费验证：

- `python -m pytest -q`：`69 passed, 57 subtests passed`。
- `python -m compileall -q scripts tests`：通过。
- `git diff --check`：审计前通过。
- 仓库内 Markdown 相对链接扫描：未发现失效链接。
- 色键合成像素真值、auto-key 多峰、alpha feather、EXIF、动画、HEIC 和性能复现。
- 从仓库外 CWD 运行文档中的相对脚本路径和 dry-run 路径规划。
- 检查 assets 的像素尺寸、颜色模式、alpha、非白内容边界和引用位置。

限制：

- 未调用真实 Ark API，因此服务端计费时点、具体错误码计费语义和 Pro 的未公开行为不能由本地审计最终证明。
- 本次能公开检索到的官方资料没有直接、清晰地列出所有 Pro model ID 和每项限制。本文将其记为“来源可追溯性缺口”，不据此断言 Pro 模型或本地配置无效。
- 性能数字只用于同机基线，不应直接作为其他硬件的绝对 SLA。

## 3. 优先级定义与缺陷总表

- **P0 / 阻断**：可造成错误交付、主体损坏、重复计费风险，或使标准 skill 调用在常规场景直接失败；发布前必须修复或明确禁用。
- **P1 / 高**：常见输入下高概率误判、资源失控、失败后不可恢复或安装不可用；应在下一版本完成。
- **P2 / 中**：边界条件、文档漂移、诊断不足或条件性平台问题；应进入后续版本。
- **P3 / 低**：维护性和展示优化问题。

| ID | 优先级 | 缺陷 | 主要位置 | 处理结论 |
|---|---|---|---|---|
| CK-01 | P0 | soft matte 对浅色边缘的 alpha 数学错误且不连续 | `remove_chroma_key.py:99-124,159-165` | 重做 matte，不调阈值凑结果 |
| CK-02 | P0 | despill 修改 fully opaque 主体 | `remove_chroma_key.py:127-136,175-177` | 改为 alpha/confidence-aware，opaque 默认不动 |
| CK-03 | P0 | feather 产生黑边并复活 source alpha=0 | `remove_chroma_key.py:167-192,285` | 分离 source alpha 与 chroma matte |
| API-01 | P0 | 所有 HTTP 错误都删除付费请求状态 | `image_gen.py:764-780,1113-1118` | 仅明确“提交前拒绝”的白名单可清理 |
| RUN-01 | P0 | bundled script 使用错误相对路径 | `SKILL.md:8,108`、`prompting.md:72` | 使用 `${CLAUDE_SKILL_DIR}` 绝对路径 |
| CK-04 | P1 | auto-key 可合成图片中不存在的颜色且无置信度 | `remove_chroma_key.py:195-229,275-293` | dominant cluster + 多峰/均匀度拒绝 |
| CK-05 | P1 | 2K/4K 逐像素 Python 处理过慢 | `remove_chroma_key.py:149-177` | Pillow band/mask C 层运算，基准门禁 |
| CK-06 | P1 | EXIF 未转正、动画静默丢帧、HEIC 行为与依赖不一致 | `remove_chroma_key.py:28-33,268-273` | 明确静态契约并补格式处理 |
| CK-07 | P1 | 无显式像素上限，未捕获 decompression bomb | 同上 | 复用统一图片安全上限 |
| FLOW-01 | P1 | “项目根目录”与实际进程 CWD 矛盾 | `image_gen.py:40-41,493-515`、`SKILL.md:60` | skill 总是传项目绝对输出路径 |
| FLOW-02 | P1 | 临时文件与最终交付物所有权未划清 | `SKILL.md:55-67` | 采用“agent 临时 / 用户交付”两态规则 |
| CFG-01 | P1 | import 时读取真实 `.env` 并修改 `os.environ` | `image_gen.py:136-167` | 改为 main/run 内惰性加载和依赖注入 |
| SAFE-01 | P1 | `--cleanup-prompt-file` 可删除任意调用方路径 | `image_gen.py:733-740` | 限定 agent-owned 临时根、普通文件和路径不冲突 |
| SIZE-01 | P1 | 档位输出只按整个模型范围验收 | `image_gen.py:907-936` | 按 1K/2K/3K/4K 分档校验 |
| MEM-01 | P1 | 多张 30 MB 输入形成超大 Base64/JSON 多份拷贝 | `image_gen.py:314-333,437-462,653-655,748-755` | 增加 aggregate payload 上限并减少复制 |
| PATH-01 | P1 | 精确目标文件名未在计费前完整验证 | `image_gen.py:483-490,593-603` | 检查 Windows 保留名、长度和 exact target |
| INSTALL-01 | P1 | 安装 scope、agent、CWD 顺序说明错误 | 两个 README `:31-55,70-88` | 重写 global/project 与 Claude-only 安装流程 |
| SAFE-02 | P1 | 错误与 dry-run 没有统一递归脱敏 | `image_gen.py:280-324,465-475,616-645,1028,1073-1084` | 所有用户可见结构统一 scrub |
| LEGAL-01 | P1 | README 标注 MIT，实际 LICENSE 是 Apache-2.0 | 两个 README `:8`、`LICENSE.txt:1-3` | 立即修正公开许可证元数据 |
| CK-08 | P2 | 输入合法低 alpha 被 noise floor 删除 | `remove_chroma_key.py:19,167-171` | noise floor 只作用于新 matte |
| CK-09 | P2 | matched 统计实际是最终透明像素数 | `remove_chroma_key.py:149-179,276-293` | 返回分项统计 |
| CK-10 | P2 | 任意 RGB key 的 CLI 承诺超出算法能力 | `remove_chroma_key.py:36-41,92-136` | 限制高饱和键色或改通用色度模型 |
| CK-11 | P2 | 全图删色会在主体内部打孔 | `remove_chroma_key.py:152-177` | 可选 border-connected 背景约束 |
| CK-12 | P2 | no-clobber 存在 TOCTOU，允许 input=output | `remove_chroma_key.py:58-68,249-261` | samefile 拒绝和真正原子 no-clobber |
| CK-13 | P2 | 编码/写入错误未经受控中文处理 | `remove_chroma_key.py:264-293` | 捕获错误并保持旧输出 |
| CK-14 | P2 | 输出缺少必要的底线校验 | 同上 | 重开验证、alpha 存在性和全空/全满检查 |
| DOC-01 | P2 | 透明 prompt 缺少可分割条件且模板自相矛盾 | `SKILL.md:103-110`、prompt refs | 单一事实源和条件化模板 |
| DOC-02 | P2 | 模型/CLI/prompt 事实重复并已漂移 | `SKILL.md` 与 `references/` | 明确 SSOT，SKILL 只负责路由 |
| DOC-03 | P2 | 普通视觉标记与 Pro 精准交互边界含混 | `SKILL.md:25`、README 模型表 | 拆分 Lite 普通标记与 Pro 精准交互 |
| DOC-04 | P2 | Pro model ID/限制缺直接可追溯官方源 | `references/pro.md` | 每项高风险事实绑定直接来源和复核日 |
| MODEL-01 | P2 | 未知 `--model` 值自动回退 Lite，可能掩盖拼写错误 | `image_gen.py:199-210` | 默认拒绝；兼容回退需显式开关 |
| PRIV-01 | P2 | prompt 前 64 字进入输出与状态文件名 | `image_gen.py:483-523` | 提供隐私安全命名模式并修正文档措辞 |
| REL-01 | P2 | 无 CI 却展示静态 `validate-passing` 徽章 | 两个 README `:7` | 添加真实 workflow 或删除徽章 |
| DEV-01 | P2 | README 要求 pytest，但运行依赖未声明 pytest | `requirements.txt`、README Development | 增加 dev extra/requirements |
| IO-02 | P2 | 原子写入被中断时可能残留临时文件 | `image_gen.py:939-957` | `finally` 清理并覆盖中断测试 |
| DRY-01 | P2 | 单图 dry-run 把真实字符串 payload 显示成数组 | `image_gen.py:447-475` | 保持真实 payload 形状，只替换值 |
| TIME-01 | P2 | `--timeout` 是单次 socket timeout，不是总 deadline | `image_gen.py:764-903` | 改名说明或实现单调时钟总 deadline |
| DOC-06 | P2 | references 把 `image` 一律写成数组，代码单图为字符串 | `lite.md:42`、`pro.md:33` | 文档改为单图字符串、多图数组 |
| ASSET-01 | P3 | README wordmark 白边和文件体积偏大 | `assets/seedream-imagegen-logo.png` | 可选裁切、压缩和语义化改名 |
| DOC-05 | P3 | 中英文 README 内容结构漂移 | 两个 README | 结构对齐或自动检查 |
| TEST-01 | P3 | 缺 frontmatter、链接、路径、安装契约测试 | `tests/` | 增加 docs contract tests |

## 4. `remove_chroma_key.py` 详细审计

### 4.1 当前实现做得好的部分

相对所给参考实现，本项目已有以下改进，应保留：

- `:44-56` 对 NaN/Inf 和范围做有限数值校验；参考实现的普通比较可能让 NaN 漏过。
- 输入使用 `is_file()`，输出目录冲突有检查。
- auto-key 忽略 fully transparent 像素的隐藏 RGB。
- WebP 使用 `lossless=True`，不会因默认有损编码进一步污染边缘。
- 同目录临时文件、file `fsync`、`os.replace` 比直接写目标更安全。
- `_is_key_edge` 增加距离上限，能保护一部分明显远离键色的主体绿色。

参考实现不能作为修复替代品：它与本项目共享 soft matte、auto-key、feather、EXIF、动画和性能问题。其文档把 `opaque_threshold` 提高到 220 也不能修复公式本身。

### 4.2 CK-01：soft matte 公式错误

核心代码：

```python
denominator = max(1.0, max(key) - other_strength)
return clamp(255 * (1 - dominance / denominator))
```

对白色前景以覆盖率 `a` 合成在纯绿背景上的像素：

```text
C = (a*255, 255, a*255)
dominance = 255 - a*255
denominator = 255 - a*255
```

所以在该分支中 `dominance / denominator` 恒为 1，alpha 被算成 0。实测：

```text
(64,255,64)   -> alpha 0，期望约 64
(128,255,128) -> alpha 255，期望约 128

(95,255,95) -> 0
(96,255,96) -> 0
(97,255,97) -> 255
```

最后三行表明只改变一个通道值，alpha 就从 0 跳至 255。原因不只在阈值，而在动态分母和 `_is_key_edge`/hard 分支切换共同造成的不连续。

修改原则：

1. 先建立合成真值测试，再选算法；不得先改 `opaque_threshold`。
2. 将 key 本身的色度优势作为稳定参考，或使用经过验证的 chroma vector/foreground estimation；不得让分母随当前像素的前景通道一起塌缩。
3. 保证透明阈值、过渡区和 opaque 区域连续、单调。
4. 对 partial alpha 做背景反混合以恢复边缘 RGB；despill 只作为保守补偿。
5. 至少覆盖 green、magenta、blue、cyan，以及黑/白/灰/红/蓝主体。

### 4.3 CK-02：despill 破坏不透明主体

`_despill()` 把所有 spill 通道直接压到其他通道最大值，既不读取 alpha，也不按污染置信度混合。实测：

```text
(20,220,20,255) -> (20,20,20,255)
```

现有 `tests/test_remove_chroma_key.py:15-30` 只断言绿色值下降，实际把错误行为固化成测试。参考实现虽跳过 `alpha >= 252`，但仍会在 251/252 形成突变，不应照搬。

修改原则：

- `alpha == 255` 默认保持原 RGB。
- despill 强度随透明度和 key-spill confidence 连续变化。
- 优先通过反混合恢复 foreground RGB；despill 是边缘补偿而不是主体重着色。
- 对无明确色度方向的灰/白/黑 key 禁用 despill 或明确失败。

### 4.4 CK-03：feather 造成黑边并破坏 source alpha

当前代码先把透明像素写成 `(0,0,0,0)`，再对最终组合 alpha 做对称 `GaussianBlur`。因此 alpha 会扩散回透明黑，而 RGB 仍为黑色。

3×1 实测：

```text
输入： (0,0,0,0), (255,0,0,255), (0,0,0,0)
输出： (0,0,0,74), (255,0,0,106), (0,0,0,74)
```

这同时制造黑色光晕、削弱主体中心，并让原本 source alpha=0 的位置重新可见。`edge-contract` 同样直接侵蚀原始 alpha 结构。

正确的数据流应至少分开：

```text
source_rgb
source_alpha
raw_chroma_matte
processed_chroma_matte
final_alpha = source_alpha * processed_chroma_matte / 255
```

contract/feather 只处理 chroma matte；`source_alpha == 0` 不得被复活。若允许向外扩张，必须先进行 foreground color propagation 或在 premultiplied RGBA 中正确处理，不能给透明黑增加 alpha。

### 4.5 CK-04：auto-key 无可靠性判定

当前每个 RGB 通道独立取 median。绿/洋红各占一半的边框会得到从未出现在图片中的灰色：

```text
(0,255,0) + (255,0,255) 的多峰边框 -> (128,128,128)
```

脚本仍继续写输出，只在事后 warning。小图的 corner patch 还可能覆盖大部分画面并采到主体；多色边框、阴影、渐变、JPEG 噪点和主体触边均无置信度判断。

修改方案：

- 从真实样本中选择 dominant cluster，不逐通道合成颜色。
- 统计 dominant share、cluster 半径/MAD、四角共识和离群点。
- 多峰、渐变、各角不一致或 key 饱和度不适配时，在写文件前失败，要求显式 `--key-color`。
- 限制采样数量，四角独立估计后再求共识。
- 处理前验证背景采样置信度；输出全空或全满时给出明确失败/警告。

### 4.6 CK-05～CK-14：其他实现问题

性能：soft matte + despill 的同机基线约为：

```text
512×512   约 1.0 s
1024×1024 约 4.1 s
2048×2048 约 17.4 s
吞吐约 0.24 MP/s
```

按像素线性外推，4K 可接近 70 秒。应预计算 key 通道信息，并优先使用 Pillow 的 band、`ImageChops`、LUT、mask/composite 等 C 层运算；仅在确有必要时引入可选 NumPy。轻型项目只把代表性的 2K 基准作为回归门禁，4K 基准保留为手工、非阻断检查。

I/O 与安全：

- 使用 `ImageOps.exif_transpose()` 后再转 RGBA。
- 明确只支持静态图片；`n_frames > 1` 应失败，不能静默输出首帧。
- 要么注册 `pillow-heif` 并测试 HEIC/HEIF，要么从本工具支持列表中明确排除。
- 明确 16-bit/HDR、ICC、EXIF、DPI 的保留/降级规则。
- 设置像素和编码尺寸上限，捕获 `DecompressionBombError` 并输出受控中文错误。
- `ALPHA_NOISE_FLOOR` 只作用于新 matte，不能删除输入本身 alpha 1～8。
- 分别统计 key match、source transparent、final transparent、partial，不得把最终透明数命名为 `matched`。
- hard/soft/despill 若只支持高饱和色度键，应在参数校验中明确限制。
- 增加 border-connected 模式或孔洞风险检测，避免删除主体内部孤立键色。
- 拒绝 input/output 同路径；非 `--force` 使用真正的原子 no-clobber。
- 编码、磁盘满、权限、路径过长等错误应保持旧输出并给出中文错误。

## 5. 透明背景 Prompt 与调用说明

### 5.1 当前问题

1. `SKILL.md:107` 与 `prompting.md:67-68` 只强调均匀背景，缺少主体与四边完全分离、足够 padding、不可裁切/触边、清晰 silhouette、无 contact/cast shadow、无 key-colored rim light/glow/bounce/motion blur。
2. “绿色主体改用洋红”过于简单。应检查主体整个色相族，而非 exact hex；若主体同时含多种候选键色、半透明或强反光，应停止简单色键方案。
3. `sample-prompts.md:217` 要求保留标签文字，`:218` 又无条件禁止文字和 Logo，无法同时满足。
4. “禁止反射”会误伤玻璃/金属的固有材质高光；真正应禁止的是背景/地面反射和键色污染。
5. `edge-contract` 与 `edge-feather` 被作为白边/锯齿的并列修复，但 feather 不是白边清除工具，当前实现还会制造黑边。
6. `border` auto-key 的前提、失败条件和不确定时停止规则未写明。
7. 现有检查方向正确，但应整理成一次轻量底线检查，不扩展为复杂评分或多轮审图流程。

### 5.2 建议的唯一模板

模板应只在 `references/sample-prompts.md` 保存完整版本，`SKILL.md` 只链接和说明适用边界：

```text
任务类型：background-extraction
核心请求：将[主体]完整、独立地置于纯色 [KEY_COLOR]（[HEX]）背景中央。
主体：轮廓完整、边缘清晰；与画布四边完全分离，保留充足 padding；不得裁切或触边。
场景/背景：整张画布为单一、完全均匀、无压缩噪点的 [KEY_COLOR]；无渐变、纹理、地面、背景物体或光照变化。
必须保持：[用户明确要求保留的材质、细节、标签文字或 Logo]；主体不得出现 [KEY_COLOR] 及其相邻色相族。
禁止：cast/contact shadow、地面反射、背景反射、key-colored rim light、glow、ambient bounce、motion blur、halo、fringing、水印和未要求的文字/Logo。
```

条件说明：

- 用户未要求保留标签/Logo 时，才禁止额外文字与 Logo。
- 允许主体固有的玻璃/金属材质高光，但这类对象通常不适合简单色键，应明确降级预期或改专业分割。
- 生成后把实际 `[HEX]` 显式传给 `--key-color`；只有 auto-key 置信度通过时才允许自动取色。
- 毛发、烟雾、液体、玻璃、薄纱、运动模糊、软阴影和半透明对象不是本脚本承诺范围。

### 5.3 轻量交付检查（非重点）

每个最终输出只做一次快速检查：

1. 文件可重新打开，格式、尺寸和 alpha 符合请求；结果不是全空或明显全不透明。
2. 在棋盘格或一个高对比底色上快速查看，确认没有明显孔洞、主体变色或严重黑边/key 色边。
3. 检查失败时报告问题并保留原图；不自动做多背景对比、像素级评分或连续付费重生成。

建议新增精简的 `references/chroma-key.md`，集中描述算法边界、参数、输入格式、source alpha、auto-key 前提、写入语义、失败恢复和上述三项检查。当前 `references/cli.md` 只负责主生图 CLI，不应继续兼任色键参考。

## 6. Assets 与参考实现对照

### 6.1 当前 asset 的实际调用

当前唯一 asset：

```text
assets/seedream-imagegen-logo.png
1774×887，RGB，无 alpha，723659 bytes
非白内容 bbox：(183,290)-(1642,576)
```

它只被以下两处引用：

- `README.md:4`
- `README-zh.md:4`

它没有被 `SKILL.md` 或脚本在运行时调用，本质上是 README wordmark。对于 Claude Code standalone skill，不存在“缺少运行时 asset 调用”的问题；实际问题仅是白边较多、文件偏大，非白内容包围区约占画布 26.5%。

建议：

- 可选裁掉白边、压缩并重命名为 `seedream-imagegen-wordmark.png`；这是低优先级展示优化，不影响 skill 功能。
- README 品牌图无需写进 SKILL 的 reference map，避免模型运行时无意义加载。

### 6.2 范围边界

参考项目的平台专属 metadata、图标和产品结构不属于本项目目标，不计为缺陷，也不进入修改计划。本项目只面向 Claude Code。

### 6.3 从参考实现吸收的内容

可借鉴：

- 使用 skill 安装目录调用 bundled script。
- 透明 prompt 中的 crisp silhouette、padding 和 no halo/fringing。

不可直接复制：

- 参考实现的色键 matte 公式与本项目共享核心错误。
- `opaque_threshold=220` 没有修复公式。
- 参考实现对 EXIF、动画、auto-key、feather 和性能也没有完整解法。

## 7. 主 CLI 与整体项目缺陷

### 7.1 API-01：HTTP 错误状态分类可能导致重复计费

`_api_response()` 在 `urllib.error.HTTPError` 上始终创建：

```python
ArkRequestError(..., ambiguous=False)
```

`run()` 随后对 `ambiguous=False` 删除 `.seedream-request.json`。本地 mock 验证 400、408、429、500、503 目前全部走相同的“明确失败”路径。

安全原则应是：只有有官方语义或响应码明确证明“请求在生成前被拒绝”的情况，才可删除状态。408、5xx、未知错误码以及响应语义不清晰的业务错误，应标记 `ambiguous` 并停止。建议实现集中式分类器：

```text
def classify_submission_outcome(http_status, ark_code) -> rejected | ambiguous
```

使用可审查的 allowlist，而不是“所有 HTTP 响应都未执行”的假设。测试需覆盖 HTTP 状态和 Ark 业务码组合，并断言状态文件是否保留。真实计费语义应以 Ark 官方说明或支持确认补齐。

### 7.2 CFG-01：import-time `.env` 副作用

`CONFIG_SOURCES = load_env()` 在模块 import 时读取 skill-local `.env` 并写入 `os.environ`。因此：

- `tests/test_image_gen.py:17` 一导入模块就读取开发者真实 `.env`，违反测试“不读取真实 `.env`”的仓库规则。
- 仅执行单元测试、导入辅助函数或 dry-run 也会读取秘密配置文件。
- 不可读 `.env` 会在 argparse/main 之前抛出异常。
- 测试结果受本机配置污染，难以隔离并行测试。

审计仅验证配置来源为 `skill-local .env`，未输出任何值。修改时应让 `load_config()` 在 `main()`/`run()` 内按需调用，返回不可变配置对象，不修改全局环境；API 函数接受显式 config。测试使用临时 `.env` 或注入配置，并全局阻断网络。

`.env.example` 当前非空占位值 `ARK_API_KEY="Your api key"` 会通过本地“非空”校验并产生误导性的认证请求。应改为空值并在 preflight 识别常见 placeholder。

### 7.3 SAFE-01：prompt 临时文件清理权限过宽

`--cleanup-prompt-file` 成功后直接 `unlink(Path(args.prompt_file))`。CLI 无法证明该路径由 agent 创建，也不验证：

- 是否位于项目 `tmp/seedream/`。
- 是否为普通文件、是否为 symlink。
- 是否与输入图、输出、状态文件或用户文件冲突。

文档虽然要求谨慎，CLI 没有执行该契约。应限定 project-root 下的专用临时目录，拒绝 symlink/reparse point 和路径冲突；更稳妥的方案是让 CLI 自己创建并管理 prompt 临时文件，而不是接收任意“成功后删除”的路径。

`SKILL.md:67` 对“色键处理的源图”也没有限定 ownership。只能删除 agent 明确创建并标记的工作副本；生成原图、用户输入和唯一结果均不得自动删除。

### 7.4 SIZE-01：档位输出验证过宽

用户请求 `2K`、`3K`、`4K` 时，`_validate_generated_image()` 只验证结果落在整个模型的 min/max pixel 范围。比如 Lite `4K` 请求返回一个落在 Lite 总范围内的 2K 结果，仍可能通过。

应建立按模型、档位、比例的允许尺寸或像素带：

- 自定义 `WIDTHxHEIGHT` 继续要求精确匹配。
- named tier 按 1K/2K/3K/4K 独立校验，而不是模型总包络。
- 允许的服务端轻微尺寸映射必须有官方依据和单测，不能任意放宽。

### 7.5 MEM-01：聚合输入内存无上限

Lite 最多 14 张参考图，每张本地允许 30 MB。理论上：

```text
原始 bytes：约 420 MB
Base64：约 560 MB
```

随后 payload、`json.dumps()` 请求体和 `_request_fingerprint()` 的 canonical JSON 还会产生大字符串/bytes 拷贝，峰值可能超过 1 GB。当前只有单图上限，没有 aggregate input、encoded payload 或 request-body 上限。

应在任何 Base64 编码前计算总预算，限制总本地输入和估算请求体；避免为 fingerprint 再序列化整份 Base64 payload，可对结构化字段和输入流式 hash。默认继续使用 URL 响应以降低响应内存。增加接近上限和超限的内存/行为测试。

### 7.6 PATH-01、FLOW-01：路径与输出生命周期

`prepare_output_destination()` 只在目标目录创建通用临时文件，不能证明具体目标名称可保存。Windows 的 `CON`、`PRN`、`AUX`、`NUL`、`COM1` 等保留 basename、尾随点/空格、路径长度问题可能在付费请求后才暴露。prompt 派生文件名只过滤非法字符，没有过滤这些名字。

应在 POST 前验证 exact target：

- portable basename 和 Windows reserved names。
- 路径长度、目标扩展名、父目录、symlink/reparse point 策略。
- 单图/组图所有目标均可提交。
- `--force` 的覆盖授权与真正原子 no-clobber。

此外，默认目录 `Path(".")` 和 `Path("images")` 只相对进程 CWD。`SKILL.md` 却称其为“当前项目根目录”。skill 调用应始终根据 `${CLAUDE_PROJECT_DIR}` 生成绝对 `--out`/`--out-dir`；若不使用该变量，文档必须准确称为“命令 CWD”，不能承诺项目根。

轻型项目只需要两态所有权：

```text
agent-owned temp -> user deliverable
```

只有 agent-owned temp 可自动清理；预览/候选在未被用户选为交付物前均按 temp 管理。交付物进入用户明确的项目路径，之后不得自动删除。

### 7.7 RUN-01、INSTALL-01：skill 调用和安装说明

Claude skill 中的 bundled script 应使用：

```text
${CLAUDE_SKILL_DIR}/scripts/image_gen.py
${CLAUDE_SKILL_DIR}/scripts/remove_chroma_key.py
```

而输入、临时 prompt 和最终输出使用 `${CLAUDE_PROJECT_DIR}`。需要为带空格路径和仓库外 CWD 增加测试。

README 安装问题：

- `npx skills add` 默认 scope 是 project，`-g` 是 global，不是“某些版本的兼容选项”。
- 未用 `-a claude-code` 锁定目标 agent；本项目应明确只安装到 Claude Code。
- 在 skill 安装前先执行相对 `requirements.txt`，CWD 不成立。
- 用法继续依赖仓库根的 `scripts/...`，没有区分开发者命令和已安装 skill 命令。
- ZIP 解压可能得到 `Seedream-Imagegen-main/`；Claude 命令发现依赖最终目录，必须保证 `~/.claude/skills/imagegen/SKILL.md`。
- Windows PowerShell 示例应使用 `"$HOME\.claude\skills\imagegen"`，不能把 `~` 传给 native command 后假定一定展开。

重写后至少提供：个人 global 安装、当前项目安装、Windows/POSIX 手动安装、依赖安装、发现验证、dry-run smoke test 和卸载说明。

### 7.8 文档、模型事实和发布工程

单一事实源建议：

- `references/lite.md`、`references/pro.md`：模型能力和直接官方证据。
- `references/cli.md`：主 CLI 参数、I/O、计费状态和恢复。
- 新 `references/chroma-key.md`：本地色键处理。
- `references/prompting.md`：prompt 原则和轻量交付检查。
- `references/sample-prompts.md`：唯一可复制模板。
- `SKILL.md`：触发、路由、安全、工作流和索引，不重复完整规格。

能力边界需澄清：火山方舟公开提示词指南明确 Lite 也可使用箭头、线框、涂鸦等普通视觉信号；另一官方教程又将精准坐标等“交互编辑”标为 Pro 支持。当前一行“坐标点、圈选、涂鸦、草图编辑”把两类能力压在一起。应拆成：

- Lite：支持箭头、线框、涂鸦等普通视觉标记控制。
- Pro：精准坐标点和更强的交互/区域编辑能力；以直接官方模型说明为准。

Pro 的 model ID、日期后缀、输入数和尺寸上限应逐项绑定可访问的直接官方来源或版本化快照。找不到公开来源是可追溯性缺口，不等于实现一定错误。

其他发布问题：

- 未知 `--model` 值目前自动回退 Lite。即使有 warning，也可能把 `proo` 这类拼写错误变成付费 Lite 请求。建议默认拒绝；如需兼容，使用显式 `--allow-model-fallback`。
- prompt 前 64 字被放入输出名和隐藏状态名。文档若称状态“不存 prompt”，应说明文件名仍可能泄露 prompt 摘要；提供 hash/自定义输出名模式。
- 两个 README 的 `validate-passing` 是静态 shields badge，仓库没有 CI。应增加真实 workflow badge，或删除。
- 两个 README 的 license badge 写 `MIT`，而 `LICENSE.txt` 明确是 `Apache License 2.0`。这是公开法律元数据错误，应在下一次发布前立即修正为 Apache-2.0；若项目确实要改成 MIT，则必须由版权方明确完成换证，不能只改 badge。
- `requirements.txt` 没有 pytest，但 README 要求运行 pytest。增加 `requirements-dev.txt`、`pyproject.toml` optional-dependencies 或等价方案。
- 英文 README 有模型表，中文 README 没有；两者安装和能力信息应保持结构对齐。
- 增加 frontmatter YAML、内部链接、asset 引用、外部 CWD、空格路径和“禁止裸相对 runtime script”契约测试。

### 7.9 其他已确认的 CLI 契约问题

统一脱敏不足：

- `_validate_remote_url()` 的部分错误会回显原始非法 URL；其中可能带签名 token。
- `preview_payload()` 保留完整 prompt；若用户误把配置中的 API key 放进 prompt，dry-run 会原样打印。
- 部分 stream/download 错误调用 `_redact_message()` 时没有传入当前 API key。

应对 dry-run JSON、错误字符串、SSE 错误对象和 URL 统一使用递归 scrubber：替换配置中的 key、data URI、URL query/fragment、Authorization、cookie 和常见 token 字段。prompt 正常内容仍可显示，但已知 secret 值必须替换。脱敏测试只用伪密钥，不读取真实 `.env`。

原子写中断清理：主 CLI `_atomic_write()` 只捕获 `OSError`。若在临时文件创建后发生 `KeyboardInterrupt` 或 `SystemExit`，临时文件可能残留。应使用 `finally` 做幂等清理；请求状态仍由上层标为 `ambiguous`，不能因为清理临时文件而删除状态证据。

dry-run 结构漂移：真实单图请求将 `image` 发送为字符串，多图才是数组；`preview_payload()` 当前统一把它显示为数组。预检必须保持真实 payload 形状，只把每个敏感值替换为占位符，否则 dry-run 不能作为可靠的结构审查。

timeout 语义：`urllib` 的 `timeout` 约束 socket operation，不是整次生成、SSE 流和下载重试的总耗时。当前 `--timeout 300` 可能总共运行远超 300 秒。应把 help/docs 改称“单次网络操作超时”，或使用 `time.monotonic()` 实现覆盖请求、流和下载的总 deadline。

references 的 payload 契约也需同步：`lite.md:42`、`pro.md:33` 写 `image` 为数组，而代码是“单图字符串、多图数组”。文档应准确反映真实发送结构。

## 8. 分阶段修改计划

### 阶段 0：立即止损与发布门禁

目标：不让现有已知错误继续作为默认路径。

1. 文档暂时移除 `--soft-matte --despill` 的默认推荐，并明确禁用 `--edge-feather`，直到 CK-01～CK-03 有真值测试。
2. 所有 bundled script 调用改为 `${CLAUDE_SKILL_DIR}`，输出改用 `${CLAUDE_PROJECT_DIR}` 绝对路径。
3. HTTP 结果分类改为保守策略：无法证明提交前拒绝的状态全部保留为 `ambiguous`。
4. 将 P0 测试先写成失败测试，避免以阈值改动掩盖算法问题。

交付：安全补丁版本；不发真实 API smoke test，除非用户另行明确授权计费。

### 阶段 1：测试基线与配置隔离

1. 建立合成 alpha 真值矩阵、opaque RGB 不变、source alpha、feather、auto-key 多峰和少量 composite fixtures。
2. 补 EXIF、动画、HEIC、16-bit、decompression bomb、input=output、no-clobber 和写入失败测试。
3. 重构 `.env` 为惰性、显式配置；测试不读取真实 `.env`，全局阻断网络。
4. 建立 HTTP 状态/业务码矩阵、递归脱敏、档位尺寸矩阵、aggregate payload 边界测试。
5. 固化一个代表性 2K 性能回归基线；4K 只做手工、非阻断记录。

交付：测试先行 PR，不改变用户可见算法结果，除安全修复外。

### 阶段 2：重构色键核心

1. 分离 `source_rgb`、`source_alpha`、`chroma_matte`。
2. 实现连续、单调并由合成真值校准的 matte。
3. 在 partial alpha 上做 foreground recovery；despill 改为平滑、置信度感知。
4. contract/feather 只处理 matte，禁止复活 source alpha=0。
5. 重做 auto-key：dominant cluster、均匀度、四角共识、多峰拒绝。
6. 增加轻量底线诊断：输出可重开、alpha 存在、全空/全满警告。
7. 用 Pillow C 层运算替代主逐像素循环。

交付：算法版本；输出默认写新文件，不自动覆盖历史结果。

### 阶段 3：CLI、I/O 与资源安全

1. EXIF transpose、静态帧契约、HEIF 策略、像素/编码上限。
2. exact target preflight、portable filename、samefile 拒绝和 no-clobber。
3. prompt 临时文件 ownership 和目录限制。
4. aggregate input/request-body 限制、减少 Base64/JSON 复制。
5. named tier 结果精确验收。
6. 所有用户错误中文化、脱敏并保持已有输出。
7. 给原子写增加中断清理；澄清或实现总 deadline；保持 dry-run 与真实 payload 同形。

### 阶段 4：工作流、文档与 assets

1. 新增 `references/chroma-key.md`。
2. 按 SSOT 重构 `SKILL.md` 和 references，消除重复事实。
3. 重写透明 prompt、auto-key 前提和三项轻量交付检查。
4. 明确 agent temp / user deliverable 两态、计费授权和失败恢复。
5. 重写 README 安装；同步中英文结构。
6. 可选裁切/压缩 README wordmark。
7. 每项模型事实绑定直接官方来源和复核日期。
8. 修正 Apache-2.0 license badge 和单图/多图 `image` 文档契约。

### 阶段 5：发布工程

1. 声明并测试支持的 Python 版本。
2. 增加 dev dependencies 和真实 CI。
3. CI 运行 unit tests、compile、docs contract、`git diff --check`；性能基准不进入常规 CI。
4. 用真实 workflow badge 替换静态徽章。
5. 发布前执行只读 dry-run smoke；付费 smoke 必须单独获得授权。

## 9. 逐文件修改映射

| 文件 | 计划修改 |
|---|---|
| `scripts/remove_chroma_key.py` | matte/despill/alpha 分层、auto-key confidence、EXIF/帧/HEIF/像素安全、原子 no-clobber、诊断和性能 |
| `tests/test_remove_chroma_key.py` | 合成真值、颜色保持、source alpha、halo、auto-key 多峰、格式/I/O/性能；删除固化错误 despill 的断言 |
| `scripts/image_gen.py` | HTTP outcome 分类、惰性 config、prompt cleanup ownership、aggregate cap、tier 校验、portable exact target、递归脱敏、临时文件清理、deadline、dry-run 同形和隐私命名 |
| `tests/test_image_gen.py` | 不读取真实 `.env`、全局断网、HTTP 状态矩阵、脱敏、payload 预算、tier、Windows 路径、中断清理、跨 CWD |
| `SKILL.md` | `${CLAUDE_SKILL_DIR}`/`${CLAUDE_PROJECT_DIR}`、两态文件所有权、临时清理、透明流程止损、轻量交付检查、模型能力边界、减少重复 |
| `references/chroma-key.md` | 新增精简色键 CLI、格式、参数、alpha、失败恢复和三项交付检查 |
| `references/cli.md` | 只保留主 CLI；明确路径、状态分类、计费和恢复 |
| `references/prompting.md` | 透明 prompt 单一原则、key 选择、停止条件和验收 |
| `references/sample-prompts.md` | 唯一透明模板；修复标签/Logo/反射矛盾 |
| `references/lite.md` | 普通视觉标记边界和直接来源 |
| `references/pro.md` | 精准交互边界、每项能力的直接官方来源 |
| `README.md` / `README-zh.md` | 安装 scope/agent/CWD、依赖、发现验证、模型表、真实 badge、色键边界 |
| `.env.example` | 空 key 和 placeholder 检查说明 |
| `requirements.txt` / dev 配置 | 运行依赖与开发依赖分离 |
| `assets/` | 可选裁切/压缩 README wordmark |
| `.github/workflows/` | 新增真实 CI（若决定保留 validate badge） |

## 10. 验收标准

### 10.1 色键正确性

- 黑、白、灰、红、蓝主体在 green/magenta key 上的合成真值 alpha 单调、连续；建议平均绝对误差不高于 8/255，最大误差阈值由真实 fixture 校准后固化。
- `(64,255,64)` 和 `(128,255,128)` 等白色边缘不再分别输出 0/255 的错误阶跃。
- `alpha == 255` 的主体 RGB 默认逐字节不变。
- `source_alpha == 0` 经 contract/feather 后仍为 0；输入 alpha 1、8、9、128、254 保留语义。
- 选取一个黑或白高对比背景做合成 fixture，不出现明显黑圈、白圈或 key 色圈。
- auto-key 对 50/50 多峰边框必须失败且不写输出；均匀背景能稳定选到真实 cluster。
- EXIF Orientation 正确；动画显式拒绝；HEIC 按声明支持或显式拒绝。
- input=output 拒绝；失败不破坏旧输出；无 `--force` 不覆盖并发新目标。
- 2048² soft+despill 同机相对当前基线至少快 5 倍；4K 仅手工记录，不作为常规发布门禁。

### 10.2 主 CLI 安全

- import `scripts.image_gen` 不读磁盘 `.env`、不修改 `os.environ`、不访问网络。
- 408、5xx 和未知 HTTP/Ark code 保留 `ambiguous` 状态；只有文档化 allowlist 才清理。
- aggregate payload 超限在任何 Base64 大量分配和 POST 前失败。
- Lite/Pro named tier 返回错误档位时失败；自定义尺寸继续精确匹配。
- Windows 保留名、路径过长、目录不可写、目标冲突在 POST 前失败。
- `--cleanup-prompt-file` 无法删除 `tmp/seedream/` 外、symlink、用户输入或输出路径。
- 未知模型值默认失败，不自动形成真实请求。
- dry-run 的单/多图 payload 结构与真实请求一致，且伪 API key、data URI 和签名 URL 不会出现在 stdout/stderr。
- 原子写入被 `KeyboardInterrupt`/`SystemExit` 打断后不残留 `.tmp`；请求状态仍保持 `ambiguous`。
- `--timeout` 的 help、实现和测试对“socket timeout”或“总 deadline”使用同一语义。
- 测试层全局阻断真实网络，并不读取仓库真实 `.env`。

### 10.3 Skill、文档与安装

- 从任意外部 CWD 和带空格的 skill/project 路径可完成 dry-run。
- runtime 文档不再出现裸 `python scripts/...`。
- 个人 global 与当前 project 安装命令均可复制执行，并锁定 `claude-code`。
- 最终目录检查能确认 `<skills-root>/imagegen/SKILL.md`。
- 所有内部链接和 asset 引用存在；YAML frontmatter 可解析。
- Lite 普通视觉标记与 Pro 精准交互分别说明，不互相否定。
- 两个 README 的关键章节、计费规则和能力表结构一致。
- badge 指向真实 CI；未配置 CI 时不显示 passing。
- license badge 与 `LICENSE.txt` 一致为 Apache-2.0。

### 10.4 生成结果的轻量质量检查

- CLI 自动确认文件可解码、格式、尺寸和数量符合请求。
- agent 最终只需打开一次结果，确认主体/编辑目标/关键文字没有明显错误；透明图额外在棋盘格或一个高对比底色上快速查看。
- 不引入质量评分、自动美学模型、多背景逐项对比或多轮候选打分。发现明显问题时报告并保留文件；任何再次付费生成仍需用户授权。

## 11. 发布门禁与建议版本拆分

建议先发一个安全补丁版本，再发算法版本：

1. **安全补丁**：API-01、RUN-01、透明参数止损、配置测试隔离。
2. **色键重构版本**：CK-01～CK-14 与新 `chroma-key.md`。
3. **工作流/发布版本**：安装、assets、CI、SSOT、模型来源治理。

在安全补丁完成前：

- 不把 `--soft-matte --despill` 作为默认推荐。
- 不使用 `--edge-feather` 交付正式透明资产。
- 不自动重试任何 408、5xx、timeout、断流或结果不确定请求。
- 不从用户项目用裸 `scripts/...` 调用 skill 工具。

## 12. 不应做的修改

- 不用参考实现的 `remove_chroma_key.py` 直接替换本脚本；它共享核心算法缺陷。
- 不用修改阈值代替合成真值测试。
- 不为了测试真实能力发起未授权 Ark 请求。
- 不删除 `pending`/`ambiguous` 状态来绕过保护。
- 不删除用户输入、生成原图或无法证明 ownership 的色键源图。
- 不在同一 PR 顺便大改无关风格；按阶段小而可审查地提交。

## 13. 外部依据

- [Claude Code Skills 官方文档](https://code.claude.com/docs/en/slash-commands)：skill 发现、目录与 `${CLAUDE_SKILL_DIR}` / `${CLAUDE_PROJECT_DIR}` 等运行上下文。
- [`npx skills` 官方仓库](https://github.com/vercel-labs/skills)：project/global scope 与 agent 选择。
- [火山方舟 Seedream 4.0–5.0 教程](https://www.volcengine.com/docs/82379/1824121?lang=zh)：Seedream 使用、交互编辑和能力说明。
- [火山方舟图片生成 API](https://api.volcengine.com/api-docs/view?action=ImageGenerations&serviceCode=ark&version=2024-01-01)：请求/响应接口依据。
- [火山方舟提示词指南](https://www.volcengine.com/docs/82379/1829186)：Lite/4.5/4.0 的箭头、线框、涂鸦等视觉信号说明。

## 14. 最终判断

项目的主方向正确，基础安全设计明显强于“临时 SDK 脚本”方案；最值得保留的是统一 CLI、dry-run、能力校验、请求状态、响应验证和原子保存。主要问题不是功能缺失，而是几处高风险边界被文档包装成默认能力：色键高级参数尚未达到视觉正确性，请求状态对 HTTP 错误过度乐观，skill 自身路径与项目路径没有分开。后续改动应保持轻型项目尺度，生成结果只做必要而简短的底线检查。

修复顺序应坚持：先保护付费状态和调用路径，再建立色键真值测试，然后重做 matte/despill/alpha，最后整理文档、安装和 assets。按本计划实施后，项目可以在不推翻现有 CLI 的前提下达到可验证、可恢复、可发布的状态。
