import argparse
import sys

from bus import GlobalStateBus
from dispatcher import dispatch
from executor import execute_skill
from skills import SKILLS, skill_by_name


def _read_input(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise ValueError("No user input provided.")


def run():
    parser = argparse.ArgumentParser(description="LLM dispatcher MVP")
    parser.add_argument("--text", help="User input text")
    parser.add_argument(
        "--dispatcher-prompt",
        default="DispatcherPrompt.md",
        help="Dispatcher prompt path",
    )
    parser.add_argument(
        "--state-path",
        default="state.json",
        help="Global state bus path",
    )
    parser.add_argument(
        "--outputs-dir",
        default="outputs",
        help="Outputs directory",
    )
    args = parser.parse_args()

    user_message = _read_input(args)
    bus = GlobalStateBus(args.state_path)
    state = bus.get_state()

    result = dispatch(
        user_message=user_message,
        bus_state=state,
        skills=SKILLS,
        dispatcher_prompt_path=args.dispatcher_prompt,
        outputs_dir=args.outputs_dir,
    )

    action = result.get("action")
    if action == "call_skill":
        skill_name = result.get("skill_name")
        skill = skill_by_name(skill_name)
        if not skill:
            bus.set_error()
            print(f"Unknown skill: {skill_name}")
            return
        bus.set_stage("skill_selected")
        bus.set_selected_skill(skill.name)
        bus.mark_skill_running(skill.name)
        try:
            output_path = execute_skill(skill, user_message)
        except Exception as exc:
            # 简化版：根据 skill.output_type 推断 output_type
            output_type = skill.output_type if hasattr(skill, 'output_type') else "unknown"
            bus.mark_skill_error(skill.name, output_type)
            print(f"Skill execution failed: {exc}")
            return
        # 简化版：使用 skill 的基本信息
        output_type = skill.output_type if hasattr(skill, 'output_type') else "unknown"
        description = skill.description if hasattr(skill, 'description') else skill.name
        bus.mark_skill_done(skill.name, output_path, output_type, description)
        print(f"Skill done. Output: {output_path}")
        return

    if action == "ask_user":
        print(result.get("question", "Need more information."))
        options = result.get("options", [])
        if options:
            print("Options:")
            for option in options:
                print(f"- {option}")
        return

    if action == "no_action":
        print(result.get("reason", "No action."))
        return

    print("Invalid dispatcher response.")
    bus.set_error()


if __name__ == "__main__":
    run()
