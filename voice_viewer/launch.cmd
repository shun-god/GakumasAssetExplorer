@echo off
where uv >nul 2>&1
if errorlevel 1 (
    echo uv is required. See the Setup section in README.md.
    pause
    exit /b 1
)
pushd "%~dp0.."
uv run --locked python voice_viewer/viewer.py %*
if errorlevel 1 pause
popd
