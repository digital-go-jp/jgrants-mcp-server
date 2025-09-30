# jGrants MCP Server テスト

## テスト実行方法

### 1. サーバー起動
```bash
python -m jgrants_mcp_server.core --port 8000
```

### 2. テスト実行
```bash
# Core機能テスト
python tests/test_core.py

```

## テストファイル

### test_core.py
**Core機能テスト** - FastMCP Client経由で直接MCPサーバーをテストします：

- **Tools**: ツール一覧取得と `search_subsidies` の実行
- **Resources**: リソース一覧取得と `jgrants://guidelines` の読み取り
- **Prompts**: プロンプト一覧取得と `subsidy_search_guide` の取得


## 成功時の出力例

```
============================================================
jGrants MCP Server Test
Server: http://localhost:8000/mcp
Time: 2025-09-29 18:00:00
============================================================

[Tools]
✅ 5 tools found
✅ search_subsidies executed

[Resources]
✅ 1 resources found
✅ resource read successful

[Prompts]
✅ 2 prompts found
✅ prompt retrieved

============================================================
✅ ALL TESTS PASSED
============================================================
```