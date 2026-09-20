"""ROS 2 command node for the ARES RP2040 LED controller."""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32MultiArray

from .client import AresPicoClient
from .controller import CommandError, LedController


class AresPicoProtocolNode(Node):
    def __init__(self) -> None:
        super().__init__('ares_pico_protocol')
        self.declare_parameter('port', 'auto')
        self.declare_parameter('serial_timeout', 0.5)
        self.declare_parameter('animation_fps', 30.0)
        self.declare_parameter('reconnect_interval', 1.0)

        port = self.get_parameter('port').value
        timeout = float(self.get_parameter('serial_timeout').value)
        animation_fps = float(self.get_parameter('animation_fps').value)
        if animation_fps <= 0.0:
            raise ValueError('animation_fps must be greater than zero')

        self._reconnect_interval = float(
            self.get_parameter('reconnect_interval').value
        )
        if self._reconnect_interval <= 0.0:
            raise ValueError('reconnect_interval must be greater than zero')
        self._next_connect_time = 0.0
        self._last_error = ''
        self._pending_frame: bytes | None = None
        self._controller = LedController()
        self._client = AresPicoClient(port, timeout=timeout)

        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.create_subscription(
            Int32MultiArray,
            '/ares/led/single',
            self._on_single,
            qos,
        )
        self.create_subscription(
            Int32MultiArray,
            '/ares/led/segment',
            self._on_segment,
            qos,
        )
        self.create_subscription(
            Int32MultiArray,
            '/ares/led/animation',
            self._on_animation,
            qos,
        )
        self.create_timer(1.0 / animation_fps, self._on_animation_tick)
        self.create_timer(self._reconnect_interval, self._retry_pending_frame)
        self.get_logger().info(
            'Ready: /ares/led/single, /ares/led/segment, /ares/led/animation'
        )

    def _on_single(self, message: Int32MultiArray) -> None:
        try:
            frame = self._controller.apply_single(message.data)
        except CommandError as exc:
            self.get_logger().error(f'Rejected /ares/led/single: {exc}')
            return
        self._send(frame)

    def _on_segment(self, message: Int32MultiArray) -> None:
        try:
            frame = self._controller.apply_segment(message.data)
        except CommandError as exc:
            self.get_logger().error(f'Rejected /ares/led/segment: {exc}')
            return
        self._send(frame)

    def _on_animation(self, message: Int32MultiArray) -> None:
        try:
            frame = self._controller.start_animation(message.data)
        except CommandError as exc:
            self.get_logger().error(f'Rejected /ares/led/animation: {exc}')
            return
        # Effect zero stops and holds. Other effects emit their first frame on
        # the next animation tick.
        if self._controller.animation is None:
            self._send(frame)

    def _on_animation_tick(self) -> None:
        frame = self._controller.tick()
        if frame is not None:
            self._send(frame)

    def _send(self, frame: bytes) -> None:
        self._pending_frame = frame
        now = time.monotonic()
        if now < self._next_connect_time:
            return
        try:
            self._client.configure_and_send(frame)
            self._pending_frame = None
            if self._last_error:
                self.get_logger().info('RP2040 communication recovered')
                self._last_error = ''
        except Exception as exc:  # Serial errors are intentionally reconnectable.
            error = f'{type(exc).__name__}: {exc}'
            if error != self._last_error:
                self.get_logger().error(f'RP2040 communication failed: {error}')
                self._last_error = error
            self._client.close()
            self._next_connect_time = now + self._reconnect_interval

    def _retry_pending_frame(self) -> None:
        if self._pending_frame is not None:
            self._send(self._pending_frame)

    def destroy_node(self):
        self._client.close()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AresPicoProtocolNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
