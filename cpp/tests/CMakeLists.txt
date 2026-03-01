include(FetchContent)

FetchContent_Declare(
    Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG v3.5.2
)
FetchContent_MakeAvailable(Catch2)

add_executable(quant_core_tests
    test_cost_model.cpp
    test_paper_broker.cpp
    test_metrics.cpp
    test_backtest_engine.cpp
)

target_include_directories(quant_core_tests PRIVATE ${CMAKE_SOURCE_DIR}/include)
target_link_libraries(quant_core_tests PRIVATE Catch2::Catch2WithMain)

# Link against the source files directly (not the pybind11 module)
target_sources(quant_core_tests PRIVATE
    ${CMAKE_SOURCE_DIR}/src/cost_model.cpp
    ${CMAKE_SOURCE_DIR}/src/paper_broker.cpp
    ${CMAKE_SOURCE_DIR}/src/risk_checks.cpp
    ${CMAKE_SOURCE_DIR}/src/position_sizer.cpp
    ${CMAKE_SOURCE_DIR}/src/signal_reconciler.cpp
    ${CMAKE_SOURCE_DIR}/src/metrics.cpp
    ${CMAKE_SOURCE_DIR}/src/backtest_engine.cpp
)

include(CTest)
include(Catch2::Catch)
catch_discover_tests(quant_core_tests)
