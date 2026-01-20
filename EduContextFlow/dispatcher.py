import json
import os
from typing import Any

from llm import LLMClient, parse_json
from skills import Skill, skill_by_name


def _bus_summary(bus_state: dict[str, Any], outputs_dir: str) -> dict[str, Any]:
    """
    构建给 Dispatcher 的总线摘要。
    只传递语义类型和元信息，不传递文件内容。
    """
    context_index = bus_state.get("context_index", {})
    
    # 只传递类型键，不传递具体引用
    available_types = list(context_index.keys())
    
    return {
        "stage": bus_state.get("stage", "idle"),
        "context_index": context_index,  # 完整的索引信息
        "available_types": available_types,  # 快速查询：有哪些类型可用
    }


def _validate_skill_requirements(
    skill: Skill, 
    context_index: dict[str, Any]
) -> tuple[bool, str]:
    """
    硬约束校验：检查 skill 的上下文依赖是否满足。
    
    Returns:
        (is_valid, reason)
    """
    required_contexts = skill.requires_context
    available_types = set(context_index.keys())
    
    for required_type in required_contexts:
        if required_type not in available_types:
            return False, f"缺少必需的上下文：{required_type}"
        
        # 检查状态是否 ready
        ctx = context_index.get(required_type, {})
        if ctx.get("status") != "ready":
            return False, f"上下文 {required_type} 尚未就绪"
    
    return True, ""


def _heuristic_dispatch(user_message: str, skills: list[Skill]) -> dict[str, Any]:
    matches = []
    lowered = user_message.lower()
    for skill in skills:
        skill_name = skill.name.lower()
        if skill_name in lowered or skill_name.replace("_", " ") in lowered:
            matches.append(skill)
            continue
        for kw in skill.trigger_keywords:
            if kw.lower() in lowered:
                matches.append(skill)
                break
    if len(matches) > 1:
        return {
            "action": "ask_user",
            "question": "Multiple skills match. Which one should I run?",
            "options": [m.name for m in matches],
        }
    if len(matches) == 1:
        return {
            "action": "ask_user",
            "question": "我理解你可能想执行下面的任务，请确认是否正确。",
            "options": [matches[0].name],
        }
    return {
        "action": "ask_user",
        "question": "我不确定你要做哪种任务，请简单描述你的目标。",
        "options": [],
    }


def dispatch(
    user_message: str,
    bus_state: dict[str, Any],
    skills: list[Skill],
    dispatcher_prompt_path: str,
    outputs_dir: str,
) -> dict[str, Any]:
    with open(dispatcher_prompt_path, "r", encoding="utf-8") as f:
        prompt = f.read().strip()

    bus_info = _bus_summary(bus_state, outputs_dir)
    skills_info = [
        {
            "name": s.name,
            "description": s.description,
            "intent_description": s.intent_description,
            "input_schema": s.input_schema,
            "output_type": s.output_type,
            "requires_context": s.requires_context,  # 添加上下文依赖信息
        }
        for s in skills
    ]
    
    # 添加硬约束规则
    constraint_rules = """
【硬约束规则 - MUST FOLLOW】

1. You may ONLY call a skill if ALL its required_context types are present in bus_state.context_index
2. If context_index does NOT contain required input types, you MUST return action="ask_user"
3. You MUST NOT infer missing context from user_message alone
4. Check requires_context field of each skill BEFORE calling it

Example:
- script_from_transcript requires_context=["transcript"]
- If context_index does NOT have "transcript", you CANNOT call script_from_transcript
- You must ask_user to generate transcript first
"""
    
    full_prompt = (
        f"{prompt}\n\n"
        f"{constraint_rules}\n\n"
        f"available_skills:\n{json.dumps(skills_info, ensure_ascii=False, indent=2)}\n\n"
        f"user_message:\n{user_message}\n\n"
        f"bus_state:\n{json.dumps(bus_info, ensure_ascii=False, indent=2)}\n"
    )

    llm = LLMClient()
    for _ in range(2):
        try:
            response = llm.complete(full_prompt)
            parsed = parse_json(response)
            if parsed is not None:
                # 【硬约束校验】在 Python 侧校验 LLM 的决策
                action = parsed.get("action")
                if action == "call_skill":
                    skill_name = parsed.get("skill_name")
                    skill = skill_by_name(skill_name)
                    
                    if skill:
                        context_index = bus_state.get("context_index", {})
                        is_valid, reason = _validate_skill_requirements(skill, context_index)
                        
                        if not is_valid:
                            # 校验失败，强制改为 ask_user
                            return {
                                "action": "ask_user",
                                "question": f"无法执行 {skill_name}：{reason}。请先完成前置步骤。",
                                "options": [],
                            }
                
                return parsed
        except Exception:
            break

    return _heuristic_dispatch(user_message, skills)
