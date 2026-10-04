cmake_minimum_required(VERSION 3.13)

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(neocart_programmer C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(neocart_programmer
    main.c
    flash_programmer.c
)

target_include_directories(neocart_programmer PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

target_link_libraries(neocart_programmer
    pico_stdlib
    hardware_gpio
    tinyusb_device
    tinyusb_board
)

# USB CDC serial (stdio over USB, not UART)
pico_enable_stdio_usb(neocart_programmer 1)
pico_enable_stdio_uart(neocart_programmer 0)

pico_add_extra_outputs(neocart_programmer)
