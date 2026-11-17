"""RM65 数字孪生: 本机 MuJoCo 实时镜像远端遥操作主臂姿态.

数据链路
    主臂(/dev/ttyUSB0, 42字节帧)  --远端-->  SSH 流(每行一个 JSON)  --本机-->  MuJoCo qpos -> 渲染

用法
    python rm65_twin.py                      # 打开 MuJoCo 窗口实时跟随
    python rm65_twin.py --no-viewer -d 5     # 不开窗, 只打印 5 秒关节角
    python rm65_twin.py --sign -1,1,1,1,1,1  # 某一轴方向反了时单独翻转

说明
    主臂角度单位是度; 从臂遥操作时直接把主臂角度透传给 rm_movej_canfd,
    因此这里无需额外变换, 只需 deg->rad。若实物零位与仿真零位有偏差, 用 --offset 补偿。
"""

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np


def app_dir():
    """可执行文件所在目录: 打包后是 exe 所在目录, 源码运行时是脚本目录."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def resource_root():
    """只读资源(models/)的根目录: PyInstaller 单目录包解压到 _MEIPASS."""
    return Path(getattr(sys, "_MEIPASS", app_dir()))


MODEL_PATH = resource_root() / "models" / "rm65" / "scene.xml"
CONFIG_PATH = app_dir() / "config.json"

DEFAULT_CONFIG = {
    "host": "219.216.72.60",
    "port": 2222,
    "user": "jy",
    "password": "123",
    "remote_python": "/home/jy/miniconda3/envs/aloha2/bin/python",
    "sign": "1,1,1,1,1,1",
    "offset": "0,0,0,0,0,0",
    "ee_rot": 0.0,
}

ARM_JOINTS = [f"joint_{i}" for i in range(1, 7)]
GRIPPER_FINGER = "4C2_Joint1"  # 指根关节, 0=完全闭合, 0.82 rad=完全张开

# 远端读取脚本: 通过 `python -u -` 从 stdin 注入, 不落盘
REMOTE_SOURCE = r'''
import json, struct, sys, time
import serial

SERIAL_PORT = "/dev/ttyUSB0"
BAUD = 460800
QUERY = bytes.fromhex("55AA02000067")
FRAME_LEN = 42
JOINT_OFFSETS = (7, 12, 17, 22, 27, 32)
GRIPPER_OFFSET = 37

ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0.05)
ser.write(QUERY)
time.sleep(0.3)
ser.reset_input_buffer()

while True:
    ser.reset_input_buffer()
    ser.write(QUERY)
    buf = b""
    while len(buf) < FRAME_LEN:
        chunk = ser.read(FRAME_LEN - len(buf))
        if not chunk:
            break
        buf += chunk
    if len(buf) < FRAME_LEN or buf[0] != 0xAA or buf[1] != 0x55:
        continue
    joints = [struct.unpack_from("<i", buf, o)[0] / 10000.0 for o in JOINT_OFFSETS]
    gripper = struct.unpack_from("<i", buf, GRIPPER_OFFSET)[0]
    sys.stdout.write(json.dumps({"q": joints, "g": gripper}) + "\n")
    sys.stdout.flush()
    time.sleep(0.01)
'''


class MasterStream(threading.Thread):
    """后台线程: 读远端主臂关节角, 断线自动重连."""

    def __init__(self, host, port, user, password, remote_python):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.remote_python = remote_python
        self.lock = threading.Lock()
        self.q_deg = None
        self.gripper = None
        self.stamp = 0.0
        self.count = 0
        self.status = "connecting"
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def snapshot(self):
        with self.lock:
            return self.q_deg, self.gripper, self.stamp

    def run(self):
        import paramiko

        while not self._stop.is_set():
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                self.status = f"ssh {self.user}@{self.host}:{self.port}"
                client.connect(self.host, port=self.port, username=self.user,
                               password=self.password, timeout=10,
                               banner_timeout=20, auth_timeout=20,
                               look_for_keys=False, allow_agent=False)
                stdin, stdout, stderr = client.exec_command(
                    f"{self.remote_python} -u -", get_pty=False)
                stdin.write(REMOTE_SOURCE)
                stdin.flush()
                stdin.channel.shutdown_write()
                self.status = "streaming"

                for line in iter(stdout.readline, ""):
                    if self._stop.is_set():
                        break
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    with self.lock:
                        self.q_deg = data["q"]
                        self.gripper = data["g"]
                        self.stamp = time.time()
                        self.count += 1
                self.status = "stream ended"
            except Exception as exc:  # 断线/连不上, 1 秒后重试
                self.status = f"error: {type(exc).__name__}: {exc}"
            finally:
                client.close()
            if not self._stop.is_set():
                self.status += " (retry in 1s)"
                self._stop.wait(1.0)


def build_joint_maps(model):
    arm_adr = [model.joint(name).qposadr[0] for name in ARM_JOINTS]
    finger_max = model.joint(GRIPPER_FINGER).range[1]  # 0.82 rad = 完全闭合
    # 4C2 夹爪 6 个关节里只有两个主动, 其余由 equality 随动; 纯运动学显示需直接写全
    gripper = {
        "4C2_Joint1": (model.joint("4C2_Joint1").qposadr[0], +1),
        "4C2_Joint2": (model.joint("4C2_Joint2").qposadr[0], +1),
        "4C2_Joint3": (model.joint("4C2_Joint3").qposadr[0], -1),
        "4C2_Joint4": (model.joint("4C2_Joint4").qposadr[0], -1),
        "4C2_Joint5": (model.joint("4C2_Joint5").qposadr[0], +1),
        "4C2_Joint6": (model.joint("4C2_Joint6").qposadr[0], +1),
    }
    return arm_adr, finger_max, gripper


def apply_pose(model, data, arm_adr, finger_max, gripper, q_deg, grip_raw, sign, offset_deg, ee_rot=0.0):
    q_target = sign * np.asarray(q_deg) + offset_deg
    q_target[5] += ee_rot  # 末端执行器绕工具轴的额外旋转(度)
    q_rad = np.deg2rad(q_target)
    lo = model.jnt_range[[model.joint(n).id for n in ARM_JOINTS], 0]
    hi = model.jnt_range[[model.joint(n).id for n in ARM_JOINTS], 1]
    data.qpos[arm_adr] = np.clip(q_rad, lo, hi)

    open_frac = float(np.clip(grip_raw / 1000.0, 0.0, 1.0))  # 主臂 0=闭合, 1000=全开
    finger = finger_max * open_frac
    for _, (adr, dir_) in gripper.items():
        data.qpos[adr] = dir_ * finger


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"config.json 读取失败, 使用默认值: {exc}")
    return cfg


def main():
    cfg = load_config()
    parser = argparse.ArgumentParser(description="RM65 数字孪生 (远端主臂 -> 本机 MuJoCo)")
    parser.add_argument("--host", default=cfg["host"])
    parser.add_argument("--port", type=int, default=cfg["port"])
    parser.add_argument("--user", default=cfg["user"])
    parser.add_argument("--password", default=cfg["password"])
    parser.add_argument("--remote-python", default=cfg["remote_python"])
    parser.add_argument("--sign", default=cfg["sign"], help="6 轴方向系数, 逗号分隔")
    parser.add_argument("--offset", default=cfg["offset"], help="6 轴零位补偿(度), 逗号分隔")
    parser.add_argument("--ee-rot", type=float, default=float(cfg.get("ee_rot", 0.0)),
                        help="末端执行器绕工具轴额外旋转(度), 用于修正夹爪朝向偏差")
    parser.add_argument("--no-viewer", action="store_true", help="不开窗口, 仅打印")
    parser.add_argument("-d", "--duration", type=float, default=0.0, help="运行秒数, 0=一直运行")
    args = parser.parse_args()

    sign = np.array([float(x) for x in args.sign.split(",")])
    offset_deg = np.array([float(x) for x in args.offset.split(",")])

    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    arm_adr, finger_max, gripper = build_joint_maps(model)

    stream = MasterStream(args.host, args.port, args.user, args.password, args.remote_python)
    stream.start()

    print(f"连接 {args.user}@{args.host}:{args.port} ...")
    t_wait = time.time()
    while stream.snapshot()[0] is None and time.time() - t_wait < 20:
        if "error" in stream.status:
            print("  " + stream.status)
        time.sleep(0.3)
    if stream.snapshot()[0] is None:
        print("未收到主臂数据, 退出。状态:", stream.status)
        stream.stop()
        return 1
    print("主臂数据已就绪:", np.round(stream.snapshot()[0], 3))
    if args.ee_rot:
        print(f"末端执行器附加旋转: {args.ee_rot:+.1f} 度")

    start = time.time()
    last_print = start
    last_count = 0

    if args.no_viewer:
        while True:
            q, g, _ = stream.snapshot()
            if q is not None:
                apply_pose(model, data, arm_adr, finger_max, gripper, q, g, sign, offset_deg, args.ee_rot)
                mujoco.mj_forward(model, data)
            now = time.time()
            if now - last_print >= 1.0:
                hz = (stream.count - last_count) / (now - last_print)
                print(f"[{now - start:5.1f}s] {hz:5.1f} Hz  q(deg)={np.round(q, 2)}  grip={g}")
                last_print, last_count = now, stream.count
            if args.duration and now - start >= args.duration:
                break
            time.sleep(1 / 120)
    else:
        with mujoco.viewer.launch_passive(model, data) as viewer:
            # 初始视角: 与 rm65_demo.py 一致, 绕 Z 轴转 180 度
            viewer.cam.azimuth = 180.0
            while viewer.is_running():
                q, g, _ = stream.snapshot()
                if q is not None:
                    apply_pose(model, data, arm_adr, finger_max, gripper, q, g, sign, offset_deg, args.ee_rot)
                    mujoco.mj_forward(model, data)
                viewer.sync()
                now = time.time()
                if now - last_print >= 2.0:
                    hz = (stream.count - last_count) / (now - last_print)
                    print(f"{hz:5.1f} Hz  q(deg)={np.round(q, 2)}  grip={g}")
                    last_print, last_count = now, stream.count
                if args.duration and now - start >= args.duration:
                    break
                time.sleep(1 / 120)

    stream.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
