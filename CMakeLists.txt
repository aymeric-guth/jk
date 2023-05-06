cmake_minimum_required(VERSION 3.10.2)
project(jk-wrapper)
enable_language(C)

add_compile_options(-W -Wall -Werror -Wno-unused-parameter)
add_executable(${PROJECT_NAME} main.c fifo.c)

target_link_libraries(${PROJECT_NAME} PUBLIC m)
target_link_libraries(${PROJECT_NAME} PUBLIC pthread)

install(TARGETS ${PROJECT_NAME} DESTINATION $ENV{WORKSPACE}/usr/bin)
