"""
Notion API 连接测试脚本

测试目标：
1. 验证 API Token 有效性
2. 验证父页面访问权限
3. 验证创建子页面功能

配置说明：
- NOTION_API_KEY: 从 .env 文件或系统环境变量加载
- NOTION_PARENT_PAGE_ID: 从 config.yaml 加载
"""

import io
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Windows UTF-8 编码处理（支持 emoji 输出）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件（优先于系统环境变量）
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

try:
    from notion_client import Client
except ImportError:
    print("未安装 notion-client 库")
    print("请运行: pip install notion-client")
    sys.exit(1)

# 导入配置系统（NOTION_API_KEY 从环境变量加载）
from app.config import NOTION_API_KEY, NOTION_PARENT_PAGE_ID, NOTION_API_VERSION


def diagnose_env_vars():
    """诊断环境变量配置"""
    print("\n" + "="*60)
    print("环境变量诊断")
    print("="*60)

    # 检查所有可能的环境变量名称
    possible_names = [
        "NOTION_API_KEY",
        "NOTION_API_TOKEN",
        "NOTION_KEY",
        "NOTION_TOKEN"
    ]

    print("\n检查环境变量：")
    for name in possible_names:
        value = os.environ.get(name)
        if value:
            masked = f"{value[:8]}...{value[-4:]}"
            print(f"  {name}: {masked}")
        else:
            print(f"  {name}: (未设置)")

    print(f"\nconfig.py 中的 NOTION_API_KEY: ", end="")
    if NOTION_API_KEY:
        print(f"{NOTION_API_KEY[:8]}...{NOTION_API_KEY[-4:]}")
    else:
        print("(未设置)")

    return NOTION_API_KEY is not None


def test_api_connection():
    """测试 1: 验证 API Token 有效性"""
    print("\n" + "="*60)
    print("测试 1: 验证 API Token 连接")
    print("="*60)

    api_key = NOTION_API_KEY
    # 只显示前 8 个字符和后 4 个字符
    masked_key = f"{api_key[:8]}...{api_key[-4:]}"
    print(f"API Token: {masked_key}")

    try:
        client = Client(auth=api_key)
        # 使用 search API 测试连接
        response = client.search(
            filter={
                "value": "page",
                "property": "object"
            }
        )
        print(f"API 连接成功！")
        print(f"   找到 {len(response.get('results', []))} 个页面")
        return True, client
    except Exception as e:
        print(f"API 连接失败: {e}")
        return False, None


def test_parent_page_access(client, parent_page_id: str):
    """测试 2: 验证父页面访问权限"""
    print("\n" + "="*60)
    print("测试 2: 验证父页面访问")
    print("="*60)

    print(f"父页面 ID: {parent_page_id}")

    try:
        page = client.pages.retrieve(page_id=parent_page_id)
        title = "Untitled"

        # 尝试获取页面标题
        if "properties" in page:
            props = page["properties"]
            # Notion 页面可能有 title 或 Name 属性
            if "title" in props:
                title_array = props["title"].get("title", [])
                if title_array:
                    title = title_array[0].get("plain_text", "Untitled")
            elif "Name" in props:
                name_array = props["Name"].get("title", [])
                if name_array:
                    title = name_array[0].get("plain_text", "Untitled")

        print(f"父页面访问成功！")
        print(f"   页面标题: {title}")
        print(f"   创建时间: {page.get('created_time', 'N/A')}")
        return True
    except Exception as e:
        print(f"父页面访问失败: {e}")
        print("\n可能的原因：")
        print("   1. 页面 ID 不正确")
        print("   2. 集成没有访问该页面的权限")
        print("   解决方案：在 Notion 中打开该页面，点击右上角「...」→「Connections」→ 添加你的集成")
        return False


def test_create_child_page(client, parent_page_id: str):
    """测试 3: 验证创建子页面功能"""
    print("\n" + "="*60)
    print("测试 3: 创建测试子页面")
    print("="*60)

    test_title = "API 测试页面"
    print(f"准备创建测试页面: {test_title}")

    try:
        # 创建子页面
        new_page = client.pages.create(
            parent={
                "type": "page_id",
                "page_id": parent_page_id
            },
            properties={
                "title": [
                    {
                        "text": {
                            "content": test_title
                        }
                    }
                ]
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "这是一个测试页面，用于验证 Notion API 连接。"
                                }
                            }
                        ]
                    }
                }
            ]
        )

        page_id = new_page["id"]
        page_url = new_page["url"]

        print(f"子页面创建成功！")
        print(f"   页面 ID: {page_id}")
        print(f"   页面 URL: {page_url}")
        print(f"\n你可以在 Notion 中查看这个测试页面")
        return True, page_id
    except Exception as e:
        print(f"子页面创建失败: {e}")
        return False, None


def cleanup_test_page(client, page_id: str):
    """清理测试页面"""
    print("\n" + "="*60)
    print("清理测试页面")
    print("="*60)

    try:
        # Notion API 使用 archive 来删除页面
        client.pages.update(
            page_id=page_id,
            archived=True
        )
        print("测试页面已删除（归档）")
    except Exception as e:
        print(f"清理失败: {e}")


def main():
    """主测试流程"""
    print("\n" + "="*60)
    print("Notion API 连接测试")
    print("="*60)

    # 诊断环境变量
    if not diagnose_env_vars():
        print("\n错误：NOTION_API_KEY 环境变量未设置")
        print("\n请使用以下命令设置（PowerShell）：")
        print("  setx NOTION_API_KEY \"your_key_here\"")
        print("\n设置后需要重新启动终端窗口才能生效")
        return 1

    # 父页面 ID（从配置文件加载）
    parent_page_id = NOTION_PARENT_PAGE_ID
    print(f"\n父页面 ID: {parent_page_id}")

    # 测试 1: API 连接
    result, client = test_api_connection()
    if not result:
        print("\n测试失败：无法连接到 Notion API")
        return 1

    # 测试 2: 父页面访问
    result = test_parent_page_access(client, parent_page_id)
    if not result:
        print("\n测试失败：无法访问父页面")
        return 1

    # 测试 3: 创建子页面
    result, test_page_id = test_create_child_page(client, parent_page_id)
    if not result:
        print("\n测试失败：无法创建子页面")
        return 1

    # 清理测试页面
    cleanup_test_page(client, test_page_id)

    print("\n" + "="*60)
    print("所有测试通过！Notion API 配置正确")
    print("="*60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
