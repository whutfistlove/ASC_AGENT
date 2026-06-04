# ==============================
# Options
# ==============================
option(ENABLE_HOST_TESTS "Enable host-side unit tests" ON)
option(ENABLE_DEVICE_TESTS "Enable real-device NPU tests" OFF)
option(ENABLE_KERNEL_SIM_TESTS "Enable kernel simulation via cannsim" ON)

# --- Helper: 从文件名提取算法名（如 max_tests.cpp → max）---
function(get_algo_name_from_host_file FILE_PATH ALGO_NAME_OUT)
    get_filename_component(BASENAME "${FILE_PATH}" NAME_WE) # e.g., "max_tests"
    string(REGEX REPLACE "_tests$" "" ALGO_NAME "${BASENAME}")
    set(${ALGO_NAME_OUT} "${ALGO_NAME}" PARENT_SCOPE)
endfunction()

# --- Host Tests: 自动扫描 ascend/host/*_tests.cpp ---
if(ENABLE_HOST_TESTS)
    file(GLOB HOST_TEST_SOURCES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}
         ${CMAKE_CURRENT_SOURCE_DIR}/ascend/host/*_tests.cpp)

    foreach(host_src IN LISTS HOST_TEST_SOURCES)
        get_algo_name_from_host_file("${CMAKE_CURRENT_SOURCE_DIR}/${host_src}" ALGO_NAME)
        string(MAKE_C_IDENTIFIER "${ALGO_NAME}" SAFE_ALGO_NAME) # 防止非法标识符

        add_executable(${SAFE_ALGO_NAME}_host_test ${host_src})
        target_link_libraries(${SAFE_ALGO_NAME}_host_test PRIVATE libascendcxx)
        target_include_directories(${SAFE_ALGO_NAME}_host_test PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/../../include
        )
        set_target_properties(${SAFE_ALGO_NAME}_host_test PROPERTIES
            CXX_STANDARD 17
            CXX_STANDARD_REQUIRED ON
            CXX_EXTENSIONS OFF
        )
        add_test(NAME "host.${ALGO_NAME}" COMMAND ${SAFE_ALGO_NAME}_host_test)
        message(STATUS "Added host test: ${ALGO_NAME} -> ${host_src}")
    endforeach()
endif()

# --- Device Tests (Real NPU) ---
if(ENABLE_DEVICE_TESTS)
    find_path(ASCEND_INCLUDE_DIR acl/acl.h
        PATHS /usr/local/Ascend/ascend-toolkit/latest/include
              $ENV{ASCEND_HOME}/include
    )
    find_library(ASCENDCL_LIBRARY ascendcl
        PATHS /usr/local/Ascend/ascend-toolkit/latest/lib64
              $ENV{ASCEND_HOME}/lib64
    )

    if(ASCEND_INCLUDE_DIR AND ASCENDCL_LIBRARY)
        file(GLOB DEVICE_TEST_SOURCES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}
             ${CMAKE_CURRENT_SOURCE_DIR}/ascend/device/*_tests.cpp)

        foreach(dev_src IN LISTS DEVICE_TEST_SOURCES)
            get_algo_name_from_host_file("${CMAKE_CURRENT_SOURCE_DIR}/${dev_src}" ALGO_NAME)
            string(MAKE_C_IDENTIFIER "${ALGO_NAME}" SAFE_ALGO_NAME)

            add_executable(${SAFE_ALGO_NAME}_device_test ${dev_src})
            target_include_directories(${SAFE_ALGO_NAME}_device_test PRIVATE
                ${CMAKE_CURRENT_SOURCE_DIR}/../../include
                ${ASCEND_INCLUDE_DIR}
            )
            target_link_libraries(${SAFE_ALGO_NAME}_device_test PRIVATE ${ASCENDCL_LIBRARY})
            set_target_properties(${SAFE_ALGO_NAME}_device_test PROPERTIES
                CXX_STANDARD 17
                CXX_STANDARD_REQUIRED ON
                CXX_EXTENSIONS OFF
            )
            add_test(NAME "device.${ALGO_NAME}" COMMAND ${SAFE_ALGO_NAME}_device_test)
            message(STATUS "Added device test: ${ALGO_NAME} -> ${dev_src}")
        endforeach()
    else()
        message(WARNING "Ascend CANN not found. Skipping device tests.")
    endif()
endif()

# --- Kernel Simulation Tests: 自动扫描 ascend/kernel/*/run_test.sh ---
if(ENABLE_KERNEL_SIM_TESTS)
    file(GLOB KERNEL_SIM_DIRS LIST_DIRECTORIES true
         ${CMAKE_CURRENT_SOURCE_DIR}/ascend/kernel/*)

    foreach(dir IN LISTS KERNEL_SIM_DIRS)
        if(IS_DIRECTORY "${dir}")
            get_filename_component(ALGO_NAME "${dir}" NAME) # e.g., "min_example"
            # 去掉 _example 后缀（约定：目录名为 {algo}_example）
            string(REGEX REPLACE "_example$" "" CLEAN_ALGO_NAME "${ALGO_NAME}")
            if(CLEAN_ALGO_NAME STREQUAL ALGO_NAME)
                # 如果没匹配到 _example，跳过（避免误加其他目录）
                continue()
            endif()

            set(SCRIPT_PATH "${dir}/run_test.sh")
            if(EXISTS "${SCRIPT_PATH}")
                string(MAKE_C_IDENTIFIER "${CLEAN_ALGO_NAME}" SAFE_ALGO_NAME)
                add_test(
                    NAME "kernel.${CLEAN_ALGO_NAME}.sim"
                    COMMAND "${SCRIPT_PATH}"
                )
                set_tests_properties("kernel.${CLEAN_ALGO_NAME}.sim" PROPERTIES
                    WORKING_DIRECTORY "${dir}"
                )
                message(STATUS "Added kernel sim test: ${CLEAN_ALGO_NAME} -> ${SCRIPT_PATH}")
            else()
                message(WARNING "Script not found: ${SCRIPT_PATH}")
            endif()
        endif()
    endforeach()
endif()