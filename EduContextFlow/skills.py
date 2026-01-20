from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    intent_description: str
    input_schema: dict
    trigger_keywords: list[str]
    prompt_template: str
    output_filename: str
    output_type: str  # "text" or "image"
    requires_context: list[str]  # 需要的上下文类型（如 ["transcript"]）
    skill_type: str = "skill"  # "skill" or "workflow"
    workflow_steps: list[str] = field(default_factory=list)  # 仅workflow类型使用，子skill名称列表


def _read_prompt(filename: str) -> str:
    base_dir = os.path.join(os.path.dirname(__file__), "skills")
    path = os.path.join(base_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


SKILLS = [
    # Skill 1: 课程目标确认
    Skill(
        name="course_goal_definition",
        description="Define course goals and learning outcomes based on course information.",
        intent_description=(
            "当用户希望明确课程的学习目标、预期成果、能力模型时使用。"
            "输入是课程主题、目标人群、时长、预期收益等基本信息。"
        ),
        input_schema={"course_topic": "string", "target_audience": "string", "course_duration": "string(optional)"},
        trigger_keywords=["课程目标", "学习目标", "定义目标", "课程目标确认"],
        prompt_template=_read_prompt("course_goal_definition.md"),
        output_filename="outputs/course_goal.md",
        output_type="text",
        requires_context=[],  # 不需要前置上下文
    ),
    # Skill 2: 课程设计方案编写
    Skill(
        name="course_design_plan",
        description="Generate course design plan based on course goals.",
        intent_description=(
            "当用户希望基于已确定的课程目标，生成课程设计方案时使用。"
            "包括章节结构、模块划分、课时安排、学习路径。"
        ),
        input_schema={"course_goal": "string"},
        trigger_keywords=["课程设计", "设计方案", "课程方案", "设计课程"],
        prompt_template=_read_prompt("course_design_plan.md"),
        output_filename="outputs/design_plan.md",
        output_type="text",
        requires_context=["course_goal"],  # 需要 course_goal 上下文
    ),
    # Skill 3: 课程设计方案评审
    Skill(
        name="course_plan_review",
        description="Review course design plan and provide feedback.",
        intent_description=(
            "当用户希望对已生成的课程设计方案进行评审时使用。"
            "输出评审结论与修改建议。"
        ),
        input_schema={"design_plan": "string"},
        trigger_keywords=["评审方案", "方案评审", "评审课程设计", "检查方案"],
        prompt_template=_read_prompt("course_plan_review.md"),
        output_filename="outputs/design_review.md",
        output_type="text",
        requires_context=["design_plan"],  # 需要 design_plan 上下文
    ),
    # Skill 4: 课程脚本编写
    Skill(
        name="course_script_writing",
        description="Write detailed course script based on design plan.",
        intent_description=(
            "当用户希望基于课程设计方案，生成详细的课程脚本时使用。"
            "包含讲解文字、示例、练习、关键知识点。"
        ),
        input_schema={"design_plan": "string"},
        trigger_keywords=["课程脚本", "写脚本", "生成脚本", "脚本编写"],
        prompt_template=_read_prompt("course_script_writing.md"),
        output_filename="outputs/course_script.md",
        output_type="text",
        requires_context=["design_plan"],  # 需要 design_plan 上下文
    ),
    # Skill 5: 课程脚本评审
    Skill(
        name="course_script_review",
        description="Review course script and provide feedback.",
        intent_description=(
            "当用户希望对已生成的课程脚本进行评审时使用。"
            "输出评审结论与修改建议。"
        ),
        input_schema={"course_script": "string"},
        trigger_keywords=["评审脚本", "脚本评审", "检查脚本", "脚本审查"],
        prompt_template=_read_prompt("course_script_review.md"),
        output_filename="outputs/script_review.md",
        output_type="text",
        requires_context=["course_script"],  # 需要 course_script 上下文
    ),
    # Skill 6: 分镜脚本编写
    Skill(
        name="storyboard_writing",
        description="Generate storyboard based on course script.",
        intent_description=(
            "当用户希望基于课程脚本，生成分镜脚本时使用。"
            "包含镜头、画面、字幕、讲解点、节奏。"
        ),
        input_schema={"course_script": "string"},
        trigger_keywords=["分镜", "分镜脚本", "生成分镜", "分镜设计"],
        prompt_template=_read_prompt("storyboard_writing.md"),
        output_filename="outputs/storyboard.md",
        output_type="text",
        requires_context=["course_script"],  # 需要 course_script 上下文
    ),
    # Skill 7: 分镜脚本评审
    Skill(
        name="storyboard_review",
        description="Review storyboard and provide feedback.",
        intent_description=(
            "当用户希望对已生成的分镜脚本进行评审时使用。"
            "输出评审结论与修改建议。"
        ),
        input_schema={"storyboard": "string"},
        trigger_keywords=["评审分镜", "分镜评审", "检查分镜", "分镜审查"],
        prompt_template=_read_prompt("storyboard_review.md"),
        output_filename="outputs/storyboard_review.md",
        output_type="text",
        requires_context=["storyboard"],  # 需要 storyboard 上下文
    ),
    # Workflow: 课程制作完整流程
    Skill(
        name="course_production_workflow",
        description="Complete course production workflow from goal definition to storyboard review.",
        intent_description=(
            "当用户希望完成完整的课程设计与制作流程时使用。"
            "系统自动按顺序执行所有步骤（目标确认→设计方案→评审→脚本→评审→分镜→评审）。"
        ),
        input_schema={"course_topic": "string", "target_audience": "string", "course_duration": "string(optional)"},
        trigger_keywords=["完整流程", "全流程", "制作课程", "课程制作", "完整课程"],
        prompt_template=_read_prompt("course_production_workflow.md"),
        output_filename="outputs/workflow_summary.md",
        output_type="text",
        requires_context=[],  # 不需要前置上下文
        skill_type="workflow",
        workflow_steps=[
            "course_goal_definition",
            "course_design_plan",
            "course_plan_review",
            "course_script_writing",
            "course_script_review",
            "storyboard_writing",
            "storyboard_review",
        ],
    ),
]


def skill_by_name(name: str) -> Skill | None:
    for skill in SKILLS:
        if skill.name == name:
            return skill
    return None
