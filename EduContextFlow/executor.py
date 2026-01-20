import base64
import os

from llm import LLMClient
from skills import Skill


_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA"
    "ASsJTYQAAAAASUVORK5CYII="
)


def _ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def _clean_llm_output(raw_output: str, original_input: str) -> str:
    """
    清理 LLM 输出，移除可能被复述的 Prompt 模板内容。
    只保留实际生成的内容。
    """
    output = raw_output.strip()
    
    # 阶段 1：移除常见的 LLM 复述开头
    bad_starts = [
        "好的，这是根据",
        "好的，我来",
        "好的，以下是",
        "根据您的要求",
        "这是为您",
        "以下是根据",
        "## Prompt 模板",
        "## 输出要求",
        "===教学内容===",
        "===用户需求===",
    ]
    
    for bad_start in bad_starts:
        if bad_start in output:
            # 找到这些标记后的内容
            idx = output.find(bad_start)
            if idx < 100:  # 如果在开头附近（前100字符内）
                # 尝试跳过这部分
                after_marker = output[idx:]
                # 找到第一个看起来像实际内容的部分
                lines = after_marker.split('\n')
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    # 跳过空行、标题、分隔符
                    if not stripped or stripped.startswith('#') or stripped.startswith('=') or stripped.startswith('-'):
                        continue
                    # 跳过包含 "Prompt"、"模板"、"要求" 等元描述的行
                    if any(kw in stripped for kw in ['Prompt', '模板', 'Template', '要求', 'Requirements', '{{', '}}']):
                        continue
                    # 找到第一行看起来像实际内容的行
                    if stripped and (stripped[0].isdigit() or len(stripped) > 10):
                        output = '\n'.join(lines[i:]).strip()
                        break
    
    # 阶段 2：如果输出包含用户输入的完整内容，说明 LLM 可能复述了 prompt
    if original_input in output:
        # 找到用户输入最后出现的位置
        last_idx = output.rfind(original_input)
        if last_idx != -1:
            # 截取用户输入之后的内容
            after_input = output[last_idx + len(original_input):].strip()
            
            # 如果后面还有实质内容，返回它
            if after_input:
                # 移除可能的分隔符和说明文字
                lines = after_input.split('\n')
                content_start = 0
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    # 跳过分隔符、说明性文字
                    if stripped in ['===', '============', '==========', '---', '现在请直接输出', '要求：']:
                        content_start = i + 1
                    elif stripped.startswith('现在请') or stripped.startswith('要求') or stripped.startswith('==='):
                        content_start = i + 1
                    elif stripped and not stripped.startswith('=') and not stripped.startswith('-'):
                        # 找到第一行实质内容
                        break
                
                cleaned = '\n'.join(lines[content_start:]).strip()
                if cleaned:
                    return cleaned
    
    # 阶段 3：移除纯元描述内容（如果整个输出都是模板说明）
    lines = output.split('\n')
    real_content_lines = []
    in_meta_section = True
    
    for line in lines:
        stripped = line.strip()
        
        # 跳过空行
        if not stripped:
            continue
        
        # 检查是否是元描述（模板、说明、要求等）
        is_meta = (
            stripped.startswith('#') or 
            stripped.startswith('=') or
            stripped.startswith('Prompt') or
            '模板' in stripped or
            'Template' in stripped or
            '{{' in stripped or
            '}}' in stripped or
            stripped in ['---', '===', '============']
        )
        
        if not is_meta:
            in_meta_section = False
        
        if not in_meta_section:
            real_content_lines.append(line)
    
    if real_content_lines:
        cleaned = '\n'.join(real_content_lines).strip()
        if cleaned:
            return cleaned
    
    # 如果清理后内容太少，返回原始输出
    return output


def _generate_text(skill: Skill, input_text: str) -> str:
    """
    纯粹的文本生成执行器。
    只负责：格式化 prompt → 调用 LLM → 返回结果
    """
    llm = LLMClient()
    prompt = skill.prompt_template.format(user_input=input_text)
    try:
        result = llm.complete(prompt)
        if result.strip():
            # 清理输出，移除可能被复述的 prompt 内容
            cleaned = _clean_llm_output(result, input_text)
            return cleaned
    except Exception:
        pass
    return (
        f"# {skill.name}\n\n"
        f"Input:\n\n{input_text}\n\n"
        "Generated content placeholder.\n"
    )


def _generate_image(skill: Skill, input_text: str, path: str):
    """
    纯粹的图像生成执行器。
    只负责：格式化 prompt → 调用 image model → 写文件
    """
    _ensure_parent_dir(path)
    llm = LLMClient()
    try:
        prompt = skill.prompt_template.format(user_input=input_text)
        raw_prompt = llm.complete(prompt).strip()
        if not raw_prompt:
            raise RuntimeError("Empty image prompt.")
        
        # 清理图像提示词，移除可能的 prompt 复述
        image_prompt = _clean_llm_output(raw_prompt, input_text)
        
        prompt_path = os.path.splitext(path)[0] + "_prompt.txt"
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(image_prompt)
        llm.generate_image(image_prompt, path)
        if os.path.exists(path) and os.path.getsize(path) < 2048:
            raise RuntimeError("Image output is too small, likely failed.")
        return
    except Exception as exc:
        error_path = os.path.splitext(path)[0] + "_error.txt"
        with open(error_path, "w", encoding="utf-8") as f:
            f.write(str(exc))
        raise


def execute_skill(skill: Skill, input_text: str) -> str:
    """
    Executor 的唯一入口。
    
    职责：
    1. 接收已经准备好的 input_text（由 App 层组装）
    2. 调用 LLM/Image Model
    3. 写输出文件
    4. 返回文件路径
    
    禁止：
    - 读取 context_index
    - 读取历史文件
    - 做任何上下文推理
    """
    output_path = skill.output_filename
    _ensure_parent_dir(output_path)
    
    if skill.output_type == "image":
        _generate_image(skill, input_text, output_path)
    else:
        content = _generate_text(skill, input_text)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    
    return output_path
