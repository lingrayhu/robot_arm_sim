# RM65 数字孪生 (MuJoCo)

用 MuJoCo 实时镜像睿尔曼 RM65 遥操作主臂的姿态。主臂通过 USB 串口读取，经 SSH 传到本机，写入仿真模型的关节角后渲染。

```
主臂(/dev/ttyUSB0) --远端--> SSH 数据流(每行 JSON) --本机--> MuJoCo qpos --> 窗口
```

## 目录说明

| 路径 | 说明 |
|---|---|
| `rm65_demo.py` | 最小仿真示例，只验证窗口和模型能否正常工作 |
| `rm65_twin.py` | 数字孪生主程序 |
| `models/rm65/` | RM65 + EG2-4C2 夹爪的 MJCF 模型和 STL |
| `rm_models/` | 睿尔曼官方模型库（多种型号的 URDF/STEP/图纸） |
| `build_portable.sh` | 打包成免安装目录 |
| `setup_env.sh` | 创建虚拟环境并安装依赖 |
| `config.json` | 连接配置（源码运行时使用） |
| `dist/rm65_twin/` | 打包好的免安装版本 |

## 方式一：直接用免安装包（推荐给使用者）

不需要 Python、不需要装依赖。

```bash
cd dist/rm65_twin
./run.sh            # 启动数字孪生
./run.sh demo       # 冒烟测试：只开窗口，不需要机械臂
```

第一次到新电脑上，先跑 `./run.sh demo`：能弹出 MuJoCo 窗口说明图形环境正常；开不了则是 GL/驱动问题，与机械臂无关。

改连接目标只需编辑同目录的 `config.json`，不用重新打包。

## 方式二：从源码运行（推荐给开发者）

虚拟环境不能跨机器拷贝，必须在本机重新创建。

```bash
./setup_env.sh                      # 创建 .venv 并安装 mujoco/numpy/paramiko
.venv/bin/python rm65_demo.py       # 冒烟测试
.venv/bin/python rm65_twin.py       # 数字孪生
```

如果提示缺少 venv 模块：

```bash
sudo apt install python3 python3-venv
```

## 配置文件

源码运行时读取仓库根目录的 `config.json`；打包版读取可执行文件同目录的 `config.json`。

```json
{
  "host": "219.216.72.60",
  "port": 2222,
  "user": "jy",
  "password": "123",
  "remote_python": "/home/jy/miniconda3/envs/aloha2/bin/python",
  "sign": "1,1,1,1,1,1",
  "offset": "0,0,0,0,0,0"
}
```

| 字段 | 说明 |
|---|---|
| `host` / `port` / `user` / `password` | 机械臂那台电脑的 SSH 连接信息 |
| `remote_python` | 远端用于读串口的 Python（需装 pyserial） |
| `sign` | 6 轴方向系数，某轴反向就改成 -1 |
| `offset` | 6 轴零位补偿，单位度 |

命令行参数优先级高于配置文件，例如 `--sign 1,-1,1,1,1,1`。

## 主臂端要求（机械臂那台电脑）

1. 主臂上电，USB 线连接，`/dev/ttyUSB0` 存在，当前用户在 `dialout` 组
2. 串口未被占用：`fuser /dev/ttyUSB0`
3. **不要同时运行**遥操作采集程序，两者会抢同一个串口
4. 该机器能被本机 SSH 访问（校园网 / VPN）

远端不需要安装任何额外程序——读取脚本由孪生程序临时注入执行。

## 常用参数

| 参数 | 说明 |
|---|---|
| `--no-viewer` | 不开窗口，只在终端打印关节角，用于排查链路 |
| `-d 10` | 运行 10 秒后退出 |
| `--sign 1,-1,1,1,1,1` | 逐轴翻转方向 |
| `--offset 0,-2.5,0,0,0,0` | 逐轴补偿零位（度） |
| `--host` / `--port` / `--user` / `--password` | 临时覆盖连接配置 |

## 打包

```bash
./build_portable.sh
```

产物在 `dist/rm65_twin/`，整个目录拷走即可。脚本会：

- 用 PyInstaller 打两个可执行程序（孪生 + 测试）
- 打包模型和 STL
- 排除构建环境的 `libstdc++`，避免覆盖目标系统的版本导致 Mesa 加载失败
- 生成 `run.sh`，启动前清理外部注入的 `LD_LIBRARY_PATH`/`LD_PRELOAD`

产物只能在同架构（x86_64）、glibc 不低于构建机的 Linux 上运行。

## 常见问题

| 现象 | 处理 |
|---|---|
| `GLX: Failed to find a suitable GLXFBConfig` / `could not create window` | 图形环境问题。在 IDE 终端里常见原因是 `LD_LIBRARY_PATH` 注入旧版 libstdc++，改用 `./run.sh` 或 `env -u LD_LIBRARY_PATH ./rm65_demo` |
| 卡在"连接..."后超时 | 网络不通，检查 VPN 或 `ping <host>` |
| "未收到主臂数据" | 串口被占用 / 主臂未上电 / `remote_python` 路径不对 |
| 关节角一直不变 | 远端有采集程序占着串口 |
| 某轴方向相反 | 改 `sign` 对应位为 -1 |
| 姿态整体有固定偏差 | 改 `offset`，填"期望值 − 实测值" |
| 运行中断一下又恢复 | 网络抖动，程序会自动重连 |

## 实现要点

- 主臂串口协议：发送 `55 AA 02 00 00 67`，返回固定 42 字节帧 `AA 55 ...`，6 个关节为 int32 小端 ÷10000（单位：度），夹爪为字节 37 处的 int32（0~1000）
- 遥操作本身把主臂角度原样透传给从臂，因此仿真侧只需度转弧度，无需额外变换
- 仿真采用纯运动学镜像（写 `qpos` + `mj_forward`），没有伺服滞后
- 夹爪在模型里 0 为完全闭合、0.82 rad 为完全张开
