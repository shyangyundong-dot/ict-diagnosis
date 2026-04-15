#!/bin/bash
# ICT项目合规诊断工具 — 一键启动脚本 (Mac)

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

echo ""
echo "🛡  ICT项目合规诊断工具"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if ! command -v python3 &>/dev/null; then
  echo "❌ 未找到 python3，请先安装 Python 3.10+"
  exit 1
fi
if ! command -v node &>/dev/null; then
  echo "❌ 未找到 node，请先安装 Node.js 18+"
  exit 1
fi

# 选用兼容依赖的 Python（3.14 与当前 pydantic 等不兼容，优先 3.11–3.13）
PYTHON_BIN=""
for cand in python3.12 python3.11 python3.13; do
  if command -v "$cand" &>/dev/null; then
    PYTHON_BIN=$(command -v "$cand")
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN=$(command -v python3)
  PY_VER=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "?")
  if [ "$PY_VER" = "3.14" ] || [ "$PY_VER" = "3.15" ]; then
    echo "❌ 当前默认 python3 为 ${PY_VER}，与本项目依赖不兼容。"
    echo "   请安装 Python 3.11–3.13（如 brew install python@3.11），然后重新运行本脚本。"
    exit 1
  fi
  echo "⚠️  未找到 python3.11–3.13，将使用: $PYTHON_BIN"
fi

echo "🐍 使用 Python: $PYTHON_BIN"

# 虚拟环境
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "📦 创建后端虚拟环境..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "📦 安装后端依赖..."
"$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

# 安装前端依赖
echo "📦 检查前端依赖..."
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
  npm install --silent
fi

# 启动后端
echo ""
echo "🚀 启动后端 (http://127.0.0.1:8000)..."
cd "$BACKEND_DIR"
"$VENV_DIR/bin/uvicorn" main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# 等待 /api/health 就绪（失败则退出，避免前端空跑）
echo "⏳ 等待后端就绪..."
READY=0
for _ in {1..30}; do
  if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo ""
  echo "❌ 后端未在 8000 端口就绪（/api/health 无响应）。"
  echo "   请在本目录执行以下命令查看报错："
  echo "   cd backend && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000"
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi

# 启动前端
echo "🚀 启动前端 (http://localhost:5173)..."
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 启动成功！"
echo ""
echo "   🌐 访问地址: http://localhost:5173"
echo "   📡 后端API:  http://127.0.0.1:8000"
echo "   📋 API文档:  http://127.0.0.1:8000/docs"
echo ""
echo "   按 Ctrl+C 停止所有服务"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

sleep 3
open http://localhost:5173 2>/dev/null || true

cleanup() {
  echo ""
  echo "⏹  正在停止服务..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  echo "👋 已停止"
  exit 0
}
trap cleanup SIGINT SIGTERM

wait
