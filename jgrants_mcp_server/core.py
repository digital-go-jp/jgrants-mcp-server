"""jGrants MCP Server - FastMCP with Streamable HTTP"""

import os
import base64
import csv
import io
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import logging
import httpx
from fastmcp import FastMCP
import pdfplumber
from markitdown import MarkItDown

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定数定義
API_BASE_URL = "https://api.jgrants-portal.go.jp/exp/v1/public"

# FastMCPサーバーの初期化
mcp = FastMCP("jgrants-mcp-server")

# ファイル保存ディレクトリ（環境変数で設定可能）
FILES_DIR = Path(os.environ.get("JGRANTS_FILES_DIR", "tmp"))
FILES_DIR.mkdir(parents=True, exist_ok=True)

_HTTP_CLIENT: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """モジュール内で共有するHTTPクライアント（Keep-Alive、接続プール再利用）。"""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        _HTTP_CLIENT = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=True,
            headers={
                "User-Agent": "jgrants-mcp-server/0.1 (+https://github.com/yourusername/jgrants-mcp-server)"
            },
        )
    return _HTTP_CLIENT


async def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """共通のHTTP GET(JSON) クライアント。エラーは {error: ...} を返す。"""
    try:
        client = _get_http_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.ReadTimeout as e:
        return {"error": f"リクエストがタイムアウトしました: {str(e)}"}
    except httpx.ConnectError as e:
        return {"error": f"APIサーバーへの接続に失敗しました: {str(e)}"}
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else 0
        return {"error": f"HTTPエラー: {status}"}
    except Exception as e:
        return {"error": f"エラーが発生しました: {str(e)}"}


# 内部関数（ツール間で共有）
async def _search_subsidies_internal(
    keyword: str = "事業", # デフォルトキーワード
    use_purpose: Optional[str] = None,
    industry: Optional[str] = None,
    target_number_of_employees: Optional[str] = None,
    target_area_search: Optional[str] = None,
    sort: str = "acceptance_end_datetime",
    order: str = "ASC",
    acceptance: int = 1
) -> Dict[str, Any]:
    """内部用: 補助金検索APIを呼び出す共通関数"""
    # 必須パラメータ（引数のsort/orderを尊重）
    params = {
        "keyword": keyword,
        "sort": sort,
        "order": order,
        "acceptance": str(acceptance),
    }
    # オプションパラメータ
    if use_purpose:
        params["use_purpose"] = use_purpose
    if industry:
        params["industry"] = industry
    if target_number_of_employees:
        params["target_number_of_employees"] = target_number_of_employees
    if target_area_search:
        params["target_area_search"] = target_area_search
    
    url = f"{API_BASE_URL}/subsidies"
    
    
    data = await _get_json(url, params=params)
    if "error" in data:
        return data

    # レスポンスを整形
    if "result" in data:
        return {
            "total_count": len(data["result"]),
            "subsidies": data["result"],
            "search_conditions": {k: v for k, v in params.items() if k not in ["limit"]},
        }
    return {"subsidies": [], "total_count": 0}


