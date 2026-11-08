# 项目记忆备份

> 本目录是 `.workbuddy/memory/` 的**版本库备份**。
>
> **为什么要有它**：`.workbuddy/` 被 `.gitignore` 排除（那里是内部工作笔记），
> 所以它是**单点** —— 2026-11-08 的一次误操作（`robocopy /MIR`）把整个工作目录
> 清空时，`.workbuddy/memory/` 一起没了，只能从会话记录 jsonl 里重建。
>
> **怎么用**：`.workbuddy/memory/` 仍是运行时的工作位置（那里写起来方便、
> 不进版本库）。但**每天收工时把 `memory/` 复制一份到这里**，
> 这样即使工作目录出事，也能从这里恢复。
>
> | 文件 | 内容 |
> |---|---|
> | `PROJECT-MEMORY.md` | 项目长期记忆（架构、坑、约定）—— 原 `MEMORY.md` |
> | `2026-11-06.md` / `2026-11-07.md` / `2026-11-08.md` | 逐日工作日志 |
>
> ★ 日志是**追加式**的：当天的新内容往后接，不改旧段落。
>
> ★ 恢复方法（万一 `.workbuddy/memory/` 丢了）：
> ```bash
> cp docs/memory/PROJECT-MEMORY.md .workbuddy/memory/MEMORY.md
> cp docs/memory/2026-*.md .workbuddy/memory/
> ```
> 再把会话记录（`~/.workbuddy/projects/<项目名>/*.jsonl`）里的后续编辑重放上去。
