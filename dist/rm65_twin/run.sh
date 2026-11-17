#!/usr/bin/env bash
# 用法: ./run.sh        启动数字孪生
#       ./run.sh demo   启动冒烟测试
cd "$(dirname "$0")" || exit 1
prog=./rm65_twin
[ "${1:-}" = "demo" ] && prog=./rm65_demo
exec env -u LD_LIBRARY_PATH -u LD_PRELOAD "$prog"
