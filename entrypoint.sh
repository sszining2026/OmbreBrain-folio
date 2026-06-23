#!/bin/sh
# entrypoint.sh — 容器启动入口
#
# 职责：确保 /app/config.yaml 是一个可用的文件再启动服务。
# 不做其他事（不改路径、不改环境变量）。
#
# 问题背景：
#   docker-compose 把宿主 config.yaml 挂进容器。若宿主路径不存在，
#   Docker 会在宿主创建一个同名目录，mount 进来后 /app/config.yaml
#   变成目录而非文件，服务启动失败。
#
# 处理逻辑：
#   1. 若 /app/config.yaml 是目录（Docker 的副作用）→ 删掉目录，
#      从内置备份复制一份写到同路径（同时写回宿主，下次就有文件了）。
#   2. 若 /app/config.yaml 不存在 → 同上。
#   3. 若是正常文件 → 直接启动，不干预。

CONFIG=/app/config.yaml
DEFAULT=/app/config.default.yaml

if [ -d "$CONFIG" ]; then
    echo "[entrypoint] config.yaml is a directory (Docker created it because host file was missing)."
    echo "[entrypoint] Removing directory and initializing from defaults..."
    rmdir "$CONFIG" 2>/dev/null || rm -rf "$CONFIG"
    cp "$DEFAULT" "$CONFIG"
    echo "[entrypoint] config.yaml initialized. Edit it on the host to customize."
elif [ ! -f "$CONFIG" ]; then
    echo "[entrypoint] config.yaml not found, initializing from defaults..."
    cp "$DEFAULT" "$CONFIG"
    echo "[entrypoint] config.yaml initialized."
fi

exec python src/server.py
