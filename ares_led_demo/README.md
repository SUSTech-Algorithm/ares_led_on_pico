# ares_led_demo

简洁演示 `ares_pico_protocol` 的三个输入 topic。默认使用30颗灯，每3秒切换一次：逐灯
彩虹、局部纯色、10种动画，最后停止并保持，然后循环。

```bash
cd /path/to/ares_led_on_pico
source /opt/ros/jazzy/setup.bash
colcon build --packages-select ares_pico_protocol ares_led_demo
source install/setup.bash
```

一条命令同时启动 protocol 与演示：

```bash
ros2 launch ares_led_demo demo.launch.py
```

也可以分别启动：

终端1：

```bash
ros2 run ares_pico_protocol ares_pico_protocol_node
```

终端2：

```bash
ros2 run ares_led_demo demo
```

改变灯珠数量与展示间隔：

```bash
ros2 run ares_led_demo demo --ros-args \
  -p led_count:=60 -p step_seconds:=2.0
```
