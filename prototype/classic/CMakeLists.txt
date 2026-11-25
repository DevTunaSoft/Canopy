cmake_minimum_required(VERSION 3.21)
project(canopy_classic_spike VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Qt6 6.4 REQUIRED COMPONENTS Quick QuickControls2)
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(GIO_UNIX QUIET IMPORTED_TARGET gio-unix-2.0)
endif()
qt_standard_project_setup()
qt_add_executable(canopy-classic-spike main.cpp WindowActivationState.cpp WindowActivationState.h RoundedDockIconProvider.cpp RoundedDockIconProvider.h SystemAppLauncher.cpp SystemAppLauncher.h)
qt_add_qml_module(canopy-classic-spike
    URI Canopy.Classic
    VERSION 1.0
    QML_FILES Main.qml Theme.qml ClockLabel.qml LauncherOverlay.qml DockTile.qml PreviewWindow.qml Wallpaper.qml FolderTile.qml ShellMenuBar.qml ShellMenuPopupSet.qml WindowActivationIndicators.qml QuickControlsOverlay.qml
    SOURCES FileModel.cpp FileModel.h
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
if(TARGET PkgConfig::GIO_UNIX)
    target_compile_definitions(canopy-classic-spike PRIVATE CANOPY_HAVE_GIO=1)
    target_link_libraries(canopy-classic-spike PRIVATE Qt6::Quick Qt6::QuickControls2 PkgConfig::GIO_UNIX)
else()
    message(STATUS "gio-unix-2.0 dev package absent: native app launching compiles as a disabled fallback")
    target_link_libraries(canopy-classic-spike PRIVATE Qt6::Quick Qt6::QuickControls2)
endif()
install(TARGETS canopy-classic-spike RUNTIME DESTINATION bin)
