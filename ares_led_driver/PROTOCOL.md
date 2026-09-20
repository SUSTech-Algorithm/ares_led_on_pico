# ARES Pico LED wire protocol v1

每个 USB CDC 数据包为：

```text
COBS(version | type | sequence_le | payload_length_le | payload | crc16_le) | 00
```

字段宽度依次为 1、1、2、2、N、2 字节。CRC 使用 CRC-16/CCITT-FALSE，初值
`0xffff`，多项式 `0x1021`，覆盖从 version 到 payload 的全部内容。

| 类型 | 值 | payload |
|---|---:|---|
| PING | `0x01` | 空 |
| CONFIG_LED_COUNT | `0x10` | `uint16_le led_count` |
| SET_FRAME | `0x11` | `R0,G0,B0,...`，必须为 `led_count * 3` 字节 |
| GET_STATUS | `0x20` | 空 |
| ACK | `0x80` | 原命令类型、结果码 |
| STATUS | `0x81` | 状态结构 |
| NACK | `0x82` | 原命令类型、错误码 |

ACK、NACK和STATUS沿用请求的 sequence。SET_FRAME 的 ACK 表示帧已复制进下位机缓冲区，
不是已经完成灯带输出。

STATUS payload 均为小端：

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
