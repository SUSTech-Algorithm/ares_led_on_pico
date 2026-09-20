#include "protocol.h"


static uint16_t read_u16_le(const uint8_t *data) {
    return (uint16_t)data[0] | ((uint16_t)data[1] << 8u);
}


static void write_u16_le(uint8_t *data, uint16_t value) {
    data[0] = (uint8_t)(value & 0xffu);
    data[1] = (uint8_t)(value >> 8u);
}


uint16_t ares_crc16_ccitt(const uint8_t *data, size_t length) {
    uint16_t crc = 0xffffu;
    for (size_t index = 0; index < length; ++index) {
        crc ^= (uint16_t)data[index] << 8u;
        for (unsigned bit = 0; bit < 8u; ++bit) {
            crc = (crc & 0x8000u)
                ? (uint16_t)((crc << 1u) ^ 0x1021u)
                : (uint16_t)(crc << 1u);
        }
    }
    return crc;
}


size_t ares_cobs_encode(
    const uint8_t *input,
    size_t input_length,
    uint8_t *output,
    size_t output_capacity) {
    if (output_capacity == 0u) {
        return 0u;
    }

    size_t read_index = 0u;
    size_t write_index = 1u;
    size_t code_index = 0u;
    uint8_t code = 1u;

    while (read_index < input_length) {
        if (input[read_index] == 0u) {
            if (code_index >= output_capacity || write_index >= output_capacity) {
                return 0u;
            }
            output[code_index] = code;
            code_index = write_index++;
            code = 1u;
            ++read_index;
        } else {
            if (write_index >= output_capacity) {
                return 0u;
            }
            output[write_index++] = input[read_index++];
            ++code;
            if (code == 0xffu) {
                if (code_index >= output_capacity || write_index >= output_capacity) {
                    return 0u;
                }
                output[code_index] = code;
                code_index = write_index++;
                code = 1u;
            }
        }
    }

    if (code_index >= output_capacity) {
        return 0u;
    }
    output[code_index] = code;
    return write_index;
}


size_t ares_cobs_decode(
    const uint8_t *input,
    size_t input_length,
    uint8_t *output,
    size_t output_capacity) {
    if (input_length == 0u) {
        return 0u;
    }

    size_t read_index = 0u;
    size_t write_index = 0u;
    while (read_index < input_length) {
        uint8_t code = input[read_index++];
        if (code == 0u || read_index + (size_t)code - 1u > input_length) {
            return 0u;
        }
        for (uint8_t offset = 1u; offset < code; ++offset) {
            if (write_index >= output_capacity) {
                return 0u;
            }
            output[write_index++] = input[read_index++];
        }
        if (code != 0xffu && read_index < input_length) {
            if (write_index >= output_capacity) {
                return 0u;
            }
            output[write_index++] = 0u;
        }
    }
    return write_index;
}


size_t ares_packet_encode(
    uint8_t message_type,
    uint16_t sequence,
    const uint8_t *payload,
    uint16_t payload_length,
    uint8_t *raw_buffer,
    size_t raw_capacity,
    uint8_t *encoded_buffer,
    size_t encoded_capacity) {
    size_t raw_length = ARES_HEADER_SIZE + payload_length + ARES_CRC_SIZE;
    if (payload_length > ARES_MAX_PAYLOAD_SIZE || raw_length > raw_capacity) {
        return 0u;
    }

    raw_buffer[0] = ARES_PROTOCOL_VERSION;
    raw_buffer[1] = message_type;
    write_u16_le(&raw_buffer[2], sequence);
    write_u16_le(&raw_buffer[4], payload_length);
    for (uint16_t index = 0u; index < payload_length; ++index) {
        raw_buffer[ARES_HEADER_SIZE + index] = payload[index];
    }
    uint16_t crc = ares_crc16_ccitt(raw_buffer, raw_length - ARES_CRC_SIZE);
    write_u16_le(&raw_buffer[raw_length - ARES_CRC_SIZE], crc);

    if (encoded_capacity < 2u) {
        return 0u;
    }
    size_t encoded_length = ares_cobs_encode(
        raw_buffer,
        raw_length,
        encoded_buffer,
        encoded_capacity - 1u);
    if (encoded_length == 0u || encoded_length >= encoded_capacity) {
        return 0u;
    }
    encoded_buffer[encoded_length++] = 0u;
    return encoded_length;
}


ares_decode_result_t ares_packet_decode(
    const uint8_t *encoded,
    size_t encoded_length,
    uint8_t *raw_buffer,
    size_t raw_capacity,
    ares_packet_t *packet) {
    size_t raw_length = ares_cobs_decode(
        encoded,
        encoded_length,
        raw_buffer,
        raw_capacity);
    if (raw_length == 0u) {
        return ARES_DECODE_COBS_ERROR;
    }
    if (raw_length < ARES_HEADER_SIZE + ARES_CRC_SIZE) {
        return ARES_DECODE_LENGTH_ERROR;
    }

    uint16_t payload_length = read_u16_le(&raw_buffer[4]);
    if (payload_length > ARES_MAX_PAYLOAD_SIZE ||
        raw_length != ARES_HEADER_SIZE + payload_length + ARES_CRC_SIZE) {
        return ARES_DECODE_LENGTH_ERROR;
    }

    uint16_t expected_crc = read_u16_le(&raw_buffer[raw_length - ARES_CRC_SIZE]);
    uint16_t actual_crc = ares_crc16_ccitt(
        raw_buffer,
        raw_length - ARES_CRC_SIZE);
    if (expected_crc != actual_crc) {
        return ARES_DECODE_CRC_ERROR;
    }
    if (raw_buffer[0] != ARES_PROTOCOL_VERSION) {
        return ARES_DECODE_VERSION_ERROR;
    }

    packet->version = raw_buffer[0];
    packet->message_type = raw_buffer[1];
    packet->sequence = read_u16_le(&raw_buffer[2]);
    packet->payload_length = payload_length;
    packet->payload = &raw_buffer[ARES_HEADER_SIZE];
    return ARES_DECODE_OK;
}
