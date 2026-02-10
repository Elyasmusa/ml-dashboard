# Development — run frontend and backend

Quick commands to run both services locally from the project root.

Install Node deps (root + frontend):

```bash
npm run install-all
```

Start both services (cross-platform):

```bash
npm run dev
```

Alternative helpers:

- PowerShell (opens two separate windows):

```powershell
.\run-dev.ps1
```

- POSIX (backgrounded processes):

```bash
chmod +x ./run-dev.sh
./run-dev.sh
```

Notes:
- Ensure Python and a virtual environment are set up for the backend. Example:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r backend/requirements.txt
```

- On macOS/Linux replace the activation command with `source .venv/bin/activate`.
