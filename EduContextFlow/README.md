# EduContextFlow

**教育上下文流管理系统** - 基于语义索引的 LLM Agent 架构

## 🎯 核心设计哲学

### 三个核心原则

1. **总线是唯一状态源**
   - 无全局变量，所有状态存储在 `GlobalStateBus`
   - Session scoped，并发安全

2. **上下文即索引，非全文**
   - `context_index` 只存储 `{type: {ref, producer, status}}`
   - 不存储文件内容，避免内存膨胀

3. **职责严格分层**
   - **Dispatcher**：决策（基于规则 + LLM）
   - **Bus**：状态存储
   - **App**：编排执行
   - **Executor**：纯执行（禁止推理）

---

## 🏗️ 架构分层

### 1️⃣ Dispatcher（调度层）

**职责**：
- 接收用户输入 + Bus 状态
- 决定下一步动作：`call_skill` | `ask_user` | `no_action` | `refuse`
- 检查 Skill 上下文依赖是否满足

**硬约束校验**（双层保障）：
```python
# LLM 层（Prompt 约束）
You may ONLY call a skill if ALL its required_context types are present

# Python 层（代码校验）
if action == "call_skill":
    is_valid, reason = _validate_skill_requirements(skill, context_index)
    if not is_valid:
        return {"action": "ask_user", "question": f"缺少: {reason}"}
```

**输出 Schema**（严格约束）：
```json
{
  "action": "call_skill | ask_user | refuse",
  "skill_name": "string | null",
  "reason": "string",
  "question": "string (仅 ask_user)",
  "options": ["string"] (仅 ask_user)
}
```

**严格禁止**：
- ❌ 输出包含 `input` 或 `input_hints` 字段（防止认知污染）
- ❌ 读取文件全文
- ❌ 做上下文拼接或推测

### 2️⃣ GlobalStateBus（状态层）

**数据结构**：
```json
{
  "session_id": "uuid",
  "stage": "idle",
  "context_index": {
    "transcript": {
      "ref": "outputs/transcript.md",
      "producer": "transcript_generation",
      "status": "ready",
      "description": "教学逐字稿"
    },
    "script": {
      "ref": "outputs/script.md",
      "producer": "script_from_transcript",
      "status": "ready",
      "description": "结构化教学脚本"
    }
  },
  "pending_user_input": "用户最后输入",
  "skills": { ... }
}
```

**关键 API**：
- `get_state()` - 获取快照
- `mark_skill_done(name, ref, type, desc)` - 写入上下文索引
- `set_pending_input(input)` - 保存当前轮次用户输入
- `clear_pending_input()` - 清空已消耗的输入（语义锁）

**pending_user_input 语义规则**（硬约束）：
```python
# 仅存储"尚未被任何 Skill 消耗"的用户原文
# 生命周期：
#   1. 用户发送消息 → set_pending_input()
#   2. Skill 执行成功 → clear_pending_input()
#   3. no_action/refuse → clear_pending_input()
#   4. ask_user → 保留（等待用户回答）
```

**禁止**：
- ❌ 存储文件内容
- ❌ 存储多轮历史输入
- ❌ 做业务逻辑判断

### 3️⃣ App（编排层）

**职责**：
1. 接收 HTTP 请求
2. 保存用户输入到 Bus
3. 调用 Dispatcher 获取决策
4. **读取上下文** + 组装输入（如果 Skill 需要）
5. 调用 Executor 执行
6. 更新 Bus 状态

**关键函数**：
```python
def _prepare_skill_input(skill, user_message, context_index):
    """
    App 层负责：读取上下文文件 + 组装输入
    Executor 只接收最终 input_text
    """
    if skill.requires_context:
        # 从 context_index 读取所需文件
        # 组装：上下文内容 + 用户要求
    return input_text
```

**stage 使用规则**（严格限制）：
```python
# ✅ 允许：记录阶段（用于 UI 展示 / debug）
bus.set_stage("skill_running")

# ❌ 禁止：基于 stage 做流程判断
if state.get("stage") == "skill_selected":  # 违规！
    ...
```

