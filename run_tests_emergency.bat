@echo off
REM Emergency Test Runner - Captures All Errors

echo ============================================
echo EMERGENCY TEST RUNNER
echo ============================================
echo.

REM Create reports directory
if not exist "tests\reports" mkdir tests\reports
echo Created: tests\reports\

REM Create coverage directory
if not exist "htmlcov" mkdir htmlcov
echo Created: htmlcov\

echo.
echo Running tests and capturing all output...
echo.

REM Run pytest and capture everything to file
pytest tests\ -v --tb=long --html=tests\reports\test_report.html --self-contained-html > test_errors.txt 2>&1

echo.
echo ============================================
echo RESULTS
echo ============================================
echo.
echo Full output saved to: test_errors.txt
echo HTML report saved to: tests\reports\test_report.html
echo.
echo Opening error log...
echo.

REM Show the error log
type test_errors.txt

echo.
echo ============================================
echo You can now share test_errors.txt
echo ============================================

pause
