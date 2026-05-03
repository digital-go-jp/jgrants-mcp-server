# マルチステージビルド: 依存関係をビルドステージで解決し本番イメージを軽量化する
# Multi-stage build: resolve dependencies in builder stage to keep production image lean
# Build multi-tahap: selesaikan dependensi di tahap builder agar image produksi lebih ringan

FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.12-slim

# セキュリティ: 非rootユーザーで実行する
# Security: run as non-root user
# Keamanan: jalankan sebagai pengguna non-root
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY jgrants_mcp_server/ ./jgrants_mcp_server/

USER app

# Cloud Run はデフォルトで 8080 番を使用する
# Cloud Run uses port 8080 by default
# Cloud Run menggunakan port 8080 secara default
ENV PORT=8080

EXPOSE 8080

# stateless_http=True が有効なASGIアプリを uvicorn で起動する
# Start the stateless ASGI app with uvicorn
# Jalankan aplikasi ASGI stateless dengan uvicorn
CMD ["sh", "-c", "uvicorn jgrants_mcp_server.core:app --host 0.0.0.0 --port ${PORT}"]
