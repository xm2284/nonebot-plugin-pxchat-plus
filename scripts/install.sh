#!/usr/bin/env bash
# 把补丁热打到运行中的容器（不重建镜像）。
# 用法: scripts/install.sh <容器名>
set -euo pipefail

CONTAINER="${1:?用法: install.sh <容器名>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker cp "$SCRIPT_DIR/patches/patch_pxchat.py"       "$CONTAINER:/tmp/"
docker cp "$SCRIPT_DIR/patches/patch_pxchat_fixes.py" "$CONTAINER:/tmp/"
docker cp "$SCRIPT_DIR/patches/apply_pergroup.py"     "$CONTAINER:/tmp/"

docker exec "$CONTAINER" python3 /tmp/patch_pxchat.py
docker exec "$CONTAINER" python3 /tmp/apply_pergroup.py
docker exec "$CONTAINER" python3 /tmp/patch_pxchat_fixes.py

docker restart "$CONTAINER"
echo "补丁已应用，容器已重启。"
