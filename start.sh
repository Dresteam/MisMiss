#!/usr/bin/env bash
# 快捷入口 → 实际脚本在 scripts/start.sh
cd "$(dirname "$0")"
exec bash scripts/start.sh "$@"
