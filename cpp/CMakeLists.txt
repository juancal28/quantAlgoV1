cmake_minimum_required(VERSION 3.15)
project(quant_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(pybind11 CONFIG REQUIRED)

# Collect all source files
set(QUANT_CORE_SOURCES
    src/cost_model.cpp
    src/paper_broker.cpp
    src/risk_checks.cpp
    src/position_sizer.cpp
    src/signal_reconciler.cpp
    src/metrics.cpp
    src/backtest_engine.cpp
)

# Collect all binding files
set(QUANT_CORE_BINDINGS
    bindings/module.cpp
    bindings/bind_cost_model.cpp
    bindings/bind_order_position.cpp
    bindings/bind_paper_broker.cpp
    bindings/bind_risk.cpp
    bindings/bind_position_sizer.cpp
    bindings/bind_signal_reconciler.cpp
    bindings/bind_metrics.cpp
    bindings/bind_backtest.cpp
)

pybind11_add_module(_quant_core ${QUANT_CORE_SOURCES} ${QUANT_CORE_BINDINGS})

target_include_directories(_quant_core PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)

install(TARGETS _quant_core DESTINATION .)
