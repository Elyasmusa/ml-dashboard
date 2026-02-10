const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const root = path.resolve(__dirname, '..');
const venvWin = path.join(root, '.venv', 'Scripts', 'python.exe');
const venvPosix = path.join(root, '.venv', 'bin', 'python');

let python = null;
if (fs.existsSync(venvWin)) python = venvWin;
else if (fs.existsSync(venvPosix)) python = venvPosix;
else python = 'python';

const backendDir = path.join(root, 'backend');
const args = ['-m', 'uvicorn', 'main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'];

console.log(`Using python: ${python}`);

const p = spawn(python, args, { cwd: backendDir, stdio: 'inherit' });

p.on('close', (code) => {
  process.exit(code);
});