# ツール定義: search_subsidies
@mcp.tool()
async def search_subsidies(
    keyword: str,
    use_purpose: Optional[str] = None,
    industry: Optional[str] = None,
    target_number_of_employees: Optional[str] = None,
    target_area_search: Optional[str] = None,
    sort: str = "acceptance_end_datetime",
    order: str = "ASC",
    acceptance: int = 1
) -> Dict[str, Any]:
    """
    高度な検索条件で補助金を検索します。

    このツールは jGrants 公開APIの "補助金検索" をラップしています。
    - jGrants ポータル: https://www.jgrants-portal.go.jp/
    - ベースURL: https://api.jgrants-portal.go.jp/exp/v1/public
    - エンドポイント: GET /subsidies
    - 公式ドキュメント: https://developers.digital.go.jp/documents/jgrants/api/

    クエリパラメータ（主なもの）
    - keyword: 検索キーワード（2-255文字程度を想定、必須）。大文字・小文字や全角・半角の表記ゆれを許容する（例：IoTとIOT、IoTとⅠoＴ、カタカナとｶﾀｶﾅを区別しない）
    - sort: 並び順フィールド（created_date / acceptance_start_datetime / acceptance_end_datetime）。created_date：作成日時、acceptance_start_datetime：募集開始日時、acceptance_end_datetime：募集終了日時
    - order: ソート順（ASC / DESC）
    - acceptance: 受付期間フィルタ（0=しない, 1=する）
    - use_purpose: 利用目的。値が複数ある場合は、「 / 」（半角スペース＋半角スラッシュ＋半角スペース）で区切る。
        "新たな事業を行いたい", "販路拡大・海外展開をしたい", "イベント・事業運営支援がほしい",
        "事業を引き継ぎたい", "研究開発・実証事業を行いたい", "人材育成を行いたい",
        "資金繰りを改善したい", "設備整備・IT導入をしたい", "雇用・職場環境を改善したい",
        "エコ・SDGs活動支援がほしい", "災害（自然災害、感染症等）支援がほしい",
        "教育・子育て・少子化支援がほしい", "スポーツ・文化支援がほしい",
        "安全・防災対策支援がほしい", "まちづくり・地域振興支援がほしい"
    - industry: 業種。値が複数ある場合は、半角スペース＋半角スラッシュ＋半角スペース）で区切る
        "農業、林業", "漁業", "鉱業、採石業、砂利採取業", "建設業", "製造業",
        "電気・ガス・熱供給・水道業", "情報通信業", "運輸業、郵便業", "卸売業、小売業",
        "金融業、保険業", "不動産業、物品賃貸業", "学術研究、専門・技術サービス業",
        "宿泊業、飲食サービス業", "生活関連サービス業、娯楽業", "教育、学習支援業",
        "医療、福祉", "複合サービス事業", "サービス業（他に分類されないもの）",
        "公務（他に分類されるものを除く）", "分類不能の産業"
    - target_number_of_employees: 従業員数の上限
        "従業員数の制約なし", "5名以下", "20名以下", "50名以下", "100名以下",
        "300名以下", "900名以下", "901名以上"
    - target_area_search: 補助対象地域
        "全国" "北海道地方" "東北地方" "関東・甲信越地方" "東海・北陸地方" "近畿地方" "中国地方" "四国地方" "九州・沖縄地方" "北海道" "青森県" "岩手県" "宮城県" "秋田県" "山形県" "福島県" "茨城県" "栃木県" "群馬県" "埼玉県" "千葉県" "東京都" "神奈川県" "新潟県" "富山県" "石川県" "福井県" "山梨県" "長野県" "岐阜県" "静岡県" "愛知県" "三重県" "滋賀県" "京都府" "大阪府" "兵庫県" "奈良県" "和歌山県" "鳥取県" "島根県" "岡山県" "広島県" "山口県" "徳島県" "香川県" "愛媛県" "高知県" "福岡県" "佐賀県" "長崎県" "熊本県" "大分県" "宮崎県" "鹿児島県" "沖縄県"

    レスポンス（API resultのラップ）
    - subsidies: APIの result 配列をそのまま返却
    - total_count: 件数
    - search_conditions: 最終的にAPIへ渡した検索条件

    注意
    - 本ツールはAPI仕様に準拠します。詳細は上記の公式ドキュメントを参照してください。
    - 各補助金の詳細は jGrants ポータル (https://www.jgrants-portal.go.jp/grants/view/{subsidy_id}) で確認できます
    - 出典表示: 本ツールで取得した情報を利用・公開する際は、
      「Jグランツ（jGrants）からの出典」である旨を明記してください。
    - デフォルトのkeywordは「事業」にしています。 

    必須パラメータ（API仕様上）
    - keyword: 検索キーワード（2〜255文字）
    - acceptance: 受付期間フィルタ（0 または 1）
      ※ 本ツールでは既定値 = 1 を用意しているため、省略時は 1 として扱います。
    
    オプションパラメータ（本ツールの引数）
    - use_purpose, industry, target_number_of_employees, target_area_search, sort, order
    
    """
    # 必須パラメータのバリデーション（API仕様準拠）
    if not isinstance(keyword, str) or not keyword.strip() or not (2 <= len(keyword.strip()) <= 255):
        return {"error": "keyword は2〜255文字の非空文字列で指定してください"}
    if acceptance not in (0, 1):
        return {"error": "acceptance は 0 または 1 を指定してください"}
    allowed_sorts = {"created_date", "acceptance_start_datetime", "acceptance_end_datetime"}
    if sort not in allowed_sorts:
        return {"error": "sort は created_date / acceptance_start_datetime / acceptance_end_datetime から選択してください"}
    if str(order).upper() not in {"ASC", "DESC"}:
        return {"error": "order は ASC または DESC を指定してください"}

    return await _search_subsidies_internal(
        keyword=keyword,
        use_purpose=use_purpose,
        industry=industry,
        target_number_of_employees=target_number_of_employees,
        target_area_search=target_area_search,
        sort=sort,
        order=str(order).upper(),
        acceptance=acceptance
    )


