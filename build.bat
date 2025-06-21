@REM activate the virtual environment
call .venv\\Scripts\\activate.bat

@REM package the sidekick as an executable with a _internal sidecar directory
pyinstaller.exe sidekick.spec --noconfirm 

echo "Executable is dist\\sidekick\\sidekick.exe"