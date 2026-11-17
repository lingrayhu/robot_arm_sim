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

apt_hint() {
  PYVER=$("$PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
  echo
  echo "$1"
  echo "请先安装对应软件包, 然后重新运行本脚本:"
  echo
  echo "  sudo apt install python3-venv python3.${PYVER}-venv"
  echo
  exit 1
}

# venv 必须同时具备 python 和 pip, 且 python 确实运行在虚拟环境内才算可用
# (venv 创建中途失败时 .venv/bin/python 会残留; 若它只是系统 python 的软链,
#  系统 pip 会被误认为可用, 所以还要校验 sys.prefix)
venv_usable() {
  [ -x .venv/bin/python ] || return 1
  [ -x .venv/bin/pip ] || return 1
  .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' 2>/dev/null
}

if ! venv_usable; then
  rm -rf .venv
  echo "创建虚拟环境 .venv (基于 $("$PY" -V 2>&1)) ..."
  if ! "$PY" -m venv .venv; then
    rm -rf .venv
    apt_hint "创建失败: 系统缺少 venv/ensurepip 模块。"
  fi
  if ! venv_usable; then
    rm -rf .venv
    apt_hint "虚拟环境缺少 pip: 系统未提供 ensurepip 支持。"
  fi
else
  echo "已存在可用 .venv, 直接更新依赖"
fi

echo "安装依赖 (mujoco / numpy / paramiko / pyinstaller) ..."
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q mujoco numpy paramiko pyinstaller

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
