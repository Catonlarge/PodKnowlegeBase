"""
系统环境变量测试

只测试 os.environ.get() 能否读取系统环境变量
"""

import os
import sys

# Windows UTF-8 编码处理
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=== 系统环境变量测试 ===")
print(f"NOTION_API_KEY = {'已设置' if os.environ.get('NOTION_API_KEY') else 'None'}")
print(f"GEMINI_API_KEY = {'已设置' if os.environ.get('GEMINI_API_KEY') else 'None'}")
print(f"MOONSHOT_API_KEY = {'已设置' if os.environ.get('MOONSHOT_API_KEY') else 'None'}")
