"""Build with a real exit code and a compact retained log on Windows."""
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
(root / '.runtime').mkdir(parents=True, exist_ok=True)
with (root/'.runtime/pilot-build.log').open('w',encoding='utf-8') as log:
 result=subprocess.run(['npm.cmd','run','build','--','--mode','pilot'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
if result.returncode:
 print((root/'.runtime/pilot-build.log').read_text(encoding='utf-8')[-4000:])
raise SystemExit(result.returncode)
