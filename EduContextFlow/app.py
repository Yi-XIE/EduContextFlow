import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Load .env file manually
env_path = ".env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

from bus import GlobalStateBus
from dispatcher import dispatch
from executor import execute_skill
from skills import SKILLS, skill_by_name


MAX_CONTEXT_CHARS = 8000


class ContextMissingError(RuntimeError):
    def __init__(self, missing_types: list[str]):
        self.missing_types = missing_types
        missing = ", ".join(sorted(set(missing_types)))
        super().__init__(f"上下文文件缺失或读取失败：{missing}")


def _prepare_skill_input(skill, user_message: str, context_index: dict) -> str:
    """
    App 层负责：读取上下文 + 组装输入。
    
    Executor 只接收最终的 input_text，不做任何上下文读取。
    """
    if not skill.requires_context:
        # 不需要上下文，直接返回用户消息
        _log_context_trace(
            f"[prepare_input] skill={skill.name} requires_context=[] input=raw_user_message"
        )
        return user_message
    
    # 需要上下文：读取并组装
    parts = []
    missing_types = []
    for ctx_type in skill.requires_context:
        ctx_info = context_index.get(ctx_type)
        if not ctx_info:
            missing_types.append(ctx_type)
            continue

        ref_path = ctx_info.get("ref", "")
        if not ref_path or not os.path.exists(ref_path):
            missing_types.append(ctx_type)
            continue

        try:
            with open(ref_path, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                missing_types.append(ctx_type)
                continue
            if len(content) > MAX_CONTEXT_CHARS:
                content = content[:MAX_CONTEXT_CHARS] + "\n\n[内容已截断]\n"
                _log_context_trace(
                    f"[prepare_input] skill={skill.name} ctx={ctx_type} truncated_to={MAX_CONTEXT_CHARS}"
                )
            parts.append(f"=== {ctx_type} ===\n{content}\n")
            _log_context_trace(
                f"[prepare_input] skill={skill.name} ctx={ctx_type} ref={ref_path} bytes={len(content)}"
            )
        except Exception:
            missing_types.append(ctx_type)
    
    if missing_types:
        missing = ", ".join(sorted(set(missing_types)))
        _log_context_trace(
            f"[prepare_input] skill={skill.name} missing_context={missing}"
        )
        raise ContextMissingError(missing_types)

    # 组装：上下文 + 用户要求
    if parts:
        final_input = "\n".join(parts) + f"\n=== 用户要求 ===\n{user_message}"
        _log_context_trace(
            f"[prepare_input] skill={skill.name} final_input_bytes={len(final_input)}"
        )
        return final_input
    else:
        return user_message


# Skill output type 映射（固定枚举）
SKILL_OUTPUT_TYPES = {
    "course_goal_definition": "course_goal",
    "course_design_plan": "design_plan",
    "course_plan_review": "design_review",
    "course_script_writing": "course_script",
    "course_script_review": "script_review",
    "storyboard_writing": "storyboard",
    "storyboard_review": "storyboard_review",
    "course_production_workflow": "workflow_summary",
}

# Skill 描述映射
SKILL_DESCRIPTIONS = {
    "course_goal_definition": "课程目标与学习成果",
    "course_design_plan": "课程设计方案",
    "course_plan_review": "课程设计方案评审报告",
    "course_script_writing": "课程脚本",
    "course_script_review": "课程脚本评审报告",
    "storyboard_writing": "分镜脚本",
    "storyboard_review": "分镜脚本评审报告",
    "course_production_workflow": "课程制作完整流程",
}


app = Flask(__name__, static_folder="web", static_url_path="")
CORS(app)

UPLOAD_FOLDER = "uploads"
OUTPUTS_FOLDER = "outputs"
STATE_PATH = "state.json"
DISPATCHER_PROMPT = "DispatcherPrompt.md"
CONTEXT_TRACE_LOG = os.path.join(OUTPUTS_FOLDER, "context_trace.log")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUTS_FOLDER, exist_ok=True)


def _log_context_trace(message: str):
    """
    记录上下文链路追踪日志（用于排查“断层/未注入/吐提示词”问题）。
    """
    try:
        with open(CONTEXT_TRACE_LOG, "a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except Exception:
        pass


@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    message = request.form.get("message", "").strip()
    files = request.files.getlist("files")

    uploaded_files = []
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            uploaded_files.append(filepath)

    if not message and not uploaded_files:
        return jsonify({"error": "No message or files provided"}), 400

    bus = GlobalStateBus(STATE_PATH)
    state = bus.get_state()

    # 保存非空的用户输入到 bus（替代全局变量）
    if message:
        bus.set_pending_input(message)

    # 统一入口：所有请求都经过 Dispatcher
    result = dispatch(
        user_message=message,
        bus_state=state,
        skills=SKILLS,
        dispatcher_prompt_path=DISPATCHER_PROMPT,
        outputs_dir=OUTPUTS_FOLDER,
    )
    _log_context_trace(
        f"[dispatch] action={result.get('action')} skill={result.get('skill_name')} reason={result.get('reason')}"
    )

    action = result.get("action")
    reply = ""
    output_files = []
    options = []

    if action == "call_skill":
        skill_name = result.get("skill_name")
        skill = skill_by_name(skill_name)
        if not skill:
            bus.set_error()
            return jsonify({"error": f"Unknown skill: {skill_name}"}), 500

        bus.set_stage("skill_selected")
        bus.set_selected_skill(skill.name)
        bus.mark_skill_running(skill.name)

        try:
            # App 层读取上下文并组装输入
            context_index = state.get("context_index", {})
            input_text = _prepare_skill_input(skill, message, context_index)
        except ContextMissingError as exc:
            # 上下文文件缺失/读取失败，返回 ask_user，保留 pending_user_input
            bus.mark_skill_error(skill.name)
            return jsonify({
                "reply": str(exc),
                "output_files": [],
                "options": [],
                "bus_state": bus.get_state(),
            }), 200

        try:
            # Executor 只接收最终输入
            output_path = execute_skill(skill, input_text)
            bus.mark_skill_done(
                skill.name,
                output_path,
                SKILL_OUTPUT_TYPES.get(skill.name, "unknown"),
                SKILL_DESCRIPTIONS.get(skill.name, skill.description)
            )
            
            # Skill 已消耗用户输入，清空 pending_user_input（语义锁）
            bus.clear_pending_input()
            
            reply = ""
            output_files.append(output_path)
        except Exception as exc:
            output_type = SKILL_OUTPUT_TYPES.get(skill.name)
            bus.mark_skill_error(skill.name, output_type)
            return jsonify({"error": f"Skill execution failed: {exc}"}), 500

    elif action == "ask_user":
        reply = result.get("question", "需要更多信息")
        options = result.get("options", [])
        if options:
            reply += "\n\n选项：\n" + "\n".join(f"- {opt}" for opt in options)

    elif action == "no_action":
        reply = result.get("reason", "当前输入不涉及任何任务")
        bus.clear_pending_input()  # 输入已处理，清空

    elif action == "refuse":
        reply = result.get("reason", "当前请求无法处理")
        bus.clear_pending_input()  # 输入已处理，清空

    else:
        bus.set_error()
        return jsonify({"error": "Invalid dispatcher response"}), 500

    return jsonify({
        "reply": reply,
        "output_files": output_files,
        "options": options,
        "bus_state": bus.get_state(),
    })


@app.route("/outputs/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUTS_FOLDER, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
