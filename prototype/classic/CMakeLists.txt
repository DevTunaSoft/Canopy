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
    QML_FILES Main.qml Theme.qml DockTile.qml PreviewWindow.qml Wallpaper.qml FolderTile.qml AppLauncher.qml
)
qt_add_resources(canopy-classic-spike "canopy-original-art"
    PREFIX "/Canopy/Classic"
    FILES assets/approved/manifest.json
          assets/wallpapers/blue-current.svg
          assets/ui/folder-blue.svg
          assets/brand/penguin-launcher.svg
          assets/icons/files.svg assets/icons/browser.svg
          assets/icons/photos.svg assets/icons/settings.svg
          assets/icons/terminal.svg assets/icons/trash.svg
)
target_link_libraries(canopy-classic-spike PRIVATE Qt6::Quick Qt6::QuickControls2)
install(TARGETS canopy-classic-spike RUNTIME DESTINATION bin)
