#!/usr/bin/env bash
# 为 Gemini 等工具生成审查材料（避开「ZIP 内最多 10 个文件」限制）：
# - 默认：按目录合并为少量 .txt（≤10），再打成 ZIP；每个 ZIP 内文件数 ≤10，仅文本。
# - --single：全部合并为 1 个 .txt，可直接上传该文件（不必再用 ZIP）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "错误：当前目录不是 Git 仓库。" >&2
  exit 1
fi

SINGLE=0
if [[ "${1:-}" == "--single" ]]; then
  SINGLE=1
fi

OUT_DIR="${ROOT}/review-bundles"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="${OUT_DIR}/gemini-${STAMP}"
mkdir -p "$WORK"

append_file() {
  local dest="$1"
  local rel="$2"
  printf '\n\n======== FILE: %s ========\n\n' "$rel" >>"$dest"
  cat "$rel" >>"$dest"
}

# 仅包含 git 已跟踪且磁盘存在的路径
tracked() { git ls-files "$@" 2>/dev/null | sort; }

if [[ "$SINGLE" -eq 1 ]]; then
  SINGLE_OUT="${WORK}/ict-diagnosis-full-codebase.txt"
  : >"$SINGLE_OUT"
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    append_file "$SINGLE_OUT" "$f"
  done < <(tracked)

  SZ="$(wc -c <"$SINGLE_OUT" | tr -d ' ')"
  echo "已生成（单文件，可直接上传）: ${SINGLE_OUT}"
  echo "大小: ${SZ} 字节（上限约 100 MB）"
  exit 0
fi

# 分卷：每卷一个 .txt，ZIP 内总文件数 ≤ 10
CHUNK_META="${WORK}/01-repo-root-and-deploy.txt"
CHUNK_PY="${WORK}/02-backend-python.txt"
CHUNK_RULES="${WORK}/03-backend-rules-json.txt"
CHUNK_FE_CFG="${WORK}/04-frontend-config-and-lock.txt"
CHUNK_FE_SRC="${WORK}/05-frontend-src.txt"

: >"$CHUNK_META"
for f in $(tracked README.md .gitignore start.sh deploy/); do
  [[ -f "$f" ]] || continue
  append_file "$CHUNK_META" "$f"
done

: >"$CHUNK_PY"
while IFS= read -r f; do
  [[ "$f" == *.py ]] || continue
  append_file "$CHUNK_PY" "$f"
done < <(tracked "backend/")

: >"$CHUNK_RULES"
for f in backend/rules/rules.json backend/rules/clauses.json; do
  [[ -f "$f" ]] || continue
  append_file "$CHUNK_RULES" "$f"
done

: >"$CHUNK_FE_CFG"
for f in frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/index.html; do
  [[ -f "$f" ]] || continue
  append_file "$CHUNK_FE_CFG" "$f"
done

: >"$CHUNK_FE_SRC"
while IFS= read -r f; do
  append_file "$CHUNK_FE_SRC" "$f"
done < <(tracked "frontend/src/")

ZIP_OUT="${OUT_DIR}/ict-diagnosis-gemini-${STAMP}.zip"
(
  cd "$WORK"
  zip -q "$ZIP_OUT" ./*.txt
)

N="$(ls -1 "$WORK"/*.txt 2>/dev/null | wc -l | tr -d ' ')"
echo "已生成目录: ${WORK}"
echo "已生成 ZIP（内仅 ${N} 个 .txt，≤10）: ${ZIP_OUT}"
echo "提示: 若仍超限，可使用: $0 --single 生成单个 txt 后直接上传该文件。"
