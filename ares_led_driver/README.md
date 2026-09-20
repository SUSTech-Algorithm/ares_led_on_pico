# ares_led_driver

RP2040-Zero 自启动 WS2812B 驱动固件。GPIO2 输出 800 kHz WS2812B 数据，USB-C 作为
USB CDC 上下位机通信接口。上位机逻辑颜色顺序为 RGB，固件输出时转换为 WS2812B 的
GRB 顺序。

## 行为

- 支持 1--1000 颗灯珠，运行时可以重新配置。
- Core 0 解析 USB 协议，Core 1 使用 PIO 输出灯带，避免输出1000颗灯时阻塞收包。
- 使用双缓冲；如果新帧到达时已有待显示帧，新帧覆盖旧帧并增加 dropped 计数。
- 灯珠数量缩小时，下一颜色帧会按旧长度补零，清除灯带尾部残留颜色。
- USB 断开后不改变灯带，保持最后一次成功显示的颜色。
- 固件不做亮度或电流限制。

## 编译

安装 ARM 工具链并准备 Pico SDK：

```bash
sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential
git clone --recurse-submodules https://github.com/raspberrypi/pico-sdk.git ~/pico-sdk
export PICO_SDK_PATH=~/pico-sdk
```

编译：

```bash
cd /path/to/ares_led_on_pico/ares_led_driver
cmake -S . -B build -DPICO_BOARD=pico
cmake --build build -j
```

生成文件为 `build/ares_led_driver.uf2`。按住 RP2040-Zero 的 BOOT，同时按下 RESET；
先松开 RESET，再松开 BOOT。出现 `RPI-RP2` 磁盘后复制 UF2，开发板会自动重启并运行。

仓库中的预编译文件可直接烧录：

```text
release/ares_led_driver.uf2
```

## 接线

```text
RP2040-Zero GPIO2 -> 300--500R -> WS2812B DIN
RP2040-Zero GND   -------------> WS2812B GND
外置5V电源 +5V   -------------> WS2812B +5V
外置5V电源 GND   -------------> 公共GND
```

GPIO2 以 3.3 V 逻辑直接驱动灯带，请缩短到第一颗灯珠的数据线。灯带供电入口并联
500--1000 uF 电解电容。1000颗灯全白的最坏电流可能接近60 A；本固件不会限制亮度，
必须由供电系统、保险丝、线径和多点注电保证安全。

## 仅测试协议C代码

这项测试不需要 Pico SDK：

```bash
cmake -S tests -B tests/build
cmake --build tests/build
ctest --test-dir tests/build --output-on-failure
```
