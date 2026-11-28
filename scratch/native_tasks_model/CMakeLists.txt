cmake_minimum_required(VERSION 3.21)
project(canopy_native_tasks_model LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.4 REQUIRED COMPONENTS Quick QuickControls2)

qt_add_executable(native-task-harness
    src/main.cpp
    src/NativeTaskBoard.cpp
    src/NativeTaskBoard.h
)
qt_add_resources(native-task-harness "canopy-original-dock-icons"
    PREFIX "/Canopy/Classic/assets"
    FILES
        icons/browser.svg
        icons/files.svg
        icons/photos.svg
        icons/settings.svg
        icons/terminal.svg
        icons/trash.svg
)
target_link_libraries(native-task-harness PRIVATE Qt6::Quick Qt6::QuickControls2)

qt_add_executable(native-task-board-probe
    src/board_probe.cpp
    src/NativeTaskBoard.cpp
    src/NativeTaskBoard.h
)
target_link_libraries(native-task-board-probe PRIVATE Qt6::Core)
