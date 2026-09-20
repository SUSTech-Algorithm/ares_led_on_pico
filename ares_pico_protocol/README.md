# ares_pico_protocol

Linux 上位机与 RP2040-Zero `ares_led_driver` 固件之间的 USB CDC 通信包。包含底层
协议客户端、硬件测试 CLI 和 ROS 2 Jazzy 控制节点。

## 协议

- USB CDC 二进制传输，串口波特率字段只为兼容主机 API，不决定 USB 实际速度。
- 每包使用 COBS 编码，以 `0x00` 结尾。
- 解码内容为版本、命令、16 bit 序号、16 bit payload 长度、payload、CRC16-CCITT。
- RGB 逻辑顺序为 `R,G,B`；Pico 固件输出 WS2812B 时转换成 `G,R,B`。
- 灯珠数量范围为 1--1000，运行期间可重新配置。
- 固件仅保留最新待显示帧；尚未显示的旧帧被覆盖时 ACK 返回
  `REPLACED_PENDING_FRAME`。
- USB 断开不会熄灯，WS2812B 保持最后一次显示结果。

## 构建与测试

```bash
cd /path/to/ares_led_on_pico
source /opt/ros/jazzy/setup.bash
colcon build --packages-select ares_pico_protocol
source install/setup.bash
python3 -m pytest ares_pico_protocol/test
```

## ROS 2节点

```bash
ros2 run ares_pico_protocol ares_pico_protocol_node
```

所有 topic 使用 `std_msgs/msg/Int32MultiArray`。索引从0开始，区间为左右闭区间。

### 逐灯颜色

```text
/ares/led/single
[总数, left, right, R_left, G_left, B_left, ..., R_right, G_right, B_right]
```

示例：4颗灯中的第1、2颗分别设为红色和蓝色：

```bash
ros2 topic pub --once /ares/led/single std_msgs/msg/Int32MultiArray \
  '{data: [4, 1, 2, 255, 0, 0, 0, 0, 255]}'
```

### 区间纯色

```text
/ares/led/segment
[总数, left, right, R, G, B]
```

只修改闭区间，区间外保持原颜色：

```bash
ros2 topic pub --once /ares/led/segment std_msgs/msg/Int32MultiArray \
  '{data: [60, 10, 29, 0, 255, 0]}'
```

### 动画

```text
/ares/led/animation
[总数, left, right, effect_id, 可选参数...]
```

动画仅修改指定区间。收到 `single` 或 `segment` 后当前动画停止；新动画替换旧动画。
所有效果均可省略参数并使用默认值。

| ID | 效果 | 可选参数 |
|---:|---|---|
| 0 | 停止并保持 | 无 |
| 1 | 正向追逐 | `R,G,B,width` |
| 2 | 反向追逐 | `R,G,B,width` |
| 3 | 彩虹循环 | `speed`，1--255 |
| 4 | 剧院灯追逐 | `R,G,B,gap` |
| 5 | 呼吸灯 | `R,G,B,period_frames` |
| 6 | 往返扫描 | `R,G,B,width` |
| 7 | 随机闪烁 | `R,G,B,density_percent` |
| 8 | 颜色擦除 | `R,G,B,direction`，方向为1或-1 |
| 9 | 双色跑马 | `R1,G1,B1,R2,G2,B2,block_width` |
| 10 | 彗星拖尾 | `R,G,B,tail_length,direction` |

例如默认彩虹和自定义青色彗星：

```bash
ros2 topic pub --once /ares/led/animation std_msgs/msg/Int32MultiArray \
  '{data: [60, 0, 59, 3]}'

ros2 topic pub --once /ares/led/animation std_msgs/msg/Int32MultiArray \
  '{data: [60, 0, 59, 10, 0, 255, 255, 12, 1]}'
```

灯珠总数变化时保留重叠部分，新增加灯珠初始化为黑色。非法长度、索引、颜色或参数会整条
拒绝，不会部分执行。

## 硬件测试

```bash
# 自动寻找单个 RP2040 CDC 设备
ros2 run ares_pico_protocol ares_pico_cli ping
ros2 run ares_pico_protocol ares_pico_cli status

# 令 60 颗灯显示红色
ros2 run ares_pico_protocol ares_pico_cli solid 60 255 0 0

# 多串口设备环境应指定稳定路径
ros2 run ares_pico_protocol ares_pico_cli \
  --port /dev/serial/by-id/usb-ARES_ares_led_driver_0001-if00 \
  status
```

Python API：

```python
from ares_pico_protocol import AresPicoClient

with AresPicoClient('auto') as pico:
    pico.configure_led_count(2)
    pico.send_frame([255, 0, 0, 0, 0, 255])
    print(pico.get_status())
```
