# Standalone compiled self-test for the new, not-yet-registered Classic
# window-activation component. Deliberately separate from the owned
# prototype/classic/CMakeLists.txt: no owned file is modified by this project.
cmake_minimum_required(VERSION 3.16)
project(canopy-window-activation-self-test LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Qml)

qt_add_executable(window-activation-self-test
    test_main.cpp
    ../WindowActivationState.cpp
    ../WindowActivationState.h
)
target_include_directories(window-activation-self-test PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/..
)
target_link_libraries(window-activation-self-test PRIVATE Qt6::Core Qt6::Qml)
