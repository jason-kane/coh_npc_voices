powershell Invoke-PS2EXE .\win_install.ps1 .\win_install.exe
rename venv venv_backup
copy /Y config.json config.json.backup
copy /Y config.json.default config.json

py -m venv --clear venv
copy /Y win_venv_mover\activate.bat venv\Scripts\activate.bat
copy /Y win_venv_mover\Activate.ps1 venv\Scripts\Activate.ps1
