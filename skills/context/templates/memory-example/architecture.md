---
type: architecture
description: 技术栈、项目结构、核心设计决策
updated: 2026-04-12
---

# 架构决策

## 技术栈
- 语言：Python 3.11
- 框架：FastAPI
- 数据库：PostgreSQL + SQLAlchemy

## 项目结构
src/ 下按领域划分模块，每个模块包含 routes/services/models。

## 核心决策
- 选择 FastAPI 而非 Django：项目以 API 为主，不需要模板引擎和 admin
- 数据库迁移用 Alembic：与 SQLAlchemy 集成最好
