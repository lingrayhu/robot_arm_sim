"""RM65-B 在 MuJoCo 中的最小示例.

运行: python rm65_demo.py
关节由位置伺服驱动, 目标位姿在 TARGET 中修改(单位: 弧度).
"""

import sys
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np

# 打包后资源解压到 _MEIPASS, 源码运行时在脚本目录
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
MODEL_PATH = BASE / "models" / "rm65" / "scene.xml"

# 目标: 6 个臂关节角度 (rad) + 夹爪左右指根关节 (rad, 0=张开, ±0.82=闭合)
TARGET = np.array([0.4, -0.4, 0.3, 0.2, -0.3, 0.5, 0.4, -0.4])

model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
data = mujoco.MjData(model)
mujoco.mj_resetDataKeyframe(model, data, 0)  # 回到 home 关键帧
data.ctrl[:] = TARGET  # 初始目标位姿, 之后可在界面 Control 面板里自由拖动修改

print("joints   :", [model.joint(i).name for i in range(model.njnt)])
print("actuators:", [model.actuator(i).name for i in range(model.nu)])
print("ctrlrange:", np.round(model.actuator_ctrlrange, 3))

with mujoco.viewer.launch_passive(model, data) as viewer:
    # 初始视角: 绕 Z 轴转 180 度, 从另一侧回看机械臂
    viewer.cam.azimuth = 180.0
    while viewer.is_running():
        mujoco.mj_step(model, data)
        viewer.sync()
