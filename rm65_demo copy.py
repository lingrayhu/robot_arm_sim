"""RM65-B 在 MuJoCo 中的最小示例.

运行: python rm65_demo.py
关节由位置伺服驱动, 目标位姿在 TARGET 中修改(单位: 弧度).
"""

from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np

MODEL_PATH = Path(__file__).parent / "models" / "rm65" / "scene.xml"

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
    while viewer.is_running():
        mujoco.mj_step(model, data)
        viewer.sync()
