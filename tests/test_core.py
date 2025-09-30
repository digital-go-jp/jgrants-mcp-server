#!/usr/bin/env python3
"""jGrants MCP Server 統合テスト"""

import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import Client


async def test_server():
    """MCP Serverの全機能をテスト"""

    server_url = os.environ.get('MCP_SERVER_URL', 'http://localhost:8000/mcp')

    print(f"\n{'='*60}")
    print(f"jGrants MCP Server Test")
    print(f"Server: {server_url}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    try:
        async with Client(server_url) as client:
            # 1. Tools テスト
            print("\n[Tools]")
            tools = await client.list_tools()
            print(f"✅ {len(tools)} tools found")

            # search_subsidies実行
            await client.call_tool("search_subsidies", {"keyword": "IT"})
            print(f"✅ search_subsidies executed")

            # 2. Resources テスト
            print("\n[Resources]")
            resources = await client.list_resources()
            print(f"✅ {len(resources)} resources found")

            if resources:
                await client.read_resource("jgrants://guidelines")
                print(f"✅ resource read successful")

            # 3. Prompts テスト
            print("\n[Prompts]")
            prompts = await client.list_prompts()
            print(f"✅ {len(prompts)} prompts found")

            if prompts:
                await client.get_prompt("subsidy_search_guide")
                print(f"✅ prompt retrieved")

            print(f"\n{'='*60}")
            print("✅ ALL TESTS PASSED")
            print(f"{'='*60}\n")
            return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_server())
    sys.exit(0 if success else 1)