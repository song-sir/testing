---
name: context
description: 项目记忆管理 — 初始化、保存、更新、归档，LLM 自主管理
triggers:
  - context init
  - context save
  - context update
  - context archive
  - 初始化记忆
  - 保存记忆
  - 更新记忆
  - 归档记忆
---

test
# 项目记忆管理

LLM 自主管理项目记忆。本指南定义约定和操作流程。

## 约定

### 目录结构

```
<project>/
├── CLAUDE.md                # ≤100 行，项目概况 + 核心规则
│                            # 必须包含指引："项目记忆 → docs/memory/MEMORY.md"
└── docs/memory/
    ├── MEMORY.md            # 索引文件，LLM 通过这里按需加载记忆
    ├── archive/             # 归档的过时记忆
    └── (其他文件/目录由 LLM 自主创建和组织)
```

### 记忆文件格式

每个记忆文件**必须**有 frontmatter：

```
---
type: <类型名，LLM 自定义>
description: <一行描述，用于判断是否需要加载>
updated: <YYYY-MM-DD>
---

# 标题

(内容)
```

### MEMORY.md 索引格式

```
# 项目记忆索引

## 必记项
- [架构决策](architecture.md) — 技术栈和核心架构决策
- [踩坑经验](pitfalls.md) — 开发过程中的关键教训

## 其他
- [文件名](路径) — 一行描述
```

**规则**：新增或删除记忆文件时，必须同步更新 MEMORY.md 索引。

### 必记项

**默认必记项**（所有项目）：

| 名称 | 说明 |
|------|------|
| architecture | 技术栈、核心架构决策、项目结构 |
| pitfalls | 开发过程中的踩坑经验和关键教训 |

**用户自定义必记项**：用户可在 CLAUDE.md frontmatter 中追加：

```yaml
---
required_memories:
  - name: api-changelog
    description: API 接口变更记录
  - name: deployment
    description: 部署流程和环境配置
---
```

用户可设置 `skip_default_memories: true` 跳过默认必记项。

最终必记项 = 默认 + 用户自定义（去掉 skip 的）。

### 记忆判断原则

- 会影响未来开发决策的 → **记**
- 调试过程中的临时信息 → **不记**
- 已在代码/注释/commit message 中体现的 → **不记**

### LLM 自由度

除必记项和上述约定外，LLM 可以自主：

- 创建任意新记忆文件（自定义 type 名）
- 组织子目录（如按模块分目录）
- 决定文件粒度（一个大文件 vs 多个小文件）
- 归档或删除过时记忆

## 操作流程

### init — 初始化记忆系统

**触发**：`/context init`

1. 检查 `docs/memory/` 是否已存在
   - 如已存在 → 提示用户已初始化，询问是否重新初始化（会清空现有记忆）
   - 用户拒绝 → 结束
2. 读取 CLAUDE.md frontmatter，提取用户自定义 `required_memories`
3. 合并默认必记项 + 用户必记项 = 完整必记项清单
4. 浏览项目代码、README、配置文件，理解项目现状
5. 创建 `docs/memory/` 目录
6. 为每个必记项创建记忆文件（带 frontmatter），**内容根据项目现状填写，不是空模板**
7. 如果 LLM 发现还有值得记录的内容，自主创建额外记忆文件
8. 创建 MEMORY.md 索引（必记项在"必记项"分区，额外的在"其他"分区）
9. 在 CLAUDE.md 中添加指引（如果没有的话）：`项目记忆 → docs/memory/MEMORY.md`
10. 向用户汇报：创建了哪些文件、记录了什么

### save — 会话结束前保存

**触发**：`/context save`

1. 回顾当前会话中产生的关键信息（架构决策、踩坑、进度变化等）
2. 如果没有值得记忆的内容 → 告知用户，结束
3. 读取 MEMORY.md 索引，加载相关记忆文件
4. 将新信息写入对应记忆文件（更新已有内容或新建文件）
5. 更新 frontmatter 的 `updated` 字段
6. 检查必记项文件是否有需要更新的
7. 如新建了文件 → 更新 MEMORY.md 索引
8. 向用户汇报：更新了哪些记忆、新增了什么

### update — 主动更新记忆

**触发**：`/context update [参数]`

用法：
- `/context update` — LLM 自行判断哪些记忆需要更新
- `/context update architecture` — 指定更新某个记忆
- `/context update "我们决定用 Redis 做缓存"` — 告诉 LLM 具体要记什么

流程：
1. 如有指定记忆名 → 加载该记忆文件，按当前项目状态更新
2. 如有具体内容 → 判断归入哪个记忆文件，写入
3. 如无参数 → 读取当前项目状态（代码、git log），对比现有记忆，找出过时内容并更新
4. 写入记忆文件，更新 frontmatter `updated` 字段
5. 如新建了文件 → 更新 MEMORY.md 索引
6. 向用户汇报变更

### archive — 归档过时记忆

**触发**：`/context archive`

1. 读取 MEMORY.md 索引，逐个检查记忆文件
2. 判断哪些内容已过时：已完成的里程碑、已解决的问题、不再适用的决策
3. 如果没有可归档内容 → 告知用户，结束
4. 将过时文件移入 `docs/memory/archive/`（保留文件，在 frontmatter 中添加 `archived: YYYY-MM-DD`）
5. 更新 MEMORY.md 索引（移除归档项，或移到"已归档"分区）
6. 向用户报告：归档了什么、为什么