**原则**：
- `stage` 只是日志字段，不是状态机控制器
- 所有流程决策必须来自 Dispatcher
- App 只执行 Dispatcher 的决策，不做自主判断

**严格禁止**：
- ❌ 基于 `stage` 做 if/else 分支判断
- ❌ 绕过 Dispatcher 直接执行 Skill

### 4️⃣ Executor（执行层）

**职责**（仅三件事）：
1. 接收 `input_text`（已由 App 组装好）
2. 格式化 Prompt → 调用 LLM/Image Model
3. 写输出文件 → 返回文件路径

**严格禁止**：
- ❌ 读取 `context_index`
- ❌ 读取历史文件
- ❌ 做任何上下文推理
- ❌ 做任何业务逻辑判断

```python
def execute_skill(skill: Skill, input_text: str) -> str:
    """
    纯粹的执行器，无状态，无副作用（除了写文件）
    """
    prompt = skill.prompt_template.format(user_input=input_text)
    result = llm.complete(prompt)
    write_output(result)
    return output_path
```

---

## 🔄 完整数据流

```
用户请求
  ↓
App: 保存到 Bus.pending_user_input
  ↓
Dispatcher: 
  - 读取 Bus.context_index
  - 校验 Skill 依赖
  - 决策: call_skill("script_from_transcript")
  ↓
App (_prepare_skill_input):
  - 读取 context_index["transcript"]["ref"]
  - 加载文件内容
  - 组装: transcript内容 + 用户要求
  ↓
Executor (execute_skill):
  - 接收 input_text
  - 调用 LLM
  - 写 outputs/script.md
  - 返回 ref
  ↓
Bus.mark_skill_done:
  - context_index["script"] = {ref, producer, status}
  ↓
返回结果给用户
```

---

## 📦 Skill 定义

每个 Skill 包含：

```python
@dataclass
class Skill:
    name: str
    description: str
    requires_context: list[str]  # 依赖的上下文类型
    output_type: str              # 输出类型（枚举）
    prompt_template: str
    ...
```

**上下文类型映射**（固定枚举）：
- `transcript_generation` → `transcript`
- `script_from_transcript` → `script` (requires: `["transcript"]`)
- `question_chain_generation` → `question_chain`
- `image_generation` → `image`

---

## 🛡️ 并发安全设计

### ❌ 之前的问题

```python
LAST_USER_MESSAGE = ""  # 全局变量
# 问题：多用户会互相覆盖
```

### ✅ 现在的解决方案

```python
# 每个 session 独立的状态
bus = GlobalStateBus(STATE_PATH)  # 基于 session_id
bus.set_pending_input(message)     # Session scoped
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
GEMINI_API_KEY=your_api_key
GEMINI_TEXT_MODEL=gemini-2.5-flash
GEMINI_IMAGE_MODEL=models/imagen-4.0-fast-generate-001
USE_PROXY=false  # 如需代理设为 true
```

### 3. 启动服务

```bash
python app.py
```

访问：http://localhost:3000

---

## 📂 项目结构

```
.
├── app.py                    # Flask 服务（编排层）
├── bus.py                    # GlobalStateBus（状态层）
├── dispatcher.py             # Dispatcher（决策层 + 校验）
├── executor.py               # Executor（纯执行层）
├── llm.py                    # LLM Client（带重试机制）
├── skills.py                 # Skill 注册表
├── skills/                   # Skill Prompt 定义
│   ├── transcript_generation.md
│   ├── image_generation.md
│   ├── script_from_transcript.md
│   └── question_chain_generation.md
├── web/                      # 前端（原生 HTML/CSS/JS）
│   ├── index.html
│   ├── styles.css
│   └── app.js               # 加载动画 + 计时器
├── outputs/                  # 生成文件输出
├── state.json                # Bus 持久化（JSON）
└── requirements.txt
```

---

## 🔧 技术栈

- **后端**：Python 3.12 + Flask + Flask-CORS
- **LLM**：Google Gemini API (gemini-2.5-flash)
- **图像生成**：Imagen 4 Fast
- **状态管理**：JSON 文件（GlobalStateBus）
- **前端**：原生 HTML/CSS/JS（无框架）

