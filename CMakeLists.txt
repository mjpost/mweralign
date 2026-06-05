cmake_minimum_required(VERSION 3.15)

project(mweralign
    VERSION 1.1.0
    DESCRIPTION "Minimum Word Error Rate alignment for speech translation evaluation"
    LANGUAGES CXX)

# Default to a release build when none is specified.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(MWERALIGN_WERROR "Treat compiler warnings as errors" OFF)

# zlib is required by gzstream.
find_package(ZLIB REQUIRED)

# Core algorithm library, shared between the CLI and (potentially) other tools.
add_library(mweralign_lib STATIC
    src/IOfile.cc
    src/mwerAlign.cc
    src/SimpleText2.cc
    src/gzstream.cc
)
target_include_directories(mweralign_lib PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(mweralign_lib PUBLIC ZLIB::ZLIB)
target_compile_options(mweralign_lib PRIVATE -Wall)
if(MWERALIGN_WERROR)
    target_compile_options(mweralign_lib PRIVATE -Werror)
endif()

# Command-line tool.
add_executable(mweralign src/main.cc)
target_link_libraries(mweralign PRIVATE mweralign_lib)

install(TARGETS mweralign
    RUNTIME DESTINATION bin)
install(TARGETS mweralign_lib
    ARCHIVE DESTINATION lib)
install(FILES
    src/mwerAlign.hh
    src/SimpleText2.hh
    src/IOfile.hh
    src/gzstream.hh
    DESTINATION include)
