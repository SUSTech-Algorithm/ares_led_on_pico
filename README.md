# ARES LED on Pico

基于 Waveshare RP2040-Zero、WS2812B 与 ROS 2 Jazzy 的灯带控制系统。RP2040
作为下位机自启动运行，负责 USB 通信和严格时序的灯带输出；Linux 上位机维护整条灯带的
RGB 状态、生成动画，并通过 ROS 2 topic 接收其他功能包的控制命令。

## 系统组成

```text
其他 ROS 2 包
   |  /ares/led/{single,segment,animation}
   v
ares_pico_protocol（完整帧缓存、动画、校验、重连）
   |  USB CDC：COBS + CRC16 二进制协议
   v
ares_led_driver（RP2040 双核 + PIO）
   |  GPIO2，800 kHz WS2812 波形
   v
300~500 Ω 串联电阻 -> WS2812B 灯带
```

仓库包含三个同级组件：

| 目录 | 用途 |
|---|---|
| `ares_led_driver` | RP2040-Zero 固件及纯 C 协议测试 |
| `ares_pico_protocol` | 串口协议客户端、调试 CLI 和 ROS 2 控制节点 |
| `ares_led_demo` | 简洁的三类 topic 与十种动画演示 |

## 快速上手

### 1. 接线与供电

本项目使用 RP2040-Zero 的 3.3 V GPIO 直接驱动灯带数据输入：

```text
RP2040-Zero GPIO2 -> 300~500 Ω 电阻 -> 第一颗 WS2812B DIN

外置稳压 5 V +  -> 灯带 +5V
外置稳压 5 V -  -> 灯带 GND、RP2040-Zero GND
```

在灯带电源入口并联 `500~1000 µF` 电解电容。必须共地，数据线要接灯带标记的
`DIN`，不能接 `DOUT`。建议缩短 GPIO2 到第一颗灯珠的数据线，以提高直接驱动的稳定性。

> 不要用 RP2040 的 3V3 引脚或电脑 USB 口给大功率灯带供电。本项目不限制亮度。
> WS2812B 全白可按最坏约 60 mA/颗估算：60、300、1000 颗分别约为 3.6 A、
> 18 A、60 A。长灯带应使用合适的电源、保险丝、线径和多点注电。

### 2. 烧录固件

可以直接烧录仓库中的 `ares_led_driver/release/ares_led_driver.uf2`：

1. 按住 RP2040-Zero 的 `BOOT`，按下并松开 `RESET`，再松开 `BOOT`。
2. Linux 出现名为 `RPI-RP2` 的 U 盘后，将 UF2 文件复制进去。
3. 开发板自动重启，随后应出现 `/dev/ttyACM*` 或 `/dev/serial/by-id/*`。

### 3. 安装上位机依赖

下列命令以 Ubuntu 24.04 和已安装的 ROS 2 Jazzy 为前提：

```bash
sudo apt update
sudo apt install python3-serial python3-pytest python3-rosdep

cd /path/to/ares_led_on_pico
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths . --ignore-src -r -y
```

若当前用户没有串口权限：

```bash
sudo usermod -aG dialout "$USER"
```

执行后注销并重新登录。关闭 Thonny、minicom 等可能占用同一串口的程序。

### 4. 构建 ROS 2 包

```bash
cd /path/to/ares_led_on_pico
source /opt/ros/jazzy/setup.bash
colcon build --packages-select ares_pico_protocol ares_led_demo --symlink-install
source install/setup.bash
```

每次打开新终端都需要再次执行 ROS 和工作区的两个 `source` 命令。

### 5. 检查上下位机通信

```bash
ros2 run ares_pico_protocol ares_pico_cli ping
ros2 run ares_pico_protocol ares_pico_cli status
ros2 run ares_pico_protocol ares_pico_cli solid 30 32 0 0
```

默认 `--port auto` 会优先查找 `/dev/serial/by-id` 中包含 ARES、RP2040 或 Pico 的
设备；否则在只有一个 `/dev/ttyACM*` 时选用它。多设备时请显式指定：

```bash
ros2 run ares_pico_protocol ares_pico_cli \
  --port /dev/serial/by-id/usb-ARES_ares_led_driver_0001-if00 status
```

### 6. 启动 ROS 2 控制节点

```bash
ros2 run ares_pico_protocol ares_pico_protocol_node
```

另开终端发布命令，例如令 60 颗灯中的第 10~29 颗变绿：

```bash
source /opt/ros/jazzy/setup.bash
source /path/to/ares_led_on_pico/install/setup.bash
ros2 topic pub --once /ares/led/segment std_msgs/msg/Int32MultiArray \
  '{data: [60, 10, 29, 0, 255, 0]}'
```

或者直接运行完整演示（同时启动协议节点）：

```bash
ros2 launch ares_led_demo demo.launch.py
```

## WS2812B 与刷新原理

