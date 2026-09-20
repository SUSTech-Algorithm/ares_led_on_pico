cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED PICO_SDK_PATH AND NOT DEFINED ENV{PICO_SDK_PATH})
  message(FATAL_ERROR "Set PICO_SDK_PATH to a Raspberry Pi Pico SDK checkout")
endif()

if(DEFINED PICO_SDK_PATH)
  include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)
else()
  include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
endif()

project(ares_led_driver C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(ares_led_driver
  src/main.c
  src/protocol.c
)

# This firmware is C-only. Avoid an unnecessary libstdc++ link dependency that
# some distribution-packaged bare-metal toolchains install separately.
set_target_properties(ares_led_driver PROPERTIES LINKER_LANGUAGE C)

target_include_directories(ares_led_driver PRIVATE src)
target_compile_options(ares_led_driver PRIVATE -Wall -Wextra -Werror)
target_link_libraries(ares_led_driver
  pico_stdlib
  pico_multicore
  hardware_pio
)

pico_generate_pio_header(
  ares_led_driver
  ${CMAKE_CURRENT_LIST_DIR}/src/ws2812.pio
)

pico_enable_stdio_uart(ares_led_driver 0)
pico_enable_stdio_usb(ares_led_driver 1)
pico_set_program_name(ares_led_driver "ares_led_driver")
pico_set_program_version(ares_led_driver "0.1.0")
pico_add_extra_outputs(ares_led_driver)
