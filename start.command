#!/bin/bash
cd "$(dirname "$0")"
echo "Starting EchoLab (website and processing queue)..."
python3 serve.py
