# Jグランツ MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.12.2%2B-green.svg)](https://gofastmcp.com)

デジタル庁が運用する補助金電子申請システム「**Jグランツ**」の公開APIをModel Context Protocol（MCP）サーバーとして実装。FastMCPフレームワークを使用し、LLMから自然言語で補助金検索・詳細取得が可能です。


## 特徴

- **リモート対応**: Streamable-HTTP経由でリモート接続可能
- **高度な検索機能**: キーワード、業種、従業員数、地域での絞り込み
- **統計分析**: 補助金の統計情報を自動集計（締切期間別、金額規模別）
- **ファイルダウンロード**: 募集要項や申請書類の自動ダウンロード・保存
- **添付資料アクセス**: PDFなどの添付資料をMarkdown/BASE64形式で取得可能
- **LLM統合**: 自然言語での補助金検索と詳細取得
- **ファイル変換**: PDF、Word、Excel、ZIPなど多様な形式をMarkdownに変換
- **動的ツール検出**: サーバーのツール変更を自動検出・適応
- **FastMCP**: 最新のFastMCPフレームワーク (v2.12.2) を使用
- **Prompts/Resources**: LLM向けのガイドとリソースを提供

## 動作確認環境

- **Claude Desktop**: v0.7.10以上
- **Python**: 3.11以上
- **FastMCP**: 2.12.2以上

## クイックスタート

### 前提条件

- Python 3.11以上
- pip (Pythonパッケージマネージャー)

### 環境セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/digital-go-jp/jgrants-mcp-server.git
cd jgrants-mcp-server

# Python仮想環境の作成
python -m venv venv

# 仮想環境の有効化
# macOS/Linux:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

### 環境変数（オプション）

必要に応じて以下の環境変数を設定できます：

| 環境変数 | デフォルト値 | 説明 |
|---------|------------|------|
| `JGRANTS_FILES_DIR` | `./jgrants_files` | 添付ファイル保存ディレクトリ |
| `API_BASE_URL` | `https://api.jgrants-portal.go.jp/exp/v1/public` | JグランツAPIエンドポイント |

設定例：
```bash
export JGRANTS_FILES_DIR=/tmp/jgrants_files
```

## サーバー起動

### HTTPサーバーモード

```bash
# HTTPサーバーを起動（デフォルト: localhost:8000）
python -m jgrants_mcp_server.core

# ホストとポートを指定
python -m jgrants_mcp_server.core --host 0.0.0.0 --port 8080
```

サーバー起動後、以下のエンドポイントが利用可能になります：
- **MCP エンドポイント**: `http://localhost:8000/mcp` もしくは `http://127.0.0.1:8000/mcp`
- **トランスポート**: Streamable-HTTP

## Claude Desktop との連携

### FastMCP CLI経由での接続（推奨）

Claude Desktop は stdio 接続のみサポートするため、FastMCP CLIをHTTPプロキシとして使用します。
この方法はResources、Prompts、Toolsのすべての機能をサポートします。

1. **MCP Server を起動**:
   ```bash
   python -m jgrants_mcp_server.core --port 8000
   ```

2. **Claude Desktop 設定ファイルを編集**:

   **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   **Linux**: `~/.config/Claude/claude_desktop_config.json`

   ```json
   {
     "mcpServers": {
       "jgrants": {
         "command": "uvx",
         "args": [
           "fastmcp",
           "run",
           "http://localhost:8000/mcp"
         ]
       }
     }
   }
   ```

   **備考**:
   - localhostでうまくいかない場合は 127.0.0.1 でお試しください
   - `uvx`は`uv`のコマンドラインツール実行機能です（`pip install uv`でインストール）
   - `uvx`がインストールされていない場合は、`fastmcp`を直接使用することもできます：
     ```json
     {
       "mcpServers": {
         "jgrants": {
           "command": "fastmcp",
           "args": [
             "run",
             "http://localhost:8000/mcp"
           ]
         }
       }
     }
     ```

4. **Claude Desktop を再起動**

### 接続確認

Claude Desktopを開き、新しい会話で以下のように質問してみてください：

```
補助金を検索できますか？
```

サーバーが正しく設定されていれば、利用可能なツールの一覧が表示されます。

## Prompts と Resources

MCPサーバーは、LLMが効果的にツールを使用できるよう、プロンプトとリソースを提供します。

### Prompts（動的ガイド）

- **`subsidy_search_guide`**: 補助金検索のベストプラクティスと推奨検索パターン
- **`api_usage_agreement`**: API利用規約と免責事項の確認

### Resources（静的リファレンス）

- **`jgrants://guidelines`**: MCPサーバー利用ガイドライン、API制限、トラブルシューティング

## 利用可能なツール

### 1. `search_subsidies`
補助金を検索します。キーワード、業種、地域、従業員数などで絞り込み可能。

**パラメータ:**
- `keyword` (str): 検索キーワード（2文字以上必須）
- `industry` (str, optional): 業種
- `target_area_search` (str, optional): 対象地域
- `target_number_of_employees` (str, optional): 従業員数制約
- `sort` (str): ソート順（`acceptance_end_datetime` / `acceptance_start_datetime` / `created_date`）
- `order` (str): 昇順/降順（`ASC` / `DESC`）
- `acceptance` (int): 受付状態（`0`: 全て / `1`: 受付中のみ）

### 2. `get_subsidy_detail`
補助金の詳細情報を取得し、添付ファイルをローカルに保存します。

**パラメータ:**
- `subsidy_id` (str): 補助金ID（18文字以下）

**返却情報:**
- 補助金の詳細情報（タイトル、補助上限額、補助率、受付期間など）
- 添付ファイルのfile:// URL（公募要領、概要資料、申請様式など）
- ファイル保存先ディレクトリのパス

### 3. `get_subsidy_overview`
補助金の統計情報を取得します（締切期間別、金額規模別の集計）。

**パラメータ:**
- `output_format` (str): 出力形式（`json` / `csv`）

### 4. `get_file_content`
保存済みの添付ファイルの内容を取得します。

**パラメータ:**
- `subsidy_id` (str): 補助金ID
- `filename` (str): ファイル名
- `return_format` (str): 返却形式（`markdown` / `base64`）

**機能:**
- PDF、Word、Excel、PowerPoint、ZIPをMarkdownに自動変換
- 変換失敗時はBASE64形式で返却

### 5. `ping`
サーバーの疎通確認を行います。

## 開発とテスト

### テスト実行

```bash
# テスト実行
pytest tests/test_core.py
```

### デバッグ

```bash
# デバッグモードで起動
python -m jgrants_mcp_server.core --log-level DEBUG
```

## ライセンス

MIT License - 詳細は[LICENSE](LICENSE)ファイルを参照してください。

## 免責事項
本実装は、技術検証を目的としたサンプルコードです。以下の点にご留意ください：
- 本コードは現状のまま提供され、動作の安定性や継続的な保守を保証するものではありません
- Jグランツサービスの検索性や動作の安定性を保証するものではありません
- 実際の利用にあたっては、JグランツAPIの利用規約 (https://www.jgrants-portal.go.jp/open-api) に準じてご利用ください


