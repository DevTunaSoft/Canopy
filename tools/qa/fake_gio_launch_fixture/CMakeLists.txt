cmake_minimum_required(VERSION 3.21)
project(canopy_fake_gio_launch_fixture LANGUAGES C CXX)

# Synthetic QA fixture only. Compiles the UNMODIFIED production launcher
# source (exported by run_fixture.sh into LAUNCHER_SRC_DIR) against a fake GIO
# shim. Nothing here is linked into Canopy Classic, and no GLib/GIO dev
# package, desktop database or real application is required.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED LAUNCHER_SRC_DIR OR "${LAUNCHER_SRC_DIR}" STREQUAL "")
  message(FATAL_ERROR "LAUNCHER_SRC_DIR must point at the exported unmodified SystemAppLauncher sources")
endif()
if(NOT EXISTS "${LAUNCHER_SRC_DIR}/SystemAppLauncher.cpp" OR
   NOT EXISTS "${LAUNCHER_SRC_DIR}/SystemAppLauncher.h")
  message(FATAL_ERROR "Exported SystemAppLauncher sources are missing from LAUNCHER_SRC_DIR")
endif()

find_package(Qt6 6.4 REQUIRED COMPONENTS Core)
qt_standard_project_setup()

set(FIXTURE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")

add_library(gio_fake STATIC "${FIXTURE_DIR}/fake_gio/gio_shim.c")
target_include_directories(gio_fake PUBLIC "${FIXTURE_DIR}/fake_gio/include")

# Binary 1: six dock mappings, fallback order and four GIO refusal paths.
qt_add_executable(gio_fixture
  "${FIXTURE_DIR}/harness/system_app_launcher_fixture.cpp"
  "${LAUNCHER_SRC_DIR}/SystemAppLauncher.cpp"
  "${LAUNCHER_SRC_DIR}/SystemAppLauncher.h")
target_compile_definitions(gio_fixture PRIVATE CANOPY_HAVE_GIO=1)
target_include_directories(gio_fixture PRIVATE
  "${LAUNCHER_SRC_DIR}" "${FIXTURE_DIR}/fake_gio/include")
target_link_libraries(gio_fixture PRIVATE Qt6::Core gio_fake)

# Binary 2: the compiled-without-GIO refusal fallback (all seven labels false).
qt_add_executable(gio_fixture_fallback
  "${FIXTURE_DIR}/harness/system_app_launcher_fixture.cpp"
  "${LAUNCHER_SRC_DIR}/SystemAppLauncher.cpp"
  "${LAUNCHER_SRC_DIR}/SystemAppLauncher.h")
target_compile_definitions(gio_fixture_fallback PRIVATE NO_GIO_BUILD=1)
target_include_directories(gio_fixture_fallback PRIVATE "${LAUNCHER_SRC_DIR}")
target_link_libraries(gio_fixture_fallback PRIVATE Qt6::Core gio_fake)
