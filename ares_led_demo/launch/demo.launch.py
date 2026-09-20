from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='ares_pico_protocol',
            executable='ares_pico_protocol_node',
            output='screen',
        ),
        Node(
            package='ares_led_demo',
            executable='demo',
            output='screen',
        ),
    ])
