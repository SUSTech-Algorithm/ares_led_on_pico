#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "hardware/clocks.h"
#include "hardware/pio.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "pico/sync.h"

#include "protocol.h"
#include "ws2812.pio.h"


#define WS2812_PIN 2u
#define WS2812_FREQUENCY 800000.0f
#define WS2812_RESET_US 300u
#define STATUS_PAYLOAD_SIZE 23u


typedef struct {
    uint16_t led_count;
    uint16_t clear_through;
    uint32_t config_epoch;

    uint8_t active_buffer;
    uint8_t pending_buffer;
    uint16_t pending_output_count;
    uint32_t pending_epoch;
    bool pending_ready;
    bool rendering;

    uint32_t received_frames;
    uint32_t displayed_frames;
    uint32_t dropped_frames;
    uint32_t crc_errors;
    uint16_t actual_fps_x10;
} driver_state_t;


static driver_state_t state;
static mutex_t state_mutex;
static uint8_t frame_buffers[2][ARES_MAX_PAYLOAD_SIZE];


static uint16_t read_u16_le(const uint8_t *data) {
    return (uint16_t)data[0] | ((uint16_t)data[1] << 8u);
}


static void write_u16_le(uint8_t *data, uint16_t value) {
    data[0] = (uint8_t)(value & 0xffu);
    data[1] = (uint8_t)(value >> 8u);
}


static void write_u32_le(uint8_t *data, uint32_t value) {
    data[0] = (uint8_t)(value & 0xffu);
    data[1] = (uint8_t)((value >> 8u) & 0xffu);
    data[2] = (uint8_t)((value >> 16u) & 0xffu);
    data[3] = (uint8_t)(value >> 24u);
}


static void usb_write_packet(
    uint8_t message_type,
    uint16_t sequence,
    const uint8_t *payload,
    uint16_t payload_length) {
    static uint8_t raw[ARES_MAX_RAW_PACKET_SIZE];
    static uint8_t encoded[ARES_MAX_ENCODED_PACKET_SIZE];
    size_t length = ares_packet_encode(
        message_type,
        sequence,
        payload,
        payload_length,
        raw,
        sizeof(raw),
        encoded,
        sizeof(encoded));
    stdio_put_string((const char *)encoded, (int)length, false, false);
    stdio_flush();
}


static void send_ack(
    const ares_packet_t *request,
    ares_result_t result,
    bool accepted) {
    uint8_t payload[2] = {request->message_type, (uint8_t)result};
    usb_write_packet(
        accepted ? ARES_MSG_ACK : ARES_MSG_NACK,
        request->sequence,
        payload,
        sizeof(payload));
}


static void send_status(uint16_t sequence) {
    uint8_t payload[STATUS_PAYLOAD_SIZE];
    mutex_enter_blocking(&state_mutex);
    write_u16_le(&payload[0], state.led_count);
    write_u16_le(&payload[2], ARES_MAX_LED_COUNT);
    write_u16_le(&payload[4], state.actual_fps_x10);
    write_u32_le(&payload[6], state.received_frames);
    write_u32_le(&payload[10], state.displayed_frames);
    write_u32_le(&payload[14], state.dropped_frames);
    write_u32_le(&payload[18], state.crc_errors);
    payload[22] = (uint8_t)(state.rendering || state.pending_ready);
    mutex_exit(&state_mutex);
    usb_write_packet(ARES_MSG_STATUS, sequence, payload, sizeof(payload));
}


static void handle_config(const ares_packet_t *packet) {
    if (packet->payload_length != 2u) {
        send_ack(packet, ARES_RESULT_BAD_LENGTH, false);
        return;
    }
    uint16_t requested_count = read_u16_le(packet->payload);
    if (requested_count == 0u || requested_count > ARES_MAX_LED_COUNT) {
        send_ack(packet, ARES_RESULT_BAD_LED_COUNT, false);
        return;
    }

    mutex_enter_blocking(&state_mutex);
    uint16_t old_extent = state.clear_through > state.led_count
        ? state.clear_through
        : state.led_count;
    if (state.pending_ready) {
        state.pending_ready = false;
        ++state.dropped_frames;
    }
    state.led_count = requested_count;
    state.clear_through = old_extent > requested_count
        ? old_extent
        : requested_count;
    ++state.config_epoch;
    mutex_exit(&state_mutex);
    send_ack(packet, ARES_RESULT_OK, true);
}


static void handle_frame(const ares_packet_t *packet) {
    mutex_enter_blocking(&state_mutex);
    uint16_t led_count = state.led_count;
    if (led_count == 0u) {
        mutex_exit(&state_mutex);
        send_ack(packet, ARES_RESULT_NOT_CONFIGURED, false);
        return;
    }
    if (packet->payload_length != led_count * 3u) {
        mutex_exit(&state_mutex);
        send_ack(packet, ARES_RESULT_BAD_LENGTH, false);
        return;
    }

    bool replaced = state.pending_ready;
    if (replaced) {
        ++state.dropped_frames;
    }
    uint8_t *destination = frame_buffers[state.pending_buffer];
    memcpy(destination, packet->payload, packet->payload_length);
    uint16_t output_count = state.clear_through;
    if (output_count < led_count) {
        output_count = led_count;
    }
    if (output_count > led_count) {
        memset(
            destination + packet->payload_length,
            0,
            (size_t)(output_count - led_count) * 3u);
    }
    state.pending_output_count = output_count;
    state.pending_epoch = state.config_epoch;
    state.pending_ready = true;
    ++state.received_frames;
    mutex_exit(&state_mutex);

    send_ack(
        packet,
        replaced ? ARES_RESULT_REPLACED_PENDING_FRAME : ARES_RESULT_OK,
        true);
}


