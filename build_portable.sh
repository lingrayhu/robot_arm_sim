#!/usr/bin/env bash
# 一键打包: 生成可整目录拷走的免安装版本 dist/rm65_twin/
# 目录内容:
#   rm65_twin    数字孪生主程序
#   rm65_demo    环境冒烟测试(不需要机械臂, 只验证窗口能否正常渲染)
#   config.json  连接配置
# 用法: ./build_portable.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
[ -x "$PY" ] || { echo "未找到 .venv, 请先创建虚拟环境并安装依赖"; exit 1; }

.venv/bin/pip install -q pyinstaller
rm -rf build dist

# 1) 数字孪生主程序
"$PY" -m PyInstaller \
  --noconfirm --clean --onedir --name rm65_twin \
  --add-data "models/rm65:models/rm65" \
  --collect-all mujoco \
  --collect-all glfw \
  rm65_twin.py

# 2) 冒烟测试程序(资源目录用 _internal_demo, 避免和主程序冲突)
"$PY" -m PyInstaller \
  --noconfirm --clean --onedir --name rm65_demo \
  --contents-directory _internal_demo \
  --add-data "models/rm65:models/rm65" \
  --collect-all mujoco \
  --collect-all glfw \
  rm65_demo.py

# 3) 合并到同一个交付目录
cp dist/rm65_demo/rm65_demo dist/rm65_twin/
cp -r dist/rm65_demo/_internal_demo dist/rm65_twin/
rm -rf dist/rm65_demo

# 4) 去掉打包进来的 libstdc++: 构建环境自带的版本可能过旧, 缺少
#    GLIBCXX_3.4.26, 会让系统 Mesa(libgallium) 加载失败 -> 窗口建不出来。
#    删掉后用目标系统自带的 libstdc++, 兼容性更好。
rm -f dist/rm65_twin/_internal/libstdc++.so.6* dist/rm65_twin/_internal_demo/libstdc++.so.6*

cp config.json dist/rm65_twin/

# 5) 启动脚本: 清掉外部注入的 LD_LIBRARY_PATH/LD_PRELOAD
#    (IDE 终端、某些运行环境会注入旧版 libstdc++, 导致 Mesa 加载失败)
cat > dist/rm65_twin/run.sh <<'EOF'
#!/usr/bin/env bash
# 用法: ./run.sh        启动数字孪生
#       ./run.sh demo   启动冒烟测试
cd "$(dirname "$0")" || exit 1
prog=./rm65_twin
[ "${1:-}" = "demo" ] && prog=./rm65_demo
exec env -u LD_LIBRARY_PATH -u LD_PRELOAD "$prog"
EOF
chmod +x dist/rm65_twin/run.sh

echo
echo "打包完成: dist/rm65_twin/"
echo "  数字孪生: ./run.sh         (或 ./rm65_twin)"
echo "  冒烟测试: ./run.sh demo    (或 ./rm65_demo)"
