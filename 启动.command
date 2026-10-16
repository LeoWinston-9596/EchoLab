#!/bin/bash
cd "$(dirname "$0")"
echo "正在启动 EchoLab(网页 + 自动解析队列)..."
python3 serve.py
