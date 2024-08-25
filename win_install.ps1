Set-ExecutionPolicy Unrestricted -Scope Process -Force
venv\Scripts\python.exe -c "import json;import os;print(json.dumps({'path': os.path.join(os.getcwd(), 'venv').replace('\\', '/')}))" > path.json
venv\Scripts\Activate.ps1
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
exit