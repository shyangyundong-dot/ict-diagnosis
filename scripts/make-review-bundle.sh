#!/usr/bin/env bash
# 生成「仅源码」审查包：仅包含 Git 已跟踪文件（当前工作区内容），
# 不含 node_modules、构建产物、data/、.env 等未跟踪或已忽略文件。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "错误：当前目录不是 Git 仓库。" >&2
  exit 1
fi

OUT_DIR="${ROOT}/review-bundles"
mkdir -p "$OUT_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
NAME="ict-diagnosis-review-${STAMP}.zip"
OUT="${OUT_DIR}/${NAME}"

# 从仓库根目录打包 git ls-files 列出的路径（与 .gitignore 一致，仅已跟踪文件）
if [[ "$(git ls-files | wc -l | tr -d ' ')" -eq 0 ]]; then
  echo "错误：没有已跟踪的文件，无法生成审查包。" >&2
  exit 1
fi

N="$(git ls-files | wc -l | tr -d ' ')"
git ls-files | zip -q "$OUT" -@

echo "已生成: ${OUT}"
echo "包含: ${N} 个已跟踪文件（不含 node_modules / data / .env 等）"
