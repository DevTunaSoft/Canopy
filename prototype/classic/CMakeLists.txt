cmake_minimum_required(VERSION 3.21)
project(canopy_classic_spike VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Qt6 6.4 REQUIRED COMPONENTS Quick QuickControls2)
qt_standard_project_setup()
qt_add_executable(canopy-classic-spike main.cpp)
qt_add_qml_module(canopy-classic-spike
    URI Canopy.Classic
    VERSION 1.0
    QML_FILES Main.qml Theme.qml DockTile.qml PreviewWindow.qml Landscape.qml LauncherOverlay.qml
)
# Explicitly opt in to separately staged, reviewed PNGs. The default build
# contains no replacement artwork and keeps the original Canvas fallbacks.
set(CANOPY_REVIEWED_ICONS_DIR "" CACHE PATH "Optional review-only icon staging directory")
if(CANOPY_REVIEWED_ICONS_DIR)
    if(NOT EXISTS "${CANOPY_REVIEWED_ICONS_DIR}/staged-icons.json")
        message(FATAL_ERROR "Expected staged-icons.json from prepare_classic_icons.py")
    endif()
    file(READ "${CANOPY_REVIEWED_ICONS_DIR}/staged-icons.json" staged_manifest)
    string(JSON scope GET "${staged_manifest}" scope)
    if(NOT scope STREQUAL "review_only_not_release_approved")
        message(FATAL_ERROR "Icon staging manifest scope not recognized")
    endif()
    set(reviewed_files)
    foreach(app browser mail files calendar photos music terminal settings)
        if(NOT EXISTS "${CANOPY_REVIEWED_ICONS_DIR}/${app}.png")
            message(FATAL_ERROR "Missing staged Canopy icon: ${app}.png")
        endif()
        list(APPEND reviewed_files "${CANOPY_REVIEWED_ICONS_DIR}/${app}.png")
    endforeach()
    qt_add_resources(canopy-classic-spike "canopy_reviewed_icons"
        PREFIX "/canopy/classic/icons"
        BASE "${CANOPY_REVIEWED_ICONS_DIR}"
        FILES ${reviewed_files}
    )
endif()
target_link_libraries(canopy-classic-spike PRIVATE Qt6::Quick Qt6::QuickControls2)
install(TARGETS canopy-classic-spike RUNTIME DESTINATION bin)
