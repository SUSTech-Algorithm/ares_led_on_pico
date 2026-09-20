#ifndef ARES_LED_PROTOCOL_H
#define ARES_LED_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

#define ARES_PROTOCOL_VERSION 1u
#define ARES_MAX_LED_COUNT 1000u
#define ARES_MAX_PAYLOAD_SIZE (ARES_MAX_LED_COUNT * 3u)
#define ARES_HEADER_SIZE 6u
#define ARES_CRC_SIZE 2u
#define ARES_MAX_RAW_PACKET_SIZE \
    (ARES_HEADER_SIZE + ARES_MAX_PAYLOAD_SIZE + ARES_CRC_SIZE)
#define ARES_MAX_ENCODED_PACKET_SIZE \
    (ARES_MAX_RAW_PACKET_SIZE + (ARES_MAX_RAW_PACKET_SIZE / 254u) + 2u)

typedef enum {
    ARES_MSG_PING = 0x01,
    ARES_MSG_CONFIG_LED_COUNT = 0x10,
    ARES_MSG_SET_FRAME = 0x11,
    ARES_MSG_GET_STATUS = 0x20,
    ARES_MSG_ACK = 0x80,
    ARES_MSG_STATUS = 0x81,
    ARES_MSG_NACK = 0x82,
} ares_message_type_t;

typedef enum {
    ARES_RESULT_OK = 0,
    ARES_RESULT_REPLACED_PENDING_FRAME = 1,
    ARES_RESULT_BAD_VERSION = 2,
    ARES_RESULT_BAD_LENGTH = 3,
    ARES_RESULT_BAD_LED_COUNT = 4,
    ARES_RESULT_NOT_CONFIGURED = 5,
    ARES_RESULT_UNKNOWN_COMMAND = 6,
} ares_result_t;

typedef enum {
    ARES_DECODE_OK = 0,
    ARES_DECODE_COBS_ERROR,
    ARES_DECODE_LENGTH_ERROR,
    ARES_DECODE_CRC_ERROR,
    ARES_DECODE_VERSION_ERROR,
} ares_decode_result_t;

typedef struct {
    uint8_t version;
    uint8_t message_type;
    uint16_t sequence;
    uint16_t payload_length;
    const uint8_t *payload;
} ares_packet_t;

uint16_t ares_crc16_ccitt(const uint8_t *data, size_t length);

size_t ares_cobs_encode(
    const uint8_t *input,
    size_t input_length,
    uint8_t *output,
    size_t output_capacity);

size_t ares_cobs_decode(
    const uint8_t *input,
    size_t input_length,
    uint8_t *output,
    size_t output_capacity);

size_t ares_packet_encode(
    uint8_t message_type,
    uint16_t sequence,
    const uint8_t *payload,
    uint16_t payload_length,
    uint8_t *raw_buffer,
    size_t raw_capacity,
    uint8_t *encoded_buffer,
    size_t encoded_capacity);

ares_decode_result_t ares_packet_decode(
    const uint8_t *encoded,
    size_t encoded_length,
    uint8_t *raw_buffer,
    size_t raw_capacity,
    ares_packet_t *packet);

#endif
