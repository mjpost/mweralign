cmake_minimum_required(VERSION 3.10)

PROJECT(mwerAlign)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}")

#if you don't want the full compiler output, remove the following line
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++0x ")
SET(CMAKE_VERBOSE_MAKEFILE ON)
#SET( CMAKE_CXX_FLAGS " -Wno-deprecated " CACHE STRING "Flags used by the C++ compiler" FORCE )
#add_definitions(-DCMAKE_INSTALL_PREFIX=YOUR INSTALL DIR HERE!!!)
add_definitions(-DIBPP_LINUX -DIBPP_GCC)
# include_directories(YOUR INCLUDE DIR HERE!!!)
# link_directories(YOUR LIB DIR HERE!!!)

#add definitions, compiler switches, etc.
ADD_DEFINITIONS(-Wall -O2 -static)

# List all source files here
include_directories(BEFORE ${CMAKE_SOURCE_DIR}/src)

set(mwerAlign_LIB_SRCS
    ${CMAKE_SOURCE_DIR}/src/mwerAlign.cc
)
add_library(mwerAlignLib STATIC ${mwerAlign_LIB_SRCS})

SET(mwerAlign_BIN_SRCS
   ${CMAKE_SOURCE_DIR}/src/main.cc
   ${CMAKE_SOURCE_DIR}/src/mwerAlign.cc
)

add_executable(mwerAlign ${mwerAlign_BIN_SRCS})

# add_subdirectory(src)
# add_subdirectory(test)


# add_library(mwerAlignLib STATIC ${mwerAlign_LIB_SRCS})
# add_executable(mwerAlign main.cc)

target_link_libraries(mwerAlign z mwerAlignLib)

install(TARGETS mwerAlign DESTINATION bin)
install(TARGETS mwerAlignLib DESTINATION lib)
install(FILES main.cc  IOfile.hh mwerAlign.cc DESTINATION include)

