"""Run the integrated API and UI together; keep this terminal open. No packages are installed."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-port',type=int,default=8000)
    parser.add_argument('--web-port',type=int,default=5173)
    args=parser.parse_args()
    if args.api_port==args.web_port or not all(1<=p<=65535 for p in (args.api_port,args.web_port)):
        parser.error('Choose distinct valid API and web ports')
    npm=shutil.which('npm')
    if not npm or not (ROOT/'frontend/node_modules').is_dir():
        raise SystemExit('Install Node.js 22+, then run npm ci in frontend/ before launching.')
    env={**os.environ,'VITE_API_BASE_URL':f'http://localhost:{args.api_port}',
         'POLTERGEIST_CORS_ORIGINS':f'http://localhost:{args.web_port},http://127.0.0.1:{args.web_port}'}
    children=[]
    try:
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',str(args.api_port)],cwd=ROOT,env=env))
        children.append(subprocess.Popen([npm,'run','dev','--','--port',str(args.web_port),'--strictPort'],cwd=ROOT/'frontend',env=env))
        print(f'Poltergeist: http://localhost:{args.web_port} — keep this terminal open; Ctrl+C stops both services.',flush=True)
        while all(child.poll() is None for child in children):time.sleep(.5)
        raise SystemExit('A service stopped. Read its error above; try different ports if they are occupied.')
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:child.terminate()
        for child in children:
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill()

if __name__=='__main__':main()