WS2812B 将颜色控制器集成在每颗灯珠中，灯珠串联连接。控制器只向第一颗灯的 DIN 发送
串行数据；每颗灯取走属于自己的 24 bit，再把剩余数据传给下一颗。WS2812B 线上顺序为
GRB，本项目对 ROS 和通信层统一暴露 RGB，固件输出时再转换为 GRB。

RP2040 使用 PIO 生成 800 kHz 的严格时序。Core 0 处理 USB CDC 数据包，Core 1 负责
提交 PIO 帧，避免长灯带输出阻塞收包。固件使用双缓冲：若上一待显示帧尚未输出，新帧会
替换它并增加 `dropped_frames`，从而优先保证低延迟和最新状态。

下位机不接收固定刷新频率，而是收到完整帧后尽快输出。理论帧时间约为：

```text
frame_time ≈ LED数量 × 30 µs + 300 µs reset
max_fps ≈ 1 / frame_time
```

据此，60、300、1000 颗灯的理论上限约为 476、108、33 FPS，实际速度还受 USB、
上位机调度和动画发布频率影响。USB 断开时灯带保持最后一次成功显示的颜色。

## ROS 2 接口

三个 topic 均使用 `std_msgs/msg/Int32MultiArray`，QoS 为 Reliable、Volatile、深度 10。
灯珠索引从 0 开始，`left` 和 `right` 都包含在控制范围内。灯珠总数必须为 1~1000，
RGB 通道必须为 0~255。非法长度、范围、颜色或灯效参数会整条拒绝，不会部分生效。

### `/ares/led/single`

逐颗设置一个闭区间：

```text
[总数, left, right, R_left, G_left, B_left, ..., R_right, G_right, B_right]
```

数组长度必须是 `3 + 3 × (right-left+1)`。例如，将 4 颗灯中的索引 1 设为红色、
索引 2 设为蓝色：

```bash
ros2 topic pub --once /ares/led/single std_msgs/msg/Int32MultiArray \
  '{data: [4, 1, 2, 255, 0, 0, 0, 0, 255]}'
```

### `/ares/led/segment`

用同一种颜色设置闭区间：

```text
[总数, left, right, R, G, B]
```

仅修改区间内颜色，其他灯保持原样：

```bash
ros2 topic pub --once /ares/led/segment std_msgs/msg/Int32MultiArray \
  '{data: [60, 10, 29, 0, 255, 0]}'
```

### `/ares/led/animation`

```text
[总数, left, right, effect_id, 可选参数...]
```

动画由上位机按 `animation_fps` 生成完整 RGB 帧，仅修改指定区间。新动画会替换旧动画；
收到 `single` 或 `segment` 命令会终止当前动画。可选参数必须全部提供，或全部省略并采用
默认值。

| ID | 效果 | 参数 | 默认值 |
|---:|---|---|---|
| 0 | 停止并保持当前帧 | 无 | — |
| 1 | 正向追逐 | `R,G,B,width` | `255,0,0,1` |
| 2 | 反向追逐 | `R,G,B,width` | `0,0,255,1` |
| 3 | 彩虹循环 | `speed`，1~255 | `3` |
| 4 | 剧院灯追逐 | `R,G,B,gap` | `255,160,0,3` |
| 5 | 呼吸灯 | `R,G,B,period_frames`，周期至少 2 帧 | `255,255,255,60` |
| 6 | 往返扫描 | `R,G,B,width` | `0,255,255,3` |
| 7 | 随机闪烁 | `R,G,B,density_percent`，1~100 | `255,255,255,15` |
| 8 | 颜色擦除 | `R,G,B,direction`，方向为 `1` 或 `-1` | `0,255,0,1` |
| 9 | 双色跑马 | `R1,G1,B1,R2,G2,B2,block_width` | `255,0,0,0,0,255,3` |
| 10 | 彗星拖尾 | `R,G,B,tail_length,direction` | `255,0,255,8,1` |

示例：默认彩虹与自定义青色彗星：

```bash
ros2 topic pub --once /ares/led/animation std_msgs/msg/Int32MultiArray \
  '{data: [60, 0, 59, 3]}'

ros2 topic pub --once /ares/led/animation std_msgs/msg/Int32MultiArray \
  '{data: [60, 0, 59, 10, 0, 255, 255, 12, 1]}'
```

灯珠数量在运行中变化时，上位机保留新旧范围重叠部分，新增加的灯初始化为黑色；缩短灯带
时，固件在下一帧按旧长度补零，避免物理灯带尾部残留颜色。

### 节点参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---:|---|
| `port` | string | `auto` | 串口路径或自动发现 |
| `serial_timeout` | double | `0.5` | 串口收发超时，秒 |
| `animation_fps` | double | `30.0` | 上位机动画生成频率，必须大于 0 |
| `reconnect_interval` | double | `1.0` | 通信失败后的重连间隔，秒，必须大于 0 |

指定参数示例：

```bash
ros2 run ares_pico_protocol ares_pico_protocol_node --ros-args \
  -p port:=/dev/ttyACM0 -p animation_fps:=20.0
```

