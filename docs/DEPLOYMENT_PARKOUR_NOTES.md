# 部署说明与检查清单 — Instinct-Parkour-Target-Amp-G1-v0

日期：2026-03-28

## 概要
本文件汇总对将训练好的 `Instinct-Parkour-Target-Amp-G1-v0` 策略部署到笔记本（作为策略主机，而不部署到机器人 Jetson）所做的代码检查、关键发现、最小可行部署步骤、运行前检查项与当前代办事项状态。

## 关键发现（代码定位）
- ONNX 加载：`ParkourAgent` 在 `logdir/exported` 中加载模型，期望存在 `0-depth_encoder.onnx` 与 `actor.onnx`（参见 `instinct_onboard/agents/parkour_agent.py`）。
- 导出入口：训练端通过 play.py 的 `--exportonnx` 将模型导出到 `logdir/exported`（参见 parkour 的 play 脚本）。
- 启动脚本：运行入口脚本为 `instinct_onboard/scripts/g1_parkour.py`（需要 `--logdir` 与 `--standdir`）。
- 摄像头：RealSense 管理在 `instinct_onboard/ros_nodes/realsense.py`，支持单进程或独立进程采集并通过共享内存传输深度图。
- 机器人接口：Unitree ROS 接口在 `instinct_onboard/ros_nodes/unitree.py`，发布/订阅话题包括 `/lowcmd`（写入时可能带 dryrun 后缀）、`/lowstate`、无线控制话题等。
- 依赖：`instinct_onboard/setup.py` 会自动选择 `onnxruntime-gpu` 或 `onnxruntime`，还依赖 `pyrealsense2`、`ros2_numpy`、ROS2 环境、以及 `unitree_go`/`unitree_hg` 消息包与 `crc_module.so`。

## 在笔记本上部署的最小可行流程（摘要）
1. 安装与准备环境（示例，假设 Ubuntu22.04 + ROS2 Humble）：

```bash
# source ROS2
source /opt/ros/humble/setup.bash

# Python virtualenv
python3 -m venv ~/instinct_venv
source ~/instinct_venv/bin/activate

# 安装 instinct_onboard（根据是否有 CUDA，可用 FORCE_CPU=1 强制 CPU）
cd /home/xinyu/Projects/HKUST/Instinct/instinct_onboard
# 若无 GPU 强制 CPU： FORCE_CPU=1 pip install -e .
pip install -e .
```

2. 准备 ROS 消息包与 crc 模块：

```bash
# 在笔记本上构建 unitree 消息包的工作区（示例）
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
# git clone unitree_go 与 unitree_hg repo
cd ~/ros2_ws
colcon build
source install/setup.bash

# 把 crc_module.so 放到运行脚本同目录或设置 LD_LIBRARY_PATH
```

3. 导出并拷贝模型（训练主机 -> 笔记本）：

```bash
# 在训练主机上导出（若尚未导出）
python source/instinctlab/instinctlab/tasks/parkour/scripts/play.py \
  --task=Instinct-Parkour-Target-Amp-G1-v0 --load_run=<your_run> --exportonnx

# 将包含 params/ 与 exported/ 的 logdir 拷贝到笔记本
rsync -avz user@train_host:/path/to/logdir ~/parkour_model_run
```

4. 本地验证 ONNX 与摄像头：

```bash
python3 - <<'PY'
import onnxruntime as ort
ort.InferenceSession("/home/youruser/parkour_model_run/exported/actor.onnx")
print("ONNX load OK")
PY

# 检查 RealSense
python3 - <<'PY'
import pyrealsense2 as rs
print(rs)
PY
```

5. 启动节点（先 dryrun）

```bash
# dryrun 模式（默认），不會下发到真实电机
python /home/xinyu/Projects/HKUST/Instinct/instinct_onboard/scripts/g1_parkour.py \
  --logdir /home/youruser/parkour_model_run \
  --standdir /home/youruser/stand_model_run \
  --depth_vis --pointcloud_vis

# 若确认安全并在同一 ROS 网络后，加 --nodryrun 允许下发实际命令
```

## 运行前关键检查（必做）
- 文件完整性：`logdir/params/env.yaml`、`logdir/params/agent.yaml`、`logdir/exported/actor.onnx`、`logdir/exported/0-depth_encoder.onnx` 必须存在。
- ONNX 推理：使用 `onnxruntime` 能成功创建 `InferenceSession`。
- RealSense 可用：能用 `pyrealsense2` 读取深度帧。
- ROS 话题与消息：启动 node 后通过 `ros2 topic list` / `ros2 topic echo` 验证话题；确认消息类型 `unitree_go` / `unitree_hg` 可用。
- 安全策略：在真实机器人上运行前，始终先 dryrun、确认动作发布到 dryrun 话题并保证物理防护措施到位。

## 网络与机器人互联要点
- 确保笔记本与机器人 Jetson 在同一 ROS2 网络（相同 `ROS_DOMAIN_ID` 或能互相发现 DDS 多播）。
- 若跨子网或有防火墙，允许 DDS/ROS2 必要端口或关闭防火墙以便发现。
- 若选择把策略运行在笔记本上而机器人接受命令，需保证机器人订阅的 `lowcmd` 话题与笔记本发布的 topic 名相匹配（注意 dryrun 时脚本会生成独特的发布 topic 后缀）。

## 当前代办事项（来自 manage_todo_list）
- **已完成**: 定位训练输出与模型文件
- **已完成**: 定位并阅读策略加载与推理代码
- **进行中**: 检查机器人/主机通信（ROS/UDP/MQTT）与端口配置
- **未开始**: 检查运行环境与依赖（Python、CUDA、ROS 版本）
- **未开始**: 整理在笔记本上部署的逐步指引与命令
- **未开始**: 列出验证与回滚测试步骤

## 我可以接着帮你的选项
- 帮你检查指定 `logdir` 的文件完整性并尝试在笔记本上加载 ONNX（请提供路径）。
- 根据笔记本的系统与是否有 CUDA，生成精确的安装命令与依赖安装脚本。
- 生成一个安全的启动脚本（先 dryrun、低速率动作验证、再切换到实际下发）。

---
文件位置：`instinct_onboard/DEPLOYMENT_PARKOUR_NOTES.md`

如需我现在检查某个 `logdir`（路径），或者根据你的笔记本生成具体安装命令，请把路径或笔记本环境信息发来。
