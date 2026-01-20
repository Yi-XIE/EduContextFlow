import json
import os
import uuid
from datetime import datetime


DEFAULT_SKILLS = {
    "course_goal_definition": {"status": "empty"},
    "course_design_plan": {"status": "empty"},
    "course_plan_review": {"status": "empty"},
    "course_script_writing": {"status": "empty"},
    "course_script_review": {"status": "empty"},
    "storyboard_writing": {"status": "empty"},
    "storyboard_review": {"status": "empty"},
    "course_production_workflow": {"status": "empty"},
}


def _default_state():
    """
    初始化默认总线状态。
    
    pending_user_input 语义规则：
    - 仅存储"尚未被任何 Skill 消耗"的用户原文
    - 在 Skill 成功执行后必须清空
    - 在 ask_user 返回后可被覆盖
    - 禁止存储历史多轮输入，只存储当前轮次
    """
    return {
        "session_id": str(uuid.uuid4()),
        "stage": "idle",
        "selected_skill": None,
        "skills": json.loads(json.dumps(DEFAULT_SKILLS)),
        "context_index": {},  # 语义上下文索引：key=类型, value={ref, producer, status}
        "last_output_ref": None,
        "pending_user_input": None,  # 当前轮次待消耗的用户输入（语义锁）
    }


class GlobalStateBus:
    def __init__(self, path: str):
        self.path = path
        self._state = None
        self._load_or_init()

    def _load_or_init(self):
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self._state = json.load(f)
        else:
            self._state = _default_state()
            self._persist()
        self._ensure_skills()

    def _ensure_skills(self):
        if "skills" not in self._state or not isinstance(self._state["skills"], dict):
            self._state["skills"] = json.loads(json.dumps(DEFAULT_SKILLS))
        for name, value in DEFAULT_SKILLS.items():
            if name not in self._state["skills"]:
                self._state["skills"][name] = value
        self._persist()

    def _persist(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=True)

    def get_state(self):
        return json.loads(json.dumps(self._state))

    def set_stage(self, stage: str):
        self._state["stage"] = stage
        self._persist()

    def set_selected_skill(self, skill_name: str | None):
        self._state["selected_skill"] = skill_name
        self._persist()

    def _get_timestamp(self) -> str:
        """获取当前时间的 ISO 格式字符串"""
        return datetime.now().isoformat()

    def set_skill_status(self, skill_name: str, status: str):
        """
        设置 Skill 的状态。
        
        status 可选值: "empty" | "running" | "done" | "error" | "skipped"
        """
        if skill_name in self._state["skills"]:
            self._state["skills"][skill_name]["status"] = status
            self._persist()

    def mark_skill_done(
        self,
        skill_name: str,
        output_ref: str,
        output_type: str,
        description: str,
    ):
        """标记 Skill 完成，并更新 context_index"""
        if skill_name in self._state["skills"]:
            self._state["skills"][skill_name]["status"] = "done"

        # 写入语义上下文索引（字典结构）
        now = self._get_timestamp()
        context_entry = {
            "ref": output_ref,
            "producer": skill_name,
            "status": "ready",
            "description": description,
            "created_at": now,
            "updated_at": now,
        }
        
        # 如果已存在，保留 created_at，只更新 updated_at
        existing = self._state.setdefault("context_index", {}).get(output_type)
        if existing and "created_at" in existing:
            context_entry["created_at"] = existing["created_at"]
        
        self._state["context_index"][output_type] = context_entry

        self._state["last_output_ref"] = output_ref
        self._state["stage"] = "skill_done"
        self._persist()

    def mark_skill_running(self, skill_name: str):
        """标记 Skill 正在运行"""
        self.set_skill_status(skill_name, "running")
        if self._state["selected_skill"] != skill_name:
            self.set_selected_skill(skill_name)

    def mark_skill_error(self, skill_name: str, output_type: str | None = None):
        """标记 Skill 执行失败"""
        self.set_skill_status(skill_name, "error")
        self._state["stage"] = "error"
        
        # 如果提供了 output_type，更新 context_index 状态为 failed
        if output_type:
            if output_type in self._state.get("context_index", {}):
                self._state["context_index"][output_type]["status"] = "failed"
                self._state["context_index"][output_type]["updated_at"] = self._get_timestamp()
        
        self._persist()

    def mark_skill_skipped(self, skill_name: str):
        """标记 Skill 被跳过"""
        self.set_skill_status(skill_name, "skipped")
        self._persist()

    def update_context_status(
        self, 
        context_type: str, 
        status: str, 
        description: str | None = None
    ):
        """
        更新 context_index 中某个上下文的状态。
        
        status 可选值: "pending" | "ready" | "failed"
        """
        if context_type not in self._state.setdefault("context_index", {}):
            # 如果不存在，创建一个基础条目
            self._state["context_index"][context_type] = {
                "ref": "",
                "producer": "",
                "status": status,
                "description": description or "",
                "created_at": self._get_timestamp(),
                "updated_at": self._get_timestamp(),
            }
        else:
            # 更新现有条目
            entry = self._state["context_index"][context_type]
            entry["status"] = status
            entry["updated_at"] = self._get_timestamp()
            if description is not None:
                entry["description"] = description
        
        self._persist()

    def set_pending_input(self, user_input: str | None):
        """
        设置当前轮次的待消耗用户输入。
        
        规则：
        - 仅在接收到新的用户消息时调用
        - 在 ask_user 返回后可覆盖（新一轮输入）
        - 不存储多轮历史
        """
        self._state["pending_user_input"] = user_input
        self._persist()

    def get_pending_input(self) -> str | None:
        """获取当前轮次的待消耗用户输入"""
        return self._state.get("pending_user_input")
    
    def clear_pending_input(self):
        """
        清空待消耗的用户输入。
        
        必须在以下情况调用：
        - Skill 成功执行完毕（输入已被消耗）
        - 返回 no_action 或 refuse（输入已被处理）
        """
        self._state["pending_user_input"] = None
        self._persist()

    def set_error(self):
        """设置全局错误状态"""
        self._state["stage"] = "error"
        self._persist()
