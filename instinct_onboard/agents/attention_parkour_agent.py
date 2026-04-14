from __future__ import annotations

import os

import numpy as np
import onnxruntime as ort
import ros2_numpy as rnp
from sensor_msgs.msg import Image

from instinct_onboard.agents.parkour_agent import ParkourAgent


class AttentionParkourAgent(ParkourAgent):
    """Parkour agent variant for attention-based parkour checkpoints.

    It keeps the same robot/action interface as ``ParkourAgent`` but uses an
    attention encoder ONNX model that consumes the full policy observation.
    """

    def _load_models(self):
        """Load ONNX models for attention-based parkour policy."""
        ort_execution_providers = ort.get_available_providers()

        attention_encoder_path = os.path.join(
            self.logdir, "exported", "0-map_attention.onnx"
        )
        if not os.path.exists(attention_encoder_path):
            legacy_attention_encoder_path = os.path.join(
                self.logdir, "exported", "map_attention_encoder.onnx"
            )
            if os.path.exists(legacy_attention_encoder_path):
                attention_encoder_path = legacy_attention_encoder_path
            else:
                raise FileNotFoundError(
                    "Attention encoder ONNX not found. Expected one of: "
                    f"{os.path.join(self.logdir, 'exported', '0-map_attention.onnx')} or "
                    f"{legacy_attention_encoder_path}"
                )

        self.ort_sessions["attention_encoder"] = ort.InferenceSession(
            attention_encoder_path,
            providers=ort_execution_providers,
        )

        actor_path = os.path.join(self.logdir, "exported", "actor.onnx")
        self.ort_sessions["actor"] = ort.InferenceSession(
            actor_path, providers=ort_execution_providers
        )
        print(f"Loaded attention ONNX models from {self.logdir}")

    def step(self):
        """Perform one attention policy inference step."""
        obs_terms = dict()
        for obs_name in self.obs_funcs.keys():
            obs_terms[obs_name] = self._get_single_obs_term(obs_name)

        depth_obs = (
            obs_terms[self.depth_obs_names[0]]
            .reshape(1, -1, self.depth_height, self.depth_width)
            .astype(np.float32)
        )

        if self.debug_depth_publisher is not None:
            depth_image_msg_data = np.asanyarray(
                depth_obs[0, -1].reshape(self.depth_height, self.depth_width) * 255 * 2,
                dtype=np.uint16,
            )
            depth_image_msg = rnp.msgify(Image, depth_image_msg_data, encoding="16UC1")
            depth_image_msg.header.stamp = self.ros_node.get_clock().now().to_msg()
            depth_image_msg.header.frame_id = "realsense_depth_link"
            self.debug_depth_publisher.publish(depth_image_msg)

        if self.debug_pointcloud_publisher is not None:
            pointcloud_msg = self.ros_node.depth_image_to_pointcloud_msg(
                depth_obs[0, -1].reshape(self.depth_height, self.depth_width)
                * self.depth_range[1]
                + self.depth_range[0]
            )
            self.debug_pointcloud_publisher.publish(pointcloud_msg)

        policy_obs = np.concatenate(
            [
                obs_terms[obs_name].reshape(-1).astype(np.float32)
                for obs_name in self.obs_funcs.keys()
            ],
            axis=-1,
        ).reshape(1, -1)

        encoder_input_name = self.ort_sessions["attention_encoder"].get_inputs()[0].name
        encoder_output = self.ort_sessions["attention_encoder"].run(
            None, {encoder_input_name: policy_obs}
        )[0]

        actor_input_name = self.ort_sessions["actor"].get_inputs()[0].name
        action = self.ort_sessions["actor"].run(
            None, {actor_input_name: encoder_output}
        )[0]
        action = action.reshape(-1)

        mask = (self._zero_action_joints == 0).astype(bool)
        full_action = np.zeros(self.ros_node.NUM_ACTIONS, dtype=np.float32)
        full_action[mask] = action

        return full_action, False
