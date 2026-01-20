#!/usr/bin/env python
"""列出所有可用的 Gemini 模型"""
import os
from google import genai

# 从 .env 加载环境变量
env_path = ".env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ 错误: 未找到 GEMINI_API_KEY")
    exit(1)

print("🔍 正在列出所有可用的 Gemini 模型...\n")

client = genai.Client(api_key=api_key)

try:
    models = client.models.list()
    
    text_models = []
    image_models = []
    other_models = []
    
    for model in models:
        name = model.name
        display_name = getattr(model, 'display_name', '')
        supported_methods = getattr(model, 'supported_generation_methods', [])
        
        # 判断模型类型
        if 'generateImage' in supported_methods or 'imagen' in name.lower():
            image_models.append((name, display_name, supported_methods))
        elif 'generateContent' in supported_methods:
            text_models.append((name, display_name, supported_methods))
        else:
            other_models.append((name, display_name, supported_methods))
    
    print("=" * 70)
    print("📝 文本生成模型")
    print("=" * 70)
    for name, display, methods in text_models:
        print(f"✓ {name}")
        if display:
            print(f"  显示名: {display}")
        print(f"  支持方法: {', '.join(methods)}")
        print()
    
    print("=" * 70)
    print("🎨 图像生成模型")
    print("=" * 70)
    if image_models:
        for name, display, methods in image_models:
            print(f"✓ {name}")
            if display:
                print(f"  显示名: {display}")
            print(f"  支持方法: {', '.join(methods)}")
            print()
    else:
        print("⚠️  未找到支持图像生成的模型")
        print()
    
    if other_models:
        print("=" * 70)
        print("🔧 其他模型")
        print("=" * 70)
        for name, display, methods in other_models:
            print(f"✓ {name}")
            if display:
                print(f"  显示名: {display}")
            print(f"  支持方法: {', '.join(methods)}")
            print()
    
except Exception as e:
    print(f"❌ 获取模型列表失败: {e}")
