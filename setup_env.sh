#!/usr/bin/env bash
# 创建本地虚拟环境 .venv 并安装依赖
# 用法: ./setup_env.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || {
  echo "未找到 $PY, 请先安装 Python 3.10+ (Ubuntu: sudo apt install python3 python3-venv)"
  exit 1
}

# 检查 Python 版本
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "需要 Python 3.10 或更高版本, 当前: $("$PY" -V 2>&1)"
  exit 1
}

if [ ! -x .venv/bin/python ]; then
  # 上次创建失败会留下残缺目录, 先清掉
  rm -rf .venv
  echo "创建虚拟环境 .venv (基于 $("$PY" -V 2>&1)) ..."
  if ! "$PY" -m venv .venv; then
    rm -rf .venv
    PYVER=$("$PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
    echo
    echo "创建失败: 系统缺少 venv/ensurepip 模块。"
    echo "请先安装对应软件包, 然后重新运行本脚本:"
    echo
    echo "  sudo apt install python3-venv python3.${PYVER}-venv"
    echo
    exit 1
  fi
else
  echo "已存在 .venv, 直接更新依赖"
fi

echo "安装依赖 (mujoco / numpy / paramiko / pyinstaller) ..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q mujoco numpy paramiko pyinstaller

echo
.venv/bin/python - <<'EOF'
import mujoco
import numpy
import paramiko

print("环境就绪  mujoco", mujoco.__version__, "| numpy", numpy.__version__,
      "| paramiko", paramiko.__version__)
EOF

echo
echo "下一步:"
echo "  冒烟测试(不需要机械臂): .venv/bin/python rm65_demo.py"
echo "  数字孪生:               .venv/bin/python rm65_twin.py"
echo "  重新打包:               ./build_portable.sh"
