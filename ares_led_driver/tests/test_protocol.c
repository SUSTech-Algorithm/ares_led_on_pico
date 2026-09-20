#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "protocol.h"


static void test_crc_known_vector(void) {
    static const uint8_t input[] = "123456789";
    assert(ares_crc16_ccitt(input, sizeof(input) - 1u) == 0x29b1u);
}


static void test_cobs_round_trip(void) {
    static const uint8_t input[] = {0u, 1u, 2u, 0u, 255u, 0u};
    uint8_t encoded[32];
    uint8_t decoded[32];
    size_t encoded_length = ares_cobs_encode(
        input, sizeof(input), encoded, sizeof(encoded));
    assert(encoded_length > 0u);
    for (size_t index = 0; index < encoded_length; ++index) {
        assert(encoded[index] != 0u);
    }
    size_t decoded_length = ares_cobs_decode(
        encoded, encoded_length, decoded, sizeof(decoded));
    assert(decoded_length == sizeof(input));
    assert(memcmp(decoded, input, sizeof(input)) == 0);
}


static void test_packet_round_trip(void) {
    static const uint8_t payload[] = {255u, 0u, 0u, 0u, 255u, 0u};
    uint8_t raw[ARES_MAX_RAW_PACKET_SIZE];
    uint8_t encoded[ARES_MAX_ENCODED_PACKET_SIZE];
    uint8_t decoded_raw[ARES_MAX_RAW_PACKET_SIZE];
    size_t encoded_length = ares_packet_encode(
        ARES_MSG_SET_FRAME,
        0x1234u,
        payload,
        sizeof(payload),
        raw,
        sizeof(raw),
        encoded,
        sizeof(encoded));
    assert(encoded_length > 1u);
    assert(encoded[encoded_length - 1u] == 0u);

    ares_packet_t packet;
    ares_decode_result_t result = ares_packet_decode(
        encoded,
        encoded_length - 1u,
        decoded_raw,
        sizeof(decoded_raw),
        &packet);
    assert(result == ARES_DECODE_OK);
    assert(packet.message_type == ARES_MSG_SET_FRAME);
    assert(packet.sequence == 0x1234u);
    assert(packet.payload_length == sizeof(payload));
    assert(memcmp(packet.payload, payload, sizeof(payload)) == 0);
}


static void test_crc_failure(void) {
    uint8_t raw[ARES_MAX_RAW_PACKET_SIZE];
    uint8_t encoded[ARES_MAX_ENCODED_PACKET_SIZE];
    uint8_t decoded_raw[ARES_MAX_RAW_PACKET_SIZE];
    size_t encoded_length = ares_packet_encode(
        ARES_MSG_PING,
        1u,
        NULL,
        0u,
        raw,
        sizeof(raw),
        encoded,
        sizeof(encoded));
    assert(encoded_length > 3u);
    encoded[2] ^= 0x40u;
    ares_packet_t packet;
    ares_decode_result_t result = ares_packet_decode(
        encoded,
        encoded_length - 1u,
        decoded_raw,
        sizeof(decoded_raw),
        &packet);
    assert(result == ARES_DECODE_CRC_ERROR);
}


int main(void) {
    test_crc_known_vector();
    test_cobs_round_trip();
    test_packet_round_trip();
    test_crc_failure();
    puts("ares_led protocol tests passed");
    return 0;
}
