import json
import os
from typing import Any

# 在导入 google.genai 之前设置代理（如果需要）
# 只有在环境变量 USE_PROXY=true 时才启用代理
_use_proxy = os.getenv("USE_PROXY", "false").lower() == "true"
if _use_proxy:
    _proxy_host = os.getenv("HTTP_PROXY_HOST", "127.0.0.1")
    _proxy_port = os.getenv("HTTP_PROXY_PORT", "7890")
    _proxy_url = f"http://{_proxy_host}:{_proxy_port}"
    
    os.environ["HTTP_PROXY"] = _proxy_url
    os.environ["HTTPS_PROXY"] = _proxy_url
    os.environ["http_proxy"] = _proxy_url
    os.environ["https_proxy"] = _proxy_url
    os.environ["ALL_PROXY"] = _proxy_url
    print(f"🌐 使用代理: {_proxy_url}")
else:
    print("🌐 直连模式（不使用代理）")


class LLMClient:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.text_model = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
        self.image_model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        self._client = None

    def _get_client(self):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def complete(self, prompt: str) -> str:
        import time
        
        client = self._get_client()
        last_error = None
        
        # 最多重试 3 次
        for attempt in range(3):
            try:
                if attempt > 0:
                    # 指数退避：2秒、4秒
                    wait_time = 2 * attempt
                    print(f"⏳ API 繁忙，等待 {wait_time} 秒后重试（第 {attempt + 1} 次）...")
                    time.sleep(wait_time)
                
                response = client.models.generate_content(
                    model=self.text_model,
                    contents=prompt,
                )
                return response.text or ""
            except Exception as exc:
                last_error = exc
                error_str = str(exc)
                
                # 如果是可重试的错误（503 过载、429 限流等），继续重试
                if any(code in error_str for code in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"]):
                    if attempt < 2:  # 还有重试机会
                        continue
                    else:
                        raise RuntimeError(f"API 服务繁忙，已重试 {attempt + 1} 次仍失败：{exc}")
                else:
                    # 其他错误直接抛出
                    raise
        
        # 所有重试都失败
        raise RuntimeError(f"API 调用失败：{last_error}")

    def generate_image(self, prompt: str, output_path: str) -> None:
        import time

        client = self._get_client()
        last_error = None

        for attempt in range(3):
            try:
                if attempt > 0:
                    wait_time = 2 * attempt
                    print(f"⏳ 图像 API 繁忙，等待 {wait_time} 秒后重试（第 {attempt + 1} 次）...")
                    time.sleep(wait_time)

                response = client.models.generate_images(
                    model=self.image_model,
                    prompt=prompt,
                )
                images = getattr(response, "generated_images", None) or []
                if not images:
                    raise RuntimeError("No image returned by model.")
                images[0].image.save(output_path)
                return
            except Exception as exc:
                last_error = exc
                error_str = str(exc)
                
                # 可重试的错误：连接问题、503、429 等
                if any(keyword in error_str for keyword in [
                    "Connection", "peer", "503", "429", 
                    "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded"
                ]):
                    if attempt < 2:  # 还有重试机会
                        continue
                    else:
                        raise RuntimeError(f"图像生成失败（API 繁忙，已重试 {attempt + 1} 次）：{exc}")
                else:
                    # 其他错误直接抛出
                    raise

        raise RuntimeError(f"图像生成失败：{last_error}")


def parse_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None