static void handle_packet(const ares_packet_t *packet) {
    switch (packet->message_type) {
        case ARES_MSG_PING:
            if (packet->payload_length == 0u) {
                send_ack(packet, ARES_RESULT_OK, true);
            } else {
                send_ack(packet, ARES_RESULT_BAD_LENGTH, false);
            }
            break;
        case ARES_MSG_CONFIG_LED_COUNT:
            handle_config(packet);
            break;
        case ARES_MSG_SET_FRAME:
            handle_frame(packet);
            break;
        case ARES_MSG_GET_STATUS:
            if (packet->payload_length == 0u) {
                send_status(packet->sequence);
            } else {
                send_ack(packet, ARES_RESULT_BAD_LENGTH, false);
            }
            break;
        default:
            send_ack(packet, ARES_RESULT_UNKNOWN_COMMAND, false);
            break;
    }
}


static inline uint32_t pack_grb(const uint8_t *rgb) {
    return ((uint32_t)rgb[1] << 24u) |
           ((uint32_t)rgb[0] << 16u) |
           ((uint32_t)rgb[2] << 8u);
}


static void render_core(void) {
    PIO pio = pio0;
    uint offset = pio_add_program(pio, &ws2812_program);
    uint sm = pio_claim_unused_sm(pio, true);
    ws2812_program_init(pio, sm, offset, WS2812_PIN, WS2812_FREQUENCY);

    uint64_t fps_window_start = time_us_64();
    uint32_t fps_window_frames = 0u;

    while (true) {
        uint8_t buffer_index = 0u;
        uint16_t output_count = 0u;
        uint32_t frame_epoch = 0u;

        mutex_enter_blocking(&state_mutex);
        if (state.pending_ready) {
            buffer_index = state.pending_buffer;
            state.active_buffer = buffer_index;
            state.pending_buffer ^= 1u;
            output_count = state.pending_output_count;
            frame_epoch = state.pending_epoch;
            state.pending_ready = false;
            state.rendering = true;
        }
        mutex_exit(&state_mutex);

        if (output_count == 0u) {
            tight_loop_contents();
            continue;
        }

        const uint8_t *frame = frame_buffers[buffer_index];
        for (uint16_t index = 0u; index < output_count; ++index) {
            pio_sm_put_blocking(pio, sm, pack_grb(&frame[index * 3u]));
        }
        sleep_us(WS2812_RESET_US);

        ++fps_window_frames;
        uint64_t now = time_us_64();
        uint64_t elapsed = now - fps_window_start;

        mutex_enter_blocking(&state_mutex);
        ++state.displayed_frames;
        state.rendering = false;
        if (frame_epoch == state.config_epoch) {
            state.clear_through = state.led_count;
        }
        if (elapsed >= 1000000u) {
            uint64_t fps_x10 = ((uint64_t)fps_window_frames * 10000000u) / elapsed;
            state.actual_fps_x10 = fps_x10 > 0xffffu
                ? 0xffffu
                : (uint16_t)fps_x10;
            fps_window_frames = 0u;
            fps_window_start = now;
        }
        mutex_exit(&state_mutex);
    }
}


int main(void) {
    mutex_init(&state_mutex);
    state.active_buffer = 0u;
    state.pending_buffer = 1u;
    stdio_usb_init();
    multicore_launch_core1(render_core);

    static uint8_t encoded[ARES_MAX_ENCODED_PACKET_SIZE];
    static uint8_t raw[ARES_MAX_RAW_PACKET_SIZE];
    size_t encoded_length = 0u;
    bool discard_until_delimiter = false;

    while (true) {
        int value = getchar_timeout_us(0u);
        if (value == PICO_ERROR_TIMEOUT) {
            tight_loop_contents();
            continue;
        }
        uint8_t byte = (uint8_t)value;
        if (byte == 0u) {
            if (!discard_until_delimiter && encoded_length > 0u) {
                ares_packet_t packet;
                ares_decode_result_t result = ares_packet_decode(
                    encoded,
                    encoded_length,
                    raw,
                    sizeof(raw),
                    &packet);
                if (result == ARES_DECODE_OK) {
                    handle_packet(&packet);
                } else if (result == ARES_DECODE_CRC_ERROR) {
                    mutex_enter_blocking(&state_mutex);
                    ++state.crc_errors;
                    mutex_exit(&state_mutex);
                }
            }
            encoded_length = 0u;
            discard_until_delimiter = false;
        } else if (!discard_until_delimiter) {
            if (encoded_length < sizeof(encoded)) {
                encoded[encoded_length++] = byte;
            } else {
                encoded_length = 0u;
                discard_until_delimiter = true;
            }
        }
    }
}
