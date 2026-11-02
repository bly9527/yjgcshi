# Powerbank Design Skills

充电宝资料分析与 AI 画板准备的经验 Skill。目标是把原理图、PCB、BOM、开发需求和芯片手册整理成可以追溯的设计依据，适用于嘉立创 EDA 专业版等后续设计工作。

## 包含的 Skill

[`powerbank-design-review`](skills/powerbank-design-review/SKILL.md) 提供：

- 文件哈希去重、同名不同版本识别和配套关系核对。
- 原理图/PCB 当前位号与来源位号、引脚/焊盘网络的交叉研究。
- 电源路径、正负极保护、差分电流采样、NTC 与板间接口分析。
- BOM 装配状态、替代料、芯片订货后缀和手册冲突处理。
- 带来源的知识库与后续画板交接，区分静态解析、EDA 检查和硬件实测。

仓库内容为通用方法和可移植工具，不含客户原图、采购表、固件或具体项目的私有资料。

## 本地使用

将 `skills/powerbank-design-review` 整个目录复制到 Codex 的用户技能目录（通常为 `~/.codex/skills`），保持目录名称。也可让支持读取 Skill 文件的其他 AI 工具直接读取其中的 `SKILL.md`。

示例请求：

```text
使用 $powerbank-design-review 学习这个文件夹里的充电宝资料，
核对原理图、PCB 与 BOM，整理保护和采样路径、版本差异，
为以后嘉立创 EDA 专业版画板建立可检索的依据。
```

只做文件索引时，可用 Python 3 标准库脚本：

```text
python skills/powerbank-design-review/scripts/inventory_sources.py <资料目录> --output <分析目录>/sources.json
```

索引只表示找到和计算过哈希，不表示已读懂设计。源工程保持只读；脚本不上传文件。实际设计仍需针对选定版本完成网络、封装、制造及硬件验证。
