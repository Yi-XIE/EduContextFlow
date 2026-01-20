# Skill: course_production_workflow
# 中文名称：课程制作完整流程
# 类型：workflow

intent_description

当用户希望完成完整的课程设计与制作流程，
通常以"帮我做一个完整的课程 / 从零开始制作课程 / 完成整个课程制作流程"为目标，
输入是课程基本信息（主题、目标人群、时长等），
且期望系统自动按顺序执行所有步骤（目标确认→设计方案→评审→脚本→评审→分镜→评审）时，调用本 Workflow。

调度器判断要点：
- 输入：课程基本信息
- 输出：完整的课程制作产物链
- 是工作流类型，会依次执行多个子skill
- 用户明确要求"完整流程"或"全流程"

## 目的（Purpose）
串联课程设计与制作的完整流程，按步骤依次执行所有子 skill，
从课程目标确认开始，到分镜脚本评审结束，生成完整的课程制作产物链。

本 Workflow 会自动管理各步骤之间的依赖关系，确保每个步骤在前置步骤完成后才执行。

---

## 前置条件（Prerequisites）
- 用户已提供课程基本信息（主题、目标人群、时长等）
- 或用户明确要求"完成整个课程制作流程"

---

## 输入字段（Input Fields）
- course_topic：课程主题或名称
- target_audience：目标人群（年龄、职业、基础水平等）
- course_duration（可选）：课程时长或课时数
- expected_outcomes（可选）：预期收益或应用场景

---

## 执行步骤（Workflow Steps）
按以下顺序依次执行：

1. `course_goal_definition` - 课程目标确认
   - 输入：课程基本信息
   - 输出：course_goal

2. `course_design_plan` - 课程设计方案编写
   - 输入：course_goal
   - 输出：design_plan

3. `course_plan_review` - 课程设计方案评审
   - 输入：design_plan
   - 输出：design_review

4. `course_script_writing` - 课程脚本编写
   - 输入：design_plan
   - 输出：course_script

5. `course_script_review` - 课程脚本评审
   - 输入：course_script
   - 输出：script_review

6. `storyboard_writing` - 分镜脚本编写
   - 输入：course_script
   - 输出：storyboard

7. `storyboard_review` - 分镜脚本评审
   - 输入：storyboard
   - 输出：storyboard_review

---

## 输出要求（Output Requirements）
- 输出为完整的课程制作产物链
- 包含所有步骤的产物文件
- 每个步骤的产物都会写入 context_index
- 最终产物包括：course_goal, design_plan, design_review, course_script, script_review, storyboard, storyboard_review

---

## 输出格式（Output Format）
Workflow 执行完成后，会在 context_index 中生成以下上下文：

- course_goal: 课程目标文档
- design_plan: 课程设计方案
- design_review: 设计方案评审报告
- course_script: 课程脚本
- script_review: 脚本评审报告
- storyboard: 分镜脚本
- storyboard_review: 分镜脚本评审报告

---

## Prompt 模板（Prompt Template）
注意：本 Workflow 不直接调用 LLM，而是通过执行器依次调用各个子 skill。

Workflow 的执行逻辑由系统自动管理，确保：
- 每个步骤在前置步骤完成后才执行
- 自动传递上下文依赖
- 记录每个步骤的执行状态

---

## 工作流说明（Workflow Notes）
- 本 Workflow 是复合型技能，会依次执行多个子 skill
- 执行过程中，每个子 skill 的产物会自动写入 context_index
- 如果某个步骤失败，Workflow 会停止并报告错误
- 用户可以通过查看 context_index 了解当前执行进度

