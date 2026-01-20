# EduContextFlow 系统状态检查文档

生成时间：$(date)

## 📋 文件位置说明

### 1. 总线数据文件（GlobalStateBus）
- **位置**：`/Users/brick/Desktop/EduContextFlow/state.json`
- **作用**：存储整个系统的状态，包括 context_index、已完成的技能、pending_user_input 等
- **更新频率**：每次状态变化时自动更新

### 2. 执行器生成的内容文件
- **位置**：`/Users/brick/Desktop/EduContextFlow/outputs/`
- **作用**：存储所有 LLM 生成的内容（逐字稿、脚本、图片、问题链等）
- **引用方式**：通过 context_index 中的 ref 字段引用

---

## 🗂️ 当前总线状态（context_index）

| 上下文类型 | 文件路径 | 生产者 | 状态 | 描述 |
|-----------|---------|--------|------|------|
| transcript | outputs/transcript.md | transcript_generation | ready | 教学逐字稿 |
| script | outputs/script.md | script_from_transcript | ready | 表格化教学视频脚本 |
| image | outputs/image.png | image_generation | ready | 教学插图 |
| question_chain | outputs/question_chain.md | question_chain_generation | ready | 引导性问题链 |

---

## 📊 上下文关联关系

```
transcript (逐字稿)
    ↓ 依赖
script (脚本) ← script_from_transcript 需要 transcript

image (图片) ← 独立生成，不依赖其他上下文

question_chain (问题链) ← 可以基于任何文本内容生成
```

---

## 🔍 关键数据流

1. **用户发送消息** → `pending_user_input` 存储
2. **Dispatcher 决策** → 读取 `context_index` 判断是否满足依赖
3. **App 准备输入** → 从 `context_index.ref` 读取文件内容
4. **Executor 执行** → 调用 LLM → 生成文件
5. **更新 Bus** → `mark_skill_done` 写入 `context_index`
6. **清空输入** → `clear_pending_input()` 清空已消耗的输入

---

## 📁 所有生成文件

见下方文件列表。