通信中断时节点保留最新待发送帧，并按 `reconnect_interval` 自动重连。

## USB 串行协议 v1

USB CDC 的波特率设置仅用于兼容串口 API，不决定 USB 实际传输速度。每包格式为：

```text
COBS(version | type | sequence_le | payload_length_le | payload | crc16_le) | 0x00
```

固定字段宽度依次为 1、1、2、2、N、2 字节。CRC 使用 CRC-16/CCITT-FALSE，初值
`0xffff`、多项式 `0x1021`，覆盖 header 和 payload。COBS 使编码后包体中没有零字节，
因此 `0x00` 可可靠地作为数据包边界。

| 消息 | 类型 | Payload |
|---|---:|---|
| `PING` | `0x01` | 空 |
| `CONFIG_LED_COUNT` | `0x10` | `uint16_le led_count` |
| `SET_FRAME` | `0x11` | `R0,G0,B0,...`，长度必须为 `led_count × 3` |
| `GET_STATUS` | `0x20` | 空 |
| `ACK` | `0x80` | 原命令类型、结果码 |
| `STATUS` | `0x81` | 下表中的状态结构 |
| `NACK` | `0x82` | 原命令类型、错误码 |

响应沿用请求的 16 bit sequence。`SET_FRAME` 的 ACK 表示帧已复制进下位机缓冲区，
不代表灯带已经完成输出。结果码如下：

| 值 | 名称 | 含义 |
|---:|---|---|
| 0 | `OK` | 成功 |
| 1 | `REPLACED_PENDING_FRAME` | 新帧覆盖了尚未显示的旧帧 |
| 2 | `BAD_VERSION` | 协议版本不支持 |
| 3 | `BAD_LENGTH` | Payload 长度错误 |
| 4 | `BAD_LED_COUNT` | 灯珠数量越界 |
| 5 | `NOT_CONFIGURED` | 尚未配置灯珠数量 |
| 6 | `UNKNOWN_COMMAND` | 未知消息类型 |

`STATUS` payload 全部为小端：

```text
uint16 led_count
uint16 max_led_count
uint16 actual_fps_x10
uint32 received_frames
uint32 displayed_frames
uint32 dropped_frames
uint32 crc_errors
uint8  busy
```

## Demo 参数

`ares_led_demo` 默认使用 30 颗灯，每 3 秒依次展示逐灯彩虹、局部纯色、10 种动画和
停止保持，然后循环。单独运行时可以覆盖参数：

```bash
ros2 run ares_led_demo demo --ros-args \
  -p led_count:=60 -p step_seconds:=2.0
```

| 参数 | 默认值 | 范围 |
|---|---:|---|
| `led_count` | `30` | 1~1000 |
| `step_seconds` | `3.0` | 大于 0 秒 |

## 从源码构建下位机固件

准备 ARM 工具链和 Raspberry Pi Pico SDK：

```bash
sudo apt install cmake ninja-build gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential
git clone --recurse-submodules https://github.com/raspberrypi/pico-sdk.git /path/to/pico-sdk
export PICO_SDK_PATH=/path/to/pico-sdk

cd /path/to/ares_led_on_pico/ares_led_driver
cmake -S . -B build -G Ninja -DPICO_BOARD=pico
cmake --build build -j
```

输出文件为 `build/ares_led_driver.uf2`。固件目标使用通用 `pico` 板级定义，适用于
RP2040-Zero 的 RP2040 核心与本项目采用的 GPIO2 接线。

## 测试

ROS 2 构建与测试：

```bash
cd /path/to/ares_led_on_pico
source /opt/ros/jazzy/setup.bash
colcon build --packages-select ares_pico_protocol ares_led_demo --symlink-install
colcon test --packages-select ares_pico_protocol ares_led_demo
colcon test-result --verbose
```

只测试与平台无关的下位机 C 协议实现：

```bash
cmake -S ares_led_driver/tests -B ares_led_driver/tests/build
cmake --build ares_led_driver/tests/build
ctest --test-dir ares_led_driver/tests/build --output-on-failure
```

## 常见问题

- `module 'serial' has no attribute 'Serial'`：安装的是错误的 `serial` 包或被同名文件遮蔽。
  卸载 `serial`，安装 `pyserial`/`python3-serial`，并确认项目中没有 `serial.py`。
- `Permission denied: /dev/ttyACM0`：将用户加入 `dialout` 组并重新登录。
- 串口存在但无法打开：关闭 Thonny、串口监视器等占用设备的程序。
- 灯色顺序错误：上位机必须发送 RGB；固件会自行转换为 WS2812B 的 GRB，不要预先交换。
- 灯随机闪烁或末端变色：优先检查共地、5 V 压降、注电点、数据线长度和串联电阻。
- `dropped_frames` 增长：上位机送帧快于灯带物理刷新能力。降低 `animation_fps`，或减少灯珠数。

更底层的信息见 `ares_led_driver/PROTOCOL.md`，各组件也保留了各自的 README。
