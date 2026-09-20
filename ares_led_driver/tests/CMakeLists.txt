cmake_minimum_required(VERSION 3.13)
project(ares_led_protocol_tests C)
set(CMAKE_C_STANDARD 11)

enable_testing()
add_executable(test_protocol test_protocol.c ../src/protocol.c)
target_include_directories(test_protocol PRIVATE ../src)
target_compile_options(test_protocol PRIVATE -Wall -Wextra -Werror)
add_test(NAME protocol COMMAND test_protocol)
