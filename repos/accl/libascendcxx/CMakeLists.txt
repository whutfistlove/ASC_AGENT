cmake_minimum_required(VERSION 3.18)
project(libascendcxx LANGUAGES CXX)

enable_testing()
option(LIBASCENDCXX_BUILD_TESTS "Build libascendcxx tests" ON)

# 👇 必须在 add_subdirectory(test/...) 之前定义！
add_library(libascendcxx INTERFACE)
target_include_directories(libascendcxx INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

# 构建测试
if(LIBASCENDCXX_BUILD_TESTS)
    add_subdirectory(test/libascendcxx)  # ← 这个必须在 add_library 之后
endif()

# 提示信息（可选）
if(CMAKE_EXPORT_COMPILE_COMMANDS)
    message(STATUS "Generated compile_commands.json in build directory.")
    message(STATUS "Run: ln -sf build/compile_commands.json .")
endif()