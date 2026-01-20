## Code Plan：LLM 调度器 + 轻量总线（MVP）

### 目标

在不使用原生 Agent 框架的情况下，实现一个最小可用系统：

* 使用 **LLM 作为调度器**
* 仅支持 **4 个 Skill**
* 根据用户输入判断是否能匹配 Skill
* 匹配成功后执行 Skill，产出内容
* 使用一个 **极简全局状态总线（JSON）** 管理流程状态

---

## 一、整体架构（MVP）

系统由 4 个核心模块组成：

1. GlobalStateBus（全局状态总线）
2. Skill Registry（Skill 注册表）
3. LLM Dispatcher（调度器）
4. Skill Executor（执行器）

所有模块均为同步调用，单进程即可跑通。

---

## 二、Global State Bus（极简版）

### 设计目标

* 只记录流程状态
* 不存正文内容
* 只服务调度判断和前端展示

### 数据结构（必须严格遵守）

```json
{
  "session_id": "string",
  "stage": "idle | skill_selected | skill_running | skill_done | error",
  "selected_skill": null,
  "skills": {
    "outline": { "status": "empty | done" },
    "experiment": { "status": "empty | done" },
    "game": { "status": "empty | done" },
    "storyboard": { "status": "empty | done" }
  },
  "last_output_ref": null
}
```

### 约束

* **禁止**把生成内容写进总线
* 内容只允许写入文件（如 `outputs/*.md`）
* 总线只写：状态 + 文件引用

---

## 三、Skill 定义（4 条，硬编码）

### Skill 接口规范

每个 Skill 是一个 Python 对象，包含以下字段：

```python
Skill(
  name: str,
  description: str,
  trigger_keywords: List[str],
  prompt_template: str,
  output_filename: str
)
```

### MVP Skills 示例
Skill 1：逐字稿生成

名称
transcript_generation

职责
根据用户提供的主题 / 要点 / 简要描述，生成自然口语化、可直接朗读或录音的逐字稿。

输入

教学主题或要点（文本）

可选：目标对象（如小学 / 初中）

输出

逐字稿文本（Markdown 或纯文本）

强调“口语化、连贯、不像论文”

=====

Skill 2：图像生成（内容资产类）

名称
image_generation

职责
根据文本描述生成教学插图 / 场景图 / 示意图。

输入
文本描述（来自用户或其他 Skill）
可选：风格标签（卡通 / 写实 / 扁平）
输出
本地图片文件（PNG/JPG）
返回文件路径作为 ref

关键约束
只在这个 Skill 内调用图像模型
不把图片塞进总线

========
Skill 3：逐字稿 → 教学脚本（结构化生成）

名称
script_from_transcript

职责
把逐字稿（老师原话 / 讲解稿）整理成结构清晰、可教学使用的视频脚本。

输入
逐字稿文本
输出
教学脚本（结构化 Markdown）

开场
讲解段
提问点
总结


Skill 4：问题链设计
名称：question_chain_generation

职责
根据已有教学内容，生成可直接在课堂中使用的互动问题，用于引导学生参与、检查理解和拓展思考。
不重写原文，不改结构，只做“提问增强”。

输入
一段教学文本（脚本 / 逐字稿 / OCR 后文本）
可选参数：
年级 / 年龄段（如：小学 / 初中）
课堂场景（可选）
输出（强结构化，利于前端/评估）
推荐 Markdown 或 JSON，例如：

## 课堂互动问题

### 一、引导性问题
- 为什么老师一开始要提到……？
- 你觉得这个现象和生活中的什么事情像？

### 二、理解检查问题
- 实验的关键步骤是哪一步？
- 如果少了这个条件，会发生什么？

### 三、思考拓展问题
- 你还能想到类似的例子吗？
- 如果换一种材料，结果会不会不同？

Prompt_Template（给 Cursor 的）


---

## 四、LLM 调度器（核心）

### 调度器职责

* 接收用户输入
* 判断最匹配的 Skill
* 不生成内容
* 只返回一个结构化结果

### Prompt 设计（关键）

调度器 Prompt 必须要求 LLM **只输出 JSON**

Prompt 核心意图：

* 给定用户输入
* 给定 Skill 列表（name + description + keywords）
* 判断：

  * 是否能匹配某个 Skill
  * 如果能，返回 skill_name
  * 如果不能，返回 null

### LLM 输出格式（必须）

```json
{
  "matched": true,
  "skill": "experiment"
}
```

或

```json
{
  "matched": false,
  "skill": null
}
```

---

## 五、调度流程（主流程）

### Step 1：用户输入

```python
user_input = "我们来搞个好玩的实验"
```

### Step 2：调用 LLM Dispatcher

```python
result = dispatch(user_input, skill_registry)
```

### Step 3：判断结果

* matched == false
  → 返回提示：“我目前只能帮你做：大纲 / 实验 / 游戏 / 分镜”

* matched == true
  → 更新总线：

```json
stage = "skill_selected"
selected_skill = "experiment"
```

---

## 六、Skill 执行器

### 执行规则

* 只执行一个 Skill
* 不读取历史对话
* 只注入：

  * Skill.prompt_template
  * 用户原始输入（可选）

### 执行流程

1. 根据 selected_skill 找到 Skill
2. 调用 LLM 生成内容
3. 将结果写入文件：

   ```
   outputs/experiment.md
   ```
4. 更新总线：

```json
stage = "skill_done"
skills.experiment.status = "done"
last_output_ref = "outputs/experiment.md"
```

---

## 七、错误处理（最低要求）

* LLM 返回非 JSON → retry 1 次
* Skill 执行异常 → stage = "error"
* 文件写入失败 → stage = "error"

---

## 八、MVP 验收标准（非常重要）

系统满足以下条件即可上线测试：

* 用户输入能被正确匹配到 Skill（≥70% 主观可用）
* 每次只执行一个 Skill
* Skill 输出能生成文件
* 总线状态始终可读、可解释
* 代码结构清晰，可扩展到 Agent 框架

---

## 九、Cursor 使用建议（给你）

你可以这样用 Cursor：

1. 先让它生成：

   * GlobalStateBus 类
   * Skill 数据结构
2. 再让它写：

   * dispatch() 调度函数
3. 最后让它写：

   * execute_skill() 执行器

每一步单独让它写，不要一次性全写。


---

总线路径下的文件全部保存在本地