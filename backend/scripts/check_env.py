"""
环境变量诊断工具

检查 NOTION_API_KEY 环境变量配置状态
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Windows UTF-8 编码处理
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ==================== dotenv 测试代码 ====================
print("=== dotenv 测试 ===")
print(f"1. 直接读取 os.environ.get('NOTION_API_KEY'): {os.environ.get('NOTION_API_KEY', 'None')}")

# 测试1: 不加载 dotenv，直接读取
print(f"2. load_dotenv() 之前读取: {os.environ.get('NOTION_API_KEY', 'None')}")

# 测试2: 加载 dotenv 后读取
load_dotenv()  # 默认从当前目录查找 .env
print(f"3. load_dotenv() 之后读取: {os.environ.get('NOTION_API_KEY', 'None')}")

# 测试3: 指定路径加载
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
print(f"4. .env 文件路径: {env_path}")
print(f"5. .env 文件存在: {env_path.exists()}")
load_dotenv(dotenv_path=env_path, override=True)
print(f"6. 指定路径加载后: {os.environ.get('NOTION_API_KEY', 'None')}")

print("\n" + "="*60 + "\n")

def check_env():
    print("\n" + "="*60)
    print("NOTION_API_KEY 环境变量诊断")
    print("="*60)

    # 检查当前进程的环境变量
    print("\n1. 当前进程环境变量:")
    key = os.environ.get("NOTION_API_KEY")
    if key:
        masked = f"{key[:8]}...{key[-4:]}"
        print(f"   NOTION_API_KEY = {masked}")
    else:
        print(f"   NOTION_API_KEY = (未设置)")

    # 列出所有 NOTION 相关的环境变量
    print("\n2. 所有 NOTION 相关的环境变量:")
    found = False
    for k, v in os.environ.items():
        if "NOTION" in k.upper():
            masked = f"{v[:8]}...{v[-4:]}" if v else "(空)"
            print(f"   {k} = {masked}")
            found = True
    if not found:
        print("   (未找到任何 NOTION 相关的环境变量)")

    # 检查配置文件
    print("\n3. 检查配置文件:")
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        print(f"   config.yaml 存在: {config_path}")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                if "notion:" in content:
                    print("   找到 notion 配置段")
                    for line in content.split("\n"):
                        if "parent_page_id" in line:
                            print(f"   {line.strip()}")
                else:
                    print("   未找到 notion 配置段")
        except Exception as e:
            print(f"   读取配置文件失败: {e}")
    else:
        print(f"   config.yaml 不存在: {config_path}")

    # 提供建议
    print("\n" + "="*60)
    if not key:
        print("环境变量未设置，请使用以下命令设置:")
        print("\n  PowerShell (临时):")
        print('    $env:NOTION_API_KEY = "your_token_here"')
        print("\n  PowerShell (永久):")
        print('    setx NOTION_API_KEY "your_token_here"')
        print("\n  设置永久变量后需要重新启动终端才能生效")
    else:
        print("环境变量配置正确！")
        print("\n运行测试命令:")
        print("  python scripts/test_notion_connection.py")
    print("="*60 + "\n")


if __name__ == "__main__":
    check_env()
