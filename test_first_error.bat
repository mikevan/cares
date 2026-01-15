@echo off
echo Running tests with stop-on-first-failure...
echo.
echo This will stop at the FIRST error so you can see it.
echo.

REM Run tests but stop at first failure
pytest tests\ -x -v --tb=short

echo.
echo ============================================
echo Test stopped at first error (see above)
echo ============================================
echo.
pause
