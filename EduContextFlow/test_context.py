#!/usr/bin/env python3
"""
上下文关联与隔离能力测试

测试目标：
1. 上下文关联：context_index 中有依赖时，能否正确调用 Skill
2. 上下文隔离：缺少依赖时，Dispatcher 能否正确拒绝并 ask_user
3. 语义锁：pending_user_input 生命周期是否正确
"""

import json
import os
import sys
from typing import Any

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env 文件
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


class ContextTester:
    def __init__(self):
        self.test_state_path = "test_state.json"
        self.test_outputs_dir = "test_outputs"
        self.dispatcher_prompt = "DispatcherPrompt.md"
        
        # 清理测试环境
        if os.path.exists(self.test_state_path):
            os.remove(self.test_state_path)
        if os.path.exists(self.test_outputs_dir):
            import shutil
            shutil.rmtree(self.test_outputs_dir)
        os.makedirs(self.test_outputs_dir, exist_ok=True)
        
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def log_test(self, name: str, passed: bool, reason: str = ""):
        """记录测试结果"""
        status = "✅ PASS" if passed else "❌ FAIL"
        msg = f"{status} - {name}"
        if reason:
            msg += f"\n    理由: {reason}"
        print(msg)
        
        self.results.append({
            "name": name,
            "passed": passed,
            "reason": reason
        })
        
        if passed:
            self.passed += 1
        else:
            self.failed += 1
    
    def test_1_initial_isolation(self):
        """测试 1：初始状态下，无上下文时应拒绝依赖型 Skill"""
        print("\n" + "=" * 60)
        print("📋 测试 1：上下文隔离 - 缺少依赖时的拒绝机制")
        print("=" * 60)
        
        bus = GlobalStateBus(self.test_state_path)
        state = bus.get_state()
        
        # 确认 context_index 为空
        context_index = state.get("context_index", {})
        if context_index:
            self.log_test("初始状态检查", False, f"context_index 应为空，但包含: {list(context_index.keys())}")
            return
        
        self.log_test("初始状态检查", True, "context_index 为空")
        
        # 尝试请求生成脚本（需要 transcript 依赖）
        bus.set_pending_input("把刚才的逐字稿整理成脚本")
        
        result = dispatch(
            user_message="把刚才的逐字稿整理成脚本",
            bus_state=state,
            skills=SKILLS,
            dispatcher_prompt_path=self.dispatcher_prompt,
            outputs_dir=self.test_outputs_dir,
        )
        
        action = result.get("action")
        skill_name = result.get("skill_name")
        
        # 应该返回 ask_user，而不是 call_skill
        if action == "ask_user":
            self.log_test("Dispatcher 正确拒绝", True, f"返回 ask_user: {result.get('question', '')}")
        elif action == "call_skill":
            self.log_test("Dispatcher 正确拒绝", False, f"错误地返回了 call_skill: {skill_name}")
        else:
            self.log_test("Dispatcher 正确拒绝", False, f"未知 action: {action}")
        
        # 检查 pending_user_input 是否保留（ask_user 时应保留）
        state_after = bus.get_state()
        pending = state_after.get("pending_user_input")
        if pending:
            self.log_test("ask_user 时保留 pending_input", True, f"pending_user_input = {pending}")
        else:
            self.log_test("ask_user 时保留 pending_input", False, "pending_user_input 被错误清空")
    
    def test_2_context_association(self):
        """测试 2：建立上下文后，依赖型 Skill 应能正确调用"""
        print("\n" + "=" * 60)
        print("📋 测试 2：上下文关联 - 依赖满足时的正确调用")
        print("=" * 60)
        
        bus = GlobalStateBus(self.test_state_path)
        
        # 步骤 1：生成逐字稿（建立 transcript 上下文）
        print("\n🔹 步骤 1：生成逐字稿")
        bus.set_pending_input("帮我生成一段讲解光合作用的逐字稿")
        
        state = bus.get_state()
        result = dispatch(
            user_message="帮我生成一段讲解光合作用的逐字稿",
            bus_state=state,
            skills=SKILLS,
            dispatcher_prompt_path=self.dispatcher_prompt,
            outputs_dir=self.test_outputs_dir,
        )
        
        # 处理两种情况：直接 call_skill 或 ask_user 确认
        if result.get("action") == "call_skill" and result.get("skill_name") == "transcript_generation":
            self.log_test("步骤 1：Dispatcher 识别逐字稿生成", True, "直接识别 transcript_generation")
        elif result.get("action") == "ask_user" and "transcript_generation" in result.get("options", []):
            self.log_test("步骤 1：Dispatcher 识别逐字稿生成", True, "请求确认（启发式匹配）")
            # 模拟用户确认，强制调用
            result = {"action": "call_skill", "skill_name": "transcript_generation"}
        else:
            self.log_test("步骤 1：Dispatcher 识别逐字稿生成", False, f"未正确识别，返回: {result}")
            return
        
        # 执行逐字稿生成
        skill = skill_by_name("transcript_generation")
        try:
            output_path = execute_skill(skill, "讲解光合作用")
            bus.mark_skill_done(
                skill.name,
                output_path,
                "transcript",
                "教学逐字稿"
            )
            bus.clear_pending_input()
            self.log_test("步骤 1：执行逐字稿生成", True, f"生成文件: {output_path}")
        except Exception as e:
            self.log_test("步骤 1：执行逐字稿生成", False, str(e))
            return
        
        # 步骤 2：检查 context_index
        print("\n🔹 步骤 2：检查上下文索引")
        state = bus.get_state()
        context_index = state.get("context_index", {})
        
        if "transcript" in context_index:
            transcript_ctx = context_index["transcript"]
            self.log_test("步骤 2：transcript 已写入 context_index", True, 
                         f"ref={transcript_ctx.get('ref')}, status={transcript_ctx.get('status')}")
            
            # 检查文件是否存在
            ref_path = transcript_ctx.get("ref", "")
            if os.path.exists(ref_path):
                with open(ref_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if len(content) > 50:
                    self.log_test("步骤 2：逐字稿文件有效", True, f"文件大小: {len(content)} 字符")
                else:
                    self.log_test("步骤 2：逐字稿文件有效", False, "文件内容过短")
            else:
                self.log_test("步骤 2：逐字稿文件存在", False, f"文件不存在: {ref_path}")
        else:
            self.log_test("步骤 2：transcript 已写入 context_index", False, 
                         f"context_index 中无 transcript: {list(context_index.keys())}")
            return
        
        # 步骤 3：请求基于逐字稿生成脚本（应该成功）
        print("\n🔹 步骤 3：基于逐字稿生成脚本")
        bus.set_pending_input("把这个逐字稿整理成表格脚本")
        
        result = dispatch(
            user_message="把这个逐字稿整理成表格脚本",
            bus_state=state,
            skills=SKILLS,
            dispatcher_prompt_path=self.dispatcher_prompt,
            outputs_dir=self.test_outputs_dir,
        )
        
        action = result.get("action")
        skill_name = result.get("skill_name")
        
        # 处理两种情况：直接 call_skill 或 ask_user 确认
        if action == "call_skill" and skill_name == "script_from_transcript":
            self.log_test("步骤 3：Dispatcher 正确调用脚本生成", True, "识别到依赖已满足")
        elif action == "ask_user" and "script_from_transcript" in result.get("options", []):
            self.log_test("步骤 3：Dispatcher 正确调用脚本生成", True, "请求确认（启发式匹配）")
            # 模拟用户确认，强制调用
            skill_name = "script_from_transcript"
        elif action == "ask_user":
            self.log_test("步骤 3：Dispatcher 正确调用脚本生成", False, 
                         f"错误地返回 ask_user（非确认）: {result.get('question')}")
            return
        else:
            self.log_test("步骤 3：Dispatcher 正确调用脚本生成", False, 
                         f"未知返回: action={action}, skill={skill_name}")
            return
        
        # 执行脚本生成
        script_skill = skill_by_name("script_from_transcript")
        try:
            # 模拟 App 层的上下文组装
            transcript_path = context_index["transcript"]["ref"]
            with open(transcript_path, "r", encoding="utf-8") as f:
                transcript_content = f.read()
            
            input_text = f"=== transcript ===\n{transcript_content}\n\n=== 用户要求 ===\n整理成表格脚本"
            
            script_output = execute_skill(script_skill, input_text)
            bus.mark_skill_done(
                script_skill.name,
                script_output,
                "script",
                "表格化教学视频脚本"
            )
            bus.clear_pending_input()
            self.log_test("步骤 3：执行脚本生成", True, f"生成文件: {script_output}")
            
            # 检查脚本内容是否引用了逐字稿
            with open(script_output, "r", encoding="utf-8") as f:
                script_content = f.read()
            
            if len(script_content) > 50:
                self.log_test("步骤 3：脚本内容有效", True, f"文件大小: {len(script_content)} 字符")
            else:
                self.log_test("步骤 3：脚本内容有效", False, "脚本内容过短")
        except Exception as e:
            self.log_test("步骤 3：执行脚本生成", False, str(e))
            return
        
        # 步骤 4：验证 pending_user_input 已清空
        print("\n🔹 步骤 4：验证语义锁")
        state_final = bus.get_state()
        pending_final = state_final.get("pending_user_input")
        
        if pending_final is None:
            self.log_test("步骤 4：pending_input 已清空", True, "Skill 执行后正确清空")
        else:
            self.log_test("步骤 4：pending_input 已清空", False, f"未清空: {pending_final}")
    
    def test_3_python_validation(self):
        """测试 3：Python 侧硬约束校验"""
        print("\n" + "=" * 60)
        print("📋 测试 3：Python 硬约束 - LLM 决策错误时的拦截")
        print("=" * 60)
        
        bus = GlobalStateBus(self.test_state_path)
        
        # 清空 context_index，模拟 LLM 错误决策
        bus._state["context_index"] = {}
        bus._persist()
        
        state = bus.get_state()
        
        # 手动构造一个"错误的 LLM 决策"（绕过 LLM，直接测试校验逻辑）
        print("\n🔹 模拟 LLM 错误决策：在无 transcript 时调用 script_from_transcript")
        
        from dispatcher import _validate_skill_requirements
        
        script_skill = skill_by_name("script_from_transcript")
        context_index = state.get("context_index", {})
        
        is_valid, reason = _validate_skill_requirements(script_skill, context_index)
        
        if not is_valid:
            self.log_test("Python 校验拦截", True, f"正确拦截: {reason}")
        else:
            self.log_test("Python 校验拦截", False, "校验未能拦截错误决策")
    
    def test_4_lifecycle_management(self):
        """测试 4：pending_user_input 生命周期管理"""
        print("\n" + "=" * 60)
        print("📋 测试 4：语义锁生命周期 - pending_user_input 管理")
        print("=" * 60)
        
        bus = GlobalStateBus(self.test_state_path)
        
        # 测试 set_pending_input
        print("\n🔹 测试 set_pending_input")
        bus.set_pending_input("测试输入")
        state = bus.get_state()
        pending = state.get("pending_user_input")
        
        if pending == "测试输入":
            self.log_test("set_pending_input", True, "输入已保存")
        else:
            self.log_test("set_pending_input", False, f"保存失败: {pending}")
        
        # 测试 clear_pending_input
        print("\n🔹 测试 clear_pending_input")
        bus.clear_pending_input()
        state = bus.get_state()
        pending = state.get("pending_user_input")
        
        if pending is None:
            self.log_test("clear_pending_input", True, "输入已清空")
        else:
            self.log_test("clear_pending_input", False, f"清空失败: {pending}")
        
        # 测试覆盖（模拟 ask_user 后的新输入）
        print("\n🔹 测试覆盖（ask_user 后的新输入）")
        bus.set_pending_input("第一轮输入")
        bus.set_pending_input("第二轮输入")  # 覆盖
        state = bus.get_state()
        pending = state.get("pending_user_input")
        
        if pending == "第二轮输入":
            self.log_test("pending_input 覆盖", True, "新输入覆盖旧输入")
        else:
            self.log_test("pending_input 覆盖", False, f"覆盖失败: {pending}")
    
    def test_5_new_task_isolation(self):
        """测试 5：新任务不被旧上下文污染"""
        print("\n" + "=" * 60)
        print("📋 测试 5：新任务隔离 - 独立任务不受历史上下文污染")
        print("=" * 60)
        
        bus = GlobalStateBus(self.test_state_path)
        
        # 步骤 1：先建立一些历史上下文（transcript + script）
        print("\n🔹 步骤 1：建立历史上下文（transcript + script）")
        
        # 模拟已有的 transcript
        transcript_path = os.path.join(self.test_outputs_dir, "test_transcript.md")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write("# 光合作用教学逐字稿\n\n同学们好，今天我们来学习光合作用...")
        
        bus._state["context_index"]["transcript"] = {
            "ref": transcript_path,
            "producer": "transcript_generation",
            "status": "ready",
            "description": "教学逐字稿"
        }
        
        # 模拟已有的 script
        script_path = os.path.join(self.test_outputs_dir, "test_script.md")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write("| 时间轴 | 画面 | 旁白 |\n|--------|------|------|\n| 0:00 | 标题 | 光合作用 |")
        
        bus._state["context_index"]["script"] = {
            "ref": script_path,
            "producer": "script_from_transcript",
            "status": "ready",
            "description": "表格化教学视频脚本"
        }
        bus._persist()
        
        context_before = list(bus.get_state()["context_index"].keys())
        self.log_test("步骤 1：历史上下文建立", True, 
                     f"已有上下文: {context_before}")
        
        # 步骤 2：用户发起独立的图像生成任务
        print("\n🔹 步骤 2：发起独立的图像生成任务")
        bus.set_pending_input("帮我生成一张森林的图片")
        
        state = bus.get_state()
        result = dispatch(
            user_message="帮我生成一张森林的图片",
            bus_state=state,
            skills=SKILLS,
            dispatcher_prompt_path=self.dispatcher_prompt,
            outputs_dir=self.test_outputs_dir,
        )
        
        action = result.get("action")
        skill_name = result.get("skill_name")
        
        # 应该识别为图像生成，不依赖历史上下文
        if action == "call_skill" and skill_name == "image_generation":
            self.log_test("步骤 2：识别独立任务", True, "正确识别 image_generation")
        elif action == "ask_user" and "image_generation" in result.get("options", []):
            self.log_test("步骤 2：识别独立任务", True, "请求确认 image_generation")
            skill_name = "image_generation"
        else:
            self.log_test("步骤 2：识别独立任务", False, 
                         f"未识别图像生成: action={action}, skill={skill_name}")
            return
        
        # 步骤 3：执行图像生成，验证不使用 transcript
        print("\n🔹 步骤 3：执行图像生成，验证输入独立性")
        
        image_skill = skill_by_name("image_generation")
        
        # 关键：App 层准备输入时，不应该读取 transcript/script
        context_index = state.get("context_index", {})
        input_text = "帮我生成一张森林的图片"  # 独立任务，不组装历史上下文
        
        # 验证 image_generation 的 requires_context 为空
        if not image_skill.requires_context:
            self.log_test("步骤 3：image_generation 无上下文依赖", True, 
                         f"requires_context = {image_skill.requires_context}")
        else:
            self.log_test("步骤 3：image_generation 无上下文依赖", False, 
                         f"错误地依赖了: {image_skill.requires_context}")
        
        try:
            # 调试信息
            print(f"    调试: input_text = {input_text}")
            print(f"    调试: skill.output_type = {image_skill.output_type}")
            print(f"    调试: skill.prompt_template 前50字符 = {image_skill.prompt_template[:50]}")
            
            # 执行图像生成
            output_path = execute_skill(image_skill, input_text)
            bus.mark_skill_done(
                image_skill.name,
                output_path,
                "image",
                "教学插图"
            )
            bus.clear_pending_input()
            
            self.log_test("步骤 3：执行图像生成", True, f"生成文件: {output_path}")
            
            # 步骤 4：验证生成的图像提示词不包含 transcript 内容
            print("\n🔹 步骤 4：验证输出独立性（无污染）")
            
            # 读取图像提示词
            prompt_file = output_path.replace(".png", "_prompt.txt")
            if os.path.exists(prompt_file):
                with open(prompt_file, "r", encoding="utf-8") as f:
                    image_prompt = f.read()
                
                # 检查是否包含 transcript 关键词（光合作用、同学们）
                pollution_keywords = ["光合作用", "同学们", "教学", "旁白"]
                has_pollution = any(kw in image_prompt for kw in pollution_keywords)
                
                if not has_pollution and "森林" in image_prompt:
                    self.log_test("步骤 4：图像提示词独立", True, 
                                 f"提示词聚焦用户需求，无历史污染")
                elif has_pollution:
                    self.log_test("步骤 4：图像提示词独立", False, 
                                 f"提示词被污染，包含历史关键词: {image_prompt[:100]}")
                else:
                    self.log_test("步骤 4：图像提示词独立", True, 
                                 f"提示词: {image_prompt[:100]}")
            else:
                self.log_test("步骤 4：检查提示词文件", False, f"提示词文件不存在: {prompt_file}")
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.log_test("步骤 3：执行图像生成", False, f"{str(e)}\n{error_detail}")
            return
        
        # 步骤 5：验证 context_index 正确更新
        print("\n🔹 步骤 5：验证上下文索引独立性")
        
        state_final = bus.get_state()
        context_final = state_final.get("context_index", {})
        
        # 应该同时存在 transcript, script, image（互不影响）
        expected_types = ["transcript", "script", "image"]
        actual_types = list(context_final.keys())
        
        if all(t in actual_types for t in expected_types):
            self.log_test("步骤 5：多上下文共存", True, 
                         f"context_index 包含: {actual_types}")
        else:
            self.log_test("步骤 5：多上下文共存", False, 
                         f"缺失类型，期望: {expected_types}, 实际: {actual_types}")
        
        # 验证 image 的 producer 正确
        if context_final.get("image", {}).get("producer") == "image_generation":
            self.log_test("步骤 5：image 上下文元信息正确", True, 
                         f"producer = image_generation")
        else:
            self.log_test("步骤 5：image 上下文元信息正确", False, 
                         f"producer 错误: {context_final.get('image', {})}")
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "🧪" * 30)
        print("EduContextFlow 上下文能力测试套件")
        print("🧪" * 30)
        
        try:
            self.test_1_initial_isolation()
            self.test_2_context_association()
            self.test_3_python_validation()
            self.test_4_lifecycle_management()
            self.test_5_new_task_isolation()  # 新增测试
        except Exception as e:
            print(f"\n❌ 测试过程中发生异常: {e}")
            import traceback
            traceback.print_exc()
        
        # 输出总结
        print("\n" + "=" * 60)
        print("📊 测试总结")
        print("=" * 60)
        print(f"✅ 通过: {self.passed}")
        print(f"❌ 失败: {self.failed}")
        print(f"📈 通过率: {self.passed / (self.passed + self.failed) * 100:.1f}%")
        
        if self.failed == 0:
            print("\n🎉 所有测试通过！架构正确！")
        else:
            print(f"\n⚠️  有 {self.failed} 个测试失败，请检查架构。")
        
        # 清理测试文件
        print("\n🧹 清理测试环境...")
        if os.path.exists(self.test_state_path):
            os.remove(self.test_state_path)
        
        return self.failed == 0


if __name__ == "__main__":
    tester = ContextTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)

