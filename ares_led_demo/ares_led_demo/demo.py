"""Cycle through single-pixel, segment, and animation commands."""

from __future__ import annotations

import colorsys

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray


class AresLedDemo(Node):
    def __init__(self) -> None:
        super().__init__('ares_led_demo')
        self.declare_parameter('led_count', 30)
        self.declare_parameter('step_seconds', 3.0)
        self._count = int(self.get_parameter('led_count').value)
        step_seconds = float(self.get_parameter('step_seconds').value)
        if not 1 <= self._count <= 1000:
            raise ValueError('led_count must be in 1..1000')
        if step_seconds <= 0.0:
            raise ValueError('step_seconds must be greater than zero')

        self._single = self.create_publisher(
            Int32MultiArray, '/ares/led/single', 10
        )
        self._segment = self.create_publisher(
            Int32MultiArray, '/ares/led/segment', 10
        )
        self._animation = self.create_publisher(
            Int32MultiArray, '/ares/led/animation', 10
        )
        self._step = 0
        self.create_timer(step_seconds, self._advance)

    @staticmethod
    def _message(data) -> Int32MultiArray:
        message = Int32MultiArray()
        message.data = list(data)
        return message

    def _advance(self) -> None:
        if self._step == 0:
            colors = []
            for index in range(self._count):
                rgb = colorsys.hsv_to_rgb(index / self._count, 1.0, 1.0)
                colors.extend(round(channel * 255) for channel in rgb)
            self._single.publish(
                self._message([self._count, 0, self._count - 1, *colors])
            )
            description = 'single: per-pixel rainbow'
        elif self._step == 1:
            left = self._count // 4
            right = max(left, self._count * 3 // 4 - 1)
            self._segment.publish(
                self._message([self._count, left, right, 0, 255, 80])
            )
            description = 'segment: green center range'
        elif 2 <= self._step <= 11:
            effect = self._step - 1
            self._animation.publish(
                self._message([self._count, 0, self._count - 1, effect])
            )
            description = f'animation: effect {effect}'
        else:
            self._animation.publish(
                self._message([self._count, 0, self._count - 1, 0])
            )
            description = 'animation: stop and hold'

        self.get_logger().info(description)
        self._step = (self._step + 1) % 13


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AresLedDemo()
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
