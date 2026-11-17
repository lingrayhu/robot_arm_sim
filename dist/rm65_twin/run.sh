#!/usr/bin/env bash
# 用法: ./run.sh        启动数字孪生
#       ./run.sh demo   启动冒烟测试
cd "$(dirname "$0")" || exit 1

# 免安装包的环境要求: x86_64 + glibc >= 2.34 (Ubuntu 22.04 及以上)
if [ "$(uname -m)" != "x86_64" ]; then
  echo "此免安装包仅支持 x86_64, 当前架构: $(uname -m)"
  echo "请改用源码方式: cd ../.. && ./setup_env.sh"
  exit 1
fi

glibc=$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$')
if [ -n "$glibc" ]; then
  major=${glibc%%.*}
  minor=${glibc#*.}
  if [ "$major" -lt 2 ] || { [ "$major" -eq 2 ] && [ "$minor" -lt 34 ]; }; then
    echo "需要 glibc >= 2.34, 当前为 $glibc"
    echo "请改用源码方式: cd ../.. && ./setup_env.sh"
    exit 1
  fi
fi

prog=./rm65_twin
[ "${1:-}" = "demo" ] && prog=./rm65_demo
exec env -u LD_LIBRARY_PATH -u LD_PRELOAD "$prog"