---

## 📝 核心特性

### ✅ 语义上下文索引

- 不存储文件内容，只存储索引
- Key = 语义类型（transcript/script/...）
- Value = {ref, producer, status, description}

### ✅ 硬约束校验

- Prompt 层约束（指导 LLM）
- Python 层校验（强制拦截）
- 依赖不满足 → 自动 ask_user

### ✅ LLM 输出清理

- 自动移除 Prompt 复述
- 智能重试（503/429 错误）
- 指数退避策略

### ✅ 前端优化

- 实时加载动画（跳动圆点）
- 等待计时器（显示已等待秒数）
- 实时文件预览

---

## 🛡️ 架构防御机制

### 三大长期风险及防范

#### 🚨 风险 1：Dispatcher 输出的认知污染

**问题**：
- 如果允许 Dispatcher 输出 `input` 字段，会诱导未来的开发者"相信 Dispatcher 的输入构造"
- 这违反了"Dispatcher 只决策，不构造内容"的原则

**防范**：
```json
// ✅ 正确的 Dispatcher 输出（无 input 字段）
{
  "action": "call_skill",
  "skill_name": "transcript_generation",
  "reason": "用户明确要求生成逐字稿"
}

// ❌ 禁止的输出（包含 input 推测）
{
  "action": "call_skill",
  "skill_name": "image_generation",
  "input": {"prompt": "森林场景"}  // 违规！
}
```

**强制规则**：
- Dispatcher 输出 schema 不包含 `input` 或 `input_hints`
- 所有输入构造由 App 层的 `_prepare_skill_input()` 完成

---

#### 🚨 风险 2：stage 被滥用为状态机控制器

**问题**：
- `stage` 只是记录字段，不应该用于流程判断
- 一旦 App 层基于 `stage` 做 if/else，就会逐渐"偷回"Dispatcher 的权力

**防范**：
```python
# ✅ 允许：记录状态（用于 UI/debug）
bus.set_stage("skill_running")
print(f"当前阶段：{state.get('stage')}")

# ❌ 禁止：基于 stage 做流程判断
if state.get("stage") == "skill_selected":  # 违规！
    execute_skill(...)
```

**强制规则**：
- App 层禁止出现 `if ... stage ... ==` 的判断逻辑
- 所有流程决策必须来自 `dispatch()` 的返回值
- `stage` 仅用于：UI 展示、日志记录、状态回放

---

#### 🚨 风险 3：pending_user_input 的语义污染

**问题**：
- 如果不明确生命周期规则，会出现"3 轮前的用户输入被错误当成当前意图"
- 多轮对话会导致状态混乱

**防范**：
```python
# ✅ 正确的生命周期管理
bus.set_pending_input(message)       # 1. 接收用户输入
result = dispatch(...)                # 2. Dispatcher 决策
execute_skill(...)                    # 3. Skill 执行
bus.clear_pending_input()             # 4. 清空（输入已消耗）

# ❌ 错误：忘记清空，导致历史污染
bus.set_pending_input("生成逐字稿")
execute_skill("transcript_generation")
# 忘记 clear_pending_input()
bus.set_pending_input("生成图片")
# 此时 pending_user_input 可能混乱
```

**强制规则**：
- Skill 成功执行后 **必须** 调用 `clear_pending_input()`
- `no_action` / `refuse` 也 **必须** 清空
- `ask_user` **保留**输入（等待用户回答）
- 禁止存储多轮历史输入

---

## 🎓 设计原则总结

| 层级 | 职责 | 禁止 |
|------|------|------|
| **Dispatcher** | 决策 + 校验依赖 | 读取文件全文 |
| **Bus** | 存储索引 | 存储文件内容 |
| **App** | 读取上下文 + 编排 | 基于 stage 做流程判断 |
| **Executor** | 调用 LLM + 写文件 | 读取 context_index |

**核心理念**：职责分离，状态单一，依赖显式，执行纯粹。

---

## 📄 License

MIT