@mcp.tool()
async def ping() -> Dict[str, Any]:
    """
    サーバーの応答を確認するためのユーティリティ。
    MCP仕様に従い、空の結果を返します。

    Returns:
        空の辞書（接続が正常であることを示す）

    必須パラメータ
    - なし
    """
    return {
        "status": "ok",
        "server": "jGrants MCP Server",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@mcp.tool()
async def get_subsidy_overview(output_format: str = "json") -> Dict[str, Any]:
    """
    補助金の最新状況を把握します。締切期間別、金額規模別の集計を提供。

    実装メモ（APIに存在しない集計のため、サーバー内で算出）
    - まず search_subsidies（GET /subsidies）を呼び、取得結果に対して集計します。
    - 受付中や締切までの日数は、acceptance_end_datetime を現在時刻と比較して算出します。
    - 金額は subsidy_max_limit を数値化して分類します（未設定は "unspecified"）。

    参考
    - jGrants ポータル: https://www.jgrants-portal.go.jp/
    - API 公式ドキュメント: https://developers.digital.go.jp/documents/jgrants/api/
    - 各補助金の詳細ページ: https://www.jgrants-portal.go.jp/grants/view/{subsidy_id} で申請手続きが可能
    - 出典表示: 本ツールで取得した情報を利用・公開する際は、「Jグランツ（jGrants）からの出典」である旨を明記してください。

    Returns:
        統計情報（締切期間別、金額規模別、緊急案件リスト等）
        output_format="csv"の場合はCSVデータを含む辞書を返却

    Args:
        output_format: 出力形式 ("json" または "csv")。デフォルトは "json"

    必須パラメータ
    - なし
    """
    # まず検索して統計を計算（デフォルトキーワードで検索）
    subsidies = await _search_subsidies_internal()

    if "error" in subsidies:
        return subsidies

    stats = {
        "total_count": subsidies.get("total_count", 0),
        "by_deadline_period": {
            "accepting": 0,
            "this_month": 0,
            "next_month": 0,
            "after_next_month": 0
        },
        "by_amount_range": {
            "under_1m": 0,
            "under_10m": 0,
            "under_100m": 0,
            "over_100m": 0,
            "unspecified": 0
        },
        "urgent_deadlines": [],
        "high_amount_subsidies": [],
        "statistics_generated_at": datetime.now(timezone.utc).isoformat()
    }

    # タイムゾーン付きの日時で比較（UTC）
    now = datetime.now(timezone.utc)

    for subsidy in subsidies.get("subsidies", []):
        # 締切による分類
        if subsidy.get("acceptance_end_datetime"):
            try:
                end_date = datetime.fromisoformat(
                    subsidy["acceptance_end_datetime"].replace("Z", "+00:00")
                )
                days_left = (end_date - now).days

                if days_left < 0:
                    continue
                elif days_left <= 30:
                    stats["by_deadline_period"]["this_month"] += 1
                elif days_left <= 60:
                    stats["by_deadline_period"]["next_month"] += 1
                else:
                    stats["by_deadline_period"]["after_next_month"] += 1

                # 緊急案件（14日以内）
                if 0 <= days_left <= 14:
                    stats["urgent_deadlines"].append({
                        "id": subsidy.get("id"),
                        "title": subsidy.get("title"),
                        "days_left": days_left
                    })
            except Exception:
                pass

        # 金額による分類
        max_limit = subsidy.get("subsidy_max_limit")
        if max_limit:
            try:
                amount = float(max_limit)
                if amount <= 1000000:
                    stats["by_amount_range"]["under_1m"] += 1
                elif amount <= 10000000:
                    stats["by_amount_range"]["under_10m"] += 1
                elif amount <= 100000000:
                    stats["by_amount_range"]["under_100m"] += 1
                else:
                    stats["by_amount_range"]["over_100m"] += 1

                # 高額補助金（5000万円以上）
                if amount >= 50000000:
                    stats["high_amount_subsidies"].append({
                        "id": subsidy.get("id"),
                        "title": subsidy.get("title"),
                        "max_amount": amount
                    })
            except:
                stats["by_amount_range"]["unspecified"] += 1
        else:
            stats["by_amount_range"]["unspecified"] += 1

    if output_format.lower() == "csv":
        return _convert_statistics_to_csv(stats)

    return stats


def _convert_statistics_to_csv(stats: Dict[str, Any]) -> Dict[str, Any]:
    """統計情報をCSV形式に変換"""
    if "error" in stats:
        return stats

    csv_data = {}

    # 締切期間別の統計をCSV化
    deadline_csv = io.StringIO()
    deadline_writer = csv.writer(deadline_csv)
    deadline_writer.writerow(["期間", "件数"])
    for period, count in stats.get("by_deadline_period", {}).items():
        period_label = {
            "accepting": "受付中",
            "this_month": "今月締切",
            "next_month": "来月締切",
            "after_next_month": "再来月以降"
        }.get(period, period)
        deadline_writer.writerow([period_label, count])
    csv_data["deadline_statistics"] = deadline_csv.getvalue()

    # 金額規模別の統計をCSV化
    amount_csv = io.StringIO()
    amount_writer = csv.writer(amount_csv)
    amount_writer.writerow(["金額規模", "件数"])
    for range_key, count in stats.get("by_amount_range", {}).items():
        range_label = {
            "under_1m": "100万円以下",
            "under_10m": "1000万円以下",
            "under_100m": "1億円以下",
            "over_100m": "1億円超",
            "unspecified": "金額未設定"
        }.get(range_key, range_key)
        amount_writer.writerow([range_label, count])
    csv_data["amount_statistics"] = amount_csv.getvalue()

    # 緊急締切案件をCSV化
    if stats.get("urgent_deadlines"):
        urgent_csv = io.StringIO()
        urgent_writer = csv.writer(urgent_csv)
        urgent_writer.writerow(["補助金ID", "補助金名", "残り日数"])
        for item in stats["urgent_deadlines"]:
            urgent_writer.writerow([
                item.get("id", ""),
                item.get("title", ""),
                item.get("days_left", "")
            ])
        csv_data["urgent_deadlines"] = urgent_csv.getvalue()

    # 高額補助金をCSV化
    if stats.get("high_amount_subsidies"):
        high_amount_csv = io.StringIO()
        high_amount_writer = csv.writer(high_amount_csv)
        high_amount_writer.writerow(["補助金ID", "補助金名", "最大金額"])
        for item in stats["high_amount_subsidies"]:
            high_amount_writer.writerow([
                item.get("id", ""),
                item.get("title", ""),
                f"{item.get('max_amount', 0):,.0f}"
            ])
        csv_data["high_amount_subsidies"] = high_amount_csv.getvalue()

    # メタ情報を追加
    csv_data["total_count"] = stats.get("total_count", 0)
    csv_data["statistics_generated_at"] = stats.get("statistics_generated_at", "")
    csv_data["format"] = "csv"

    return csv_data




# ツール定義: get_subsidy_detail（統合版）
@mcp.tool()
async def get_subsidy_detail(subsidy_id: str) -> Dict[str, Any]:
    """
    補助金の詳細情報を取得し、添付ファイルを自動的にダウンロードします。
    
    Args:
        subsidy_id: 補助金ID（例: "a0WJ200000CDR9HMAX"）
    
    Returns:
        以下の構造を持つ辞書:
        {
            "id": str,                    # 補助金ID
            "title": str,                 # 補助金名称
            "description": str,           # 詳細説明（HTML形式）
            "subsidy_max_limit": str,     # 最大補助額
            "acceptance_start": str,      # 募集開始日時（ISO8601形式）
            "acceptance_end": str,        # 募集終了日時（ISO8601形式）
            "status": str,                # "受付中" または "受付終了"
            "target": {
                "area": str,              # 補助対象地域
                "industry": str,          # 対象業種
                "employees": str,         # 対象従業員数
                "purpose": str            # 利用目的
            },
            "application_url": str,       # 申請ページURL
            "last_updated": str,          # 最終更新日時
            "files": {                    # ダウンロードしたファイル情報
                "application_guidelines": [ # 申請ガイドライン
                    {
                        "name": str,      # ファイル名
                        "url": str,       # file://形式のローカルURL
                        "path": str,      # ローカルファイルパス
                        "size": int       # ファイルサイズ（バイト）
                    }
                ],
                "outline_of_grant": [...], # 補助金概要（同上の構造）
                "application_form": [...]  # 申請書類（同上の構造）
            },
            "save_directory": str         # ファイル保存先ディレクトリ
        }

    このツールは jGrants 公開APIの "補助金詳細" をラップしています。
    - ベースURL: https://api.jgrants-portal.go.jp/exp/v1/public
    - エンドポイント: GET /subsidies/id/{subsidy_id}
    - 公式ドキュメント: https://developers.digital.go.jp/documents/jgrants/api/

    機能詳細:
    - APIから取得したBASE64エンコードされたファイルを自動的にデコード
    - ローカルファイルシステムに保存（tmp/{subsidy_id}/以下）
    - file://形式のURLを生成してMCPクライアントに返却
    - PDF、ZIP等の各種ファイル形式に対応
    - ファイル名の自動サニタイズ（安全な文字のみ使用）

    注意事項:
    - ファイルはローカルのtmpディレクトリに保存されます。補助金の情報はファイルに詳細が含まれることが多いため、すべてのfile urlをリンク(ブラウザから開けるリンク)として表示してあげてください
    - 出典表示: 本ツールで取得した情報を利用・公開する際は、
      「Jグランツ（jGrants）からの出典」である旨を明記してください

    必須パラメータ:
    - subsidy_id: 取得対象の補助金ID（非空の文字列）
    """
    # 入力バリデーション（API仕様準拠）
    if not isinstance(subsidy_id, str) or not subsidy_id.strip():
        return {"error": "subsidy_id は非空の文字列で指定してください"}

    # 個別の詳細エンドポイントを使用
    url = f"{API_BASE_URL}/subsidies/id/{subsidy_id}"

    data = await _get_json(url)
    if "error" in data:
        if data["error"].startswith("HTTPエラー: 404"):
            return {"error": f"補助金ID '{subsidy_id}' が見つかりません"}
        return data

    # レスポンスを整形
    if isinstance(data, dict):
        result = data.get("result", data)
        if isinstance(result, list) and len(result) > 0:
            subsidy = result[0]
        elif isinstance(result, dict):
            subsidy = result
        else:
            return {"error": "予期しないレスポンス形式"}

        # ステータス判定（締切日が未来なら受付中）
        status = "受付終了"
        end_raw = subsidy.get("acceptance_end_datetime")
        if end_raw:
            try:
                end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                if end_dt >= datetime.now(end_dt.tzinfo):
                    status = "受付中"
            except Exception:
                status = "受付中"

        formatted_result = {
            "id": subsidy.get("id", subsidy_id),
            "title": subsidy.get("title", ""),
            "description": subsidy.get("detail", subsidy.get("description", "")),
            "subsidy_max_limit": subsidy.get("subsidy_max_limit"),
            "acceptance_start": subsidy.get("acceptance_start_datetime"),
            "acceptance_end": subsidy.get("acceptance_end_datetime"),
            "target": {
                "area": subsidy.get("target_area_search"),
                "industry": subsidy.get("target_industry"),
                "employees": subsidy.get("target_number_of_employees"),
                "purpose": subsidy.get("use_purpose")
            },
            "application_url": subsidy.get("inquiry_url"),
            "last_updated": subsidy.get("update_datetime"),
            "status": status
        }

        # ファイルを保存してURLを生成
        files_data = {
            "application_guidelines": subsidy.get("application_guidelines", []),
            "outline_of_grant": subsidy.get("outline_of_grant", []),
            "application_form": subsidy.get("application_form", [])
        }

        subsidy_dir = FILES_DIR / subsidy_id
        subsidy_dir.mkdir(exist_ok=True)

        saved_files = {}
        file_type_names = {
            "application_guidelines": "申請ガイドライン",
            "outline_of_grant": "補助金概要",
            "application_form": "申請書"
        }

        debug_files = os.environ.get("JGRANTS_DEBUG_FILES", "0") not in ("0", "false", "False", "")
        for file_type, file_list in files_data.items():
            if file_list:
                saved_files[file_type] = []
                base_name = file_type_names[file_type]

                for idx, file_data in enumerate(file_list):
                    if isinstance(file_data, dict):
                        # APIレスポンスのキー名に合わせる（name, data）
                        file_name = file_data.get("name") or file_data.get("file_name", f"{base_name}_{idx+1}.pdf")
                        file_base64 = file_data.get("data") or file_data.get("file_data", "")

                        # デバッグログ（環境変数で有効化時のみ）
                        if debug_files:
                            with open("/tmp/jgrants_debug.log", "a") as debug_log:
                                debug_log.write(
                                    f"DEBUG: file_name={file_name}, file_base64 length={len(file_base64) if file_base64 else 0}\n"
                                )
                        if file_base64:
                            try:
                                # BASE64データの検証
                                if not isinstance(file_base64, str) or len(file_base64.strip()) == 0:
                                    raise ValueError("無効なBASE64データ")
                                
                                # ファイル名のサニタイズ（日本語を保持）
                                import re
                                
                                # 日本語文字（ひらがな、カタカナ、漢字）を保持しつつ、危険な文字を除去
                                # Windowsで使えない文字: < > : " | ? * \ /
                                # パス区切り文字も除去
                                dangerous_chars = r'[<>:"|?*\\/]'
                                safe_file_name = re.sub(dangerous_chars, '_', file_name)
                                
                                # 空白を_に変換
                                safe_file_name = safe_file_name.replace(' ', '_')
                                
                                # ファイル名が空になった場合のフォールバック
                                if not safe_file_name or safe_file_name == '_':
                                    safe_file_name = f"{base_name}_{idx+1}.pdf"
                                
                                # BASE64デコード
                                file_content = base64.b64decode(file_base64.strip())
                                
                                # 空ファイルチェック
                                if len(file_content) == 0:
                                    raise ValueError("デコード後のファイルが空です")
                                
                                file_path = subsidy_dir / safe_file_name

                                with open(file_path, "wb") as f:
                                    f.write(file_content)

                                # ファイル情報を保存
                                saved_files[file_type].append({
                                    "name": safe_file_name,
                                    "original_name": file_name,  # オリジナルのファイル名も保持
                                    "size": len(file_content),
                                    "mcp_access": {
                                        "tool": "get_file_content",
                                        "params": {
                                            "subsidy_id": subsidy_id,
                                            "filename": safe_file_name
                                        },
                                        "description": f"このファイルにアクセスするには get_file_content ツールを使用してください"
                                    }
                                })
                            except Exception as e:
                                error_msg = f"保存失敗 ({file_name}): {str(e)}"
                                saved_files[file_type].append({
                                    "name": file_name,
                                    "error": error_msg
                                })

        formatted_result["files"] = saved_files
        formatted_result["save_directory"] = str(subsidy_dir)

        return formatted_result

    return {"error": "予期しないレスポンス形式"}



@mcp.tool()
async def get_file_content(subsidy_id: str, filename: str, return_format: str = "markdown") -> Dict[str, Any]:
    """
    保存されたファイルの内容を取得（Markdown形式またはBASE64形式）

    補助金詳細取得時に保存されたファイルをMCP経由で取得します。
    PDFファイルの場合はデフォルトでMarkdown形式で返します。

    パラメータ:
    - subsidy_id: 補助金ID
    - filename: ファイル名
    - return_format: "markdown" (デフォルト) または "base64"

    戻り値（Markdown形式の場合）:
    - filename: ファイル名
    - content_markdown: Markdown形式のテキスト内容
    - mime_type: MIMEタイプ
    - size_bytes: ファイルサイズ（バイト）
    - extraction_method: 抽出方法

    戻り値（BASE64形式の場合）:
    - filename: ファイル名
    - content_base64: BASE64エンコードされたファイル内容
    - mime_type: MIMEタイプ
    - size_bytes: ファイルサイズ（バイト）

    使用例:
    1. get_subsidy_detail で補助金詳細を取得
    2. files フィールドから必要なファイル名を確認
    3. このツールでファイル内容を取得
    """
    try:
        # デバッグ: パラメータを確認
        logger.info(f"get_file_content called with subsidy_id={subsidy_id}, filename={filename}, return_format={return_format}")

        file_path = FILES_DIR / subsidy_id / filename
        logger.info(f"Looking for file at: {file_path}")

        if not file_path.exists():
            return {"error": f"ファイルが見つかりません: {subsidy_id}/{filename}"}

        # MIMEタイプの判定
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"

        # ファイルサイズを取得
        file_size = file_path.stat().st_size

        # Markdown形式が要求された場合、MarkItDownで対応可能なファイル形式をチェック
        if return_format == "markdown":
            # MarkItDownがサポートする形式
            supported_extensions = {
                '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt',
                '.html', '.htm', '.xml', '.rtf', '.txt', '.csv', '.md',
                '.zip'  # ZIPファイルも対応
            }

            file_extension = Path(filename).suffix.lower()

            if file_extension in supported_extensions:
                try:
                    # MarkItDownを使用してMarkdownに変換
                    converter = MarkItDown()
                    result = converter.convert(str(file_path))
                    extracted_markdown = result.text_content

                    if extracted_markdown and extracted_markdown.strip():
                        logger.info(f"{file_extension}からMarkdownを抽出しました: {len(extracted_markdown)} 文字")
                        return {
                            "filename": filename,
                            "content_markdown": extracted_markdown,
                            "mime_type": mime_type,
                            "size_bytes": file_size,
                            "extraction_method": f"markitdown_{file_extension[1:]}"  # 拡張子から.を除去
                        }
                    else:
                        logger.warning(f"{file_extension}からMarkdownの抽出に失敗しました。BASE64形式で返します。")
                        return_format = "base64"  # フォールバック
                except Exception as e:
                    logger.error(f"MarkItDown変換エラー: {e}")
                    # PDFの場合はpdfplumberにフォールバック
                    if mime_type == "application/pdf":
                        try:
                            with pdfplumber.open(file_path) as pdf:
                                text_parts = []
                                for i, page in enumerate(pdf.pages, 1):
                                    page_text = page.extract_text()
                                    if page_text:
                                        text_parts.append(f"## ページ {i}\n\n{page_text}")
                                extracted_markdown = "\n\n---\n\n".join(text_parts)

                                if extracted_markdown and extracted_markdown.strip():
                                    logger.info(f"pdfplumberでPDFからMarkdownを抽出しました: {len(extracted_markdown)} 文字")
                                    return {
                                        "filename": filename,
                                        "content_markdown": extracted_markdown,
                                        "mime_type": mime_type,
                                        "size_bytes": file_size,
                                        "extraction_method": "pdfplumber_markdown"
                                    }
                        except Exception as e2:
                            logger.error(f"pdfplumber変換エラー: {e2}")
                    return_format = "base64"  # フォールバック

        # テキストファイルの場合は直接読み込み
        if return_format == "markdown" and mime_type and mime_type.startswith("text/"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text_content = f.read()
                return {
                    "filename": filename,
                    "content_markdown": text_content,
                    "mime_type": mime_type,
                    "size_bytes": file_size,
                    "extraction_method": "text_file"
                }
            except Exception as e:
                logger.error(f"テキストファイル読み込みエラー: {e}")
                return_format = "base64"  # フォールバック

        # その他のファイル形式の場合はBASE64
        with open(file_path, "rb") as f:
            content = f.read()

        content_base64 = base64.b64encode(content).decode('utf-8')

        return {
            "filename": filename,
            "content_base64": content_base64,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "data_uri": f"data:{mime_type};base64,{content_base64[:100]}..." if len(content_base64) > 100 else f"data:{mime_type};base64,{content_base64}"
        }

    except Exception as e:
        logger.error(f"get_file_content error: {e}", exc_info=True)
        return {"error": f"ファイル読み込みエラー: {str(e)}"}






# Prompts機能 - LLMへの指示とユーザーへの注意喚起
@mcp.prompt
async def subsidy_search_guide():
    """
    補助金検索のガイドとベストプラクティス

    このプロンプトは、補助金検索を効果的に行うための指示を提供します。
    """
    return """
# jGrants補助金検索ガイド

## 検索時の注意事項
1. **キーワード選択**: 「補助金」「助成金」「事業」など複数のキーワードを試してください
2. **絞り込み条件**: 業種、従業員数、地域などで絞り込むと精度が向上します
3. **締切確認**: 募集終了日時を必ず確認してください

## データ利用時の重要事項
- 出典表示: 「Jグランツ（jGrants）からの出典」である旨を明記してください
- 最新情報: 詳細は公式サイト https://www.jgrants-portal.go.jp/ で確認してください
- API制限: 過度な連続アクセスは避けてください

## 推奨される使い方
1. まず広いキーワード（例: "事業"）で検索
2. 結果を確認して、必要に応じて絞り込み条件を追加
3. 気になる補助金の詳細をget_subsidy_detailで取得
4. PDFファイルがある場合はget_file_contentで内容確認
"""

@mcp.prompt
async def api_usage_agreement():
    """
    jGrants API利用に関する同意事項

    API利用前にユーザーに確認すべき事項を提示します。
    """
    return """
# jGrants API 利用同意事項

## 以下の点にご同意いただけますか？

1. **出典表示義務**
   - 取得した情報を公開する際は「Jグランツ（jGrants）」からの出典である旨を明記します

2. **情報の確認**
   - 取得した情報は参考情報として扱い、正式な申請前に公式サイトで最新情報を確認します

3. **適切な利用**
   - APIへの過度な連続アクセスを避け、サーバーに負荷をかけないよう配慮します

4. **個人情報の取り扱い**
   - 補助金申請に関する個人情報や企業情報を適切に管理します

これらの条件に同意の上、補助金検索を開始してください。
"""

@mcp.resource("jgrants://guidelines")
async def usage_guidelines():
    """
    jGrants MCP サーバー利用ガイドライン

    このリソースは常に参照可能な利用ガイドラインを提供します。
    """
    return """jGrants MCP サーバー利用ガイドライン

【重要な注意事項】
- 本サーバーはjGrants公開APIを使用しています
- 取得した情報の出典表示は必須です
- 正式な申請前に必ず公式サイトで最新情報を確認してください

【推奨される検索パターン】
1. 広いキーワードから始める: search_subsidies(keyword="事業")
2. 条件を追加して絞り込む: industry, target_area_search等を指定
3. 統計情報を確認: get_subsidy_statistics()
4. 詳細情報を取得: get_subsidy_detail(subsidy_id)

【API制限について】
- 連続的な大量アクセスは避けてください
- エラーが発生した場合は時間を置いて再試行してください
"""

def main():
    """メインエントリーポイント（Streamable HTTPサーバーモード）"""
    import argparse

    parser = argparse.ArgumentParser(description="jGrants MCP Server (FastMCP Streamable HTTP)")
    parser.add_argument("--host", default="127.0.0.1", help="ホスト (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="ポート (default: 8000)")

    args = parser.parse_args()

    # 常にStreamable HTTPサーバーを起動
    mcp.run(transport="streamable-http", host=args.host, port=args.port)


# ASGIアプリケーションをエクスポート
app = mcp.http_app()
# FastMCPアプリケーションの名前を設定
if hasattr(app, '__setattr__'):
    app.name = "jgrants-mcp-server"


if __name__ == "__main__":
    main()
