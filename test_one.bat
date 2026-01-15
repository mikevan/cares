@echo off
REM Run ONE test to see full error details

echo Running single test to see errors...
echo.

REM Run just one smoke test with full output
pytest tests\smoke\test_health_checks.py::TestDatabaseConnectivity::test_database_connection -v --tb=long --capture=no

echo.
echo ============================================
echo.
echo If you see errors above, copy and paste them.
echo.
pause
