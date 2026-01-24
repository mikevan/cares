@echo off
setlocal enabledelayedexpansion

REM Ensure we're using the virtual environment
set VENV_PYTHON=%~dp0.venv\Scripts\python.exe
set VENV_PYTEST=%~dp0.venv\Scripts\pytest.exe

REM Check if venv exists
if not exist "%VENV_PYTHON%" (
    echo ERROR: Virtual environment not found!
    echo Please run: python -m venv .venv
    echo Then: .venv\Scripts\pip.exe install -r requirements-dev.txt
    pause
    exit /b 1
)

REM Default values
set VERBOSE=-v
set COVERAGE=--cov=. --cov-report=html:htmlcov --cov-report=term-missing
set MAXFAIL=--maxfail=5
set MARKERS=
set EXTRA_ARGS=

REM Parse arguments
:parse
if "%~1"=="" goto :run
if /I "%~1"=="--help" goto :help
if /I "%~1"=="-h" goto :help
if /I "%~1"=="-v" (
    set VERBOSE=-v
    shift
    goto :parse
)
if /I "%~1"=="-vv" (
    set VERBOSE=-vv -s
    shift
    goto :parse
)
if /I "%~1"=="--no-cov" (
    set COVERAGE=
    shift
    goto :parse
)
if /I "%~1"=="--fast" (
    set MAXFAIL=--maxfail=1
    shift
    goto :parse
)
if /I "%~1"=="--all" (
    set MAXFAIL=
    shift
    goto :parse
)
if /I "%~1"=="--unit" (
    set MARKERS=-m unit
    shift
    goto :parse
)
if /I "%~1"=="--integration" (
    set MARKERS=-m integration
    shift
    goto :parse
)
if /I "%~1"=="--functional" (
    set MARKERS=-m functional
    shift
    goto :parse
)
if /I "%~1"=="--smoke" (
    set MARKERS=-m smoke
    shift
    goto :parse
)
set EXTRA_ARGS=!EXTRA_ARGS! %~1
shift
goto :parse

:help
echo ================================================================================
echo                         CARES TEST SUITE
echo ================================================================================
echo.
echo Usage: full-test.bat [OPTIONS]
echo.
echo Options:
echo   -h, --help          Show this help message
echo   -v                  Verbose output (default)
echo   -vv                 Extra verbose output with print statements
echo   --no-cov            Skip coverage report (faster)
echo   --fast              Stop after first failure
echo   --all               Run all tests (don't stop on failures)
echo.
echo Test Selection:
echo   --unit              Run only unit tests
echo   --integration       Run only integration tests
echo   --functional        Run only functional tests
echo   --smoke             Run only smoke tests
echo.
echo Environment:
echo   Python: .venv (3.12.10)
echo   All dependencies isolated in virtual environment
echo.
echo Examples:
echo   full-test.bat                   # Run all tests
echo   full-test.bat -vv               # Extra verbose
echo   full-test.bat --unit --no-cov   # Unit tests only, no coverage
echo   full-test.bat --fast            # Stop after first failure
echo.
echo Reports:
echo   - Test Report:     tests\reports\test_report.html
echo   - Coverage Report: htmlcov\index.html
echo ================================================================================
goto :eof

:run
echo ================================================================================
echo                         CARES TEST SUITE
echo ================================================================================
echo Environment: Python 3.12.10 (.venv)
echo.
echo Running tests...
echo.

"%VENV_PYTEST%" tests/ ^
  --html=tests/reports/test_report.html ^
  --self-contained-html ^
  --tb=short ^
  %VERBOSE% ^
  %COVERAGE% ^
  %MAXFAIL% ^
  %MARKERS% ^
  %EXTRA_ARGS%

set EXIT_CODE=%ERRORLEVEL%

echo.
echo ================================================================================
if %EXIT_CODE%==0 (
    echo Tests PASSED!
) else (
    echo Tests FAILED - See reports for details
)
echo.
echo Reports generated:
echo   - Test Report:     tests\reports\test_report.html
echo   - Coverage Report: htmlcov\index.html
echo ================================================================================
echo.

exit /b %EXIT_CODE%