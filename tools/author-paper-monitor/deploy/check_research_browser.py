"""Run P1's two-user browser workflow in a throwaway HTTPS/SQLite environment.

Requires the backend venv, an existing Playwright Node package/browser, and openssl.
Uses the current dist-reading build; creates no production identities or paid calls.
"""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--playwright-module',default='playwright')
    parser.add_argument('--browser-executable')
    parser.add_argument('--node',default='node')
    parser.add_argument('--port',type=int,default=8877)
    args=parser.parse_args()
    # Never accidentally run the tests against an unrelated service on this port.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',args.port))
    if not (REPO/'frontend/dist-reading/reading.html').exists():
        raise SystemExit('Build the reader first: cd frontend && npm run build:reading')
    with tempfile.TemporaryDirectory(prefix='pas-p1-browser-') as work:
        path=Path(work);key=path/'key.pem';cert=path/'cert.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        env={**os.environ,'PAS_BROWSER_TEST_DIR':work,'PAS_BROWSER_TEST_ORIGIN':f'https://localhost:{args.port}',
             'PAS_BROWSER_EVIDENCE_DIR':str(REPO/'tools/author-paper-monitor/review-evidence'),'PLAYWRIGHT_MODULE':args.playwright_module}
        if args.browser_executable:env['PLAYWRIGHT_EXECUTABLE_PATH']=args.browser_executable
        with (path/'server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','uvicorn','--app-dir',str(REPO/'backend/tests/browser'),'research_server:app',
                '--port',str(args.port),'--ssl-keyfile',str(key),'--ssl-certfile',str(cert)],env=env,stdout=log,stderr=log)
            try:
                for _ in range(150):
                    if process.poll() is not None:raise RuntimeError('Browser fixture server exited before startup.')
                    try:
                        with socket.create_connection(('127.0.0.1',args.port),timeout=.2):break
                    except OSError:time.sleep(.2)
                else:raise RuntimeError('Browser fixture startup timed out.')
                subprocess.run([args.node,str(REPO/'frontend/scripts/reading_browser_check.cjs')],check=True,env=env,cwd=REPO/'frontend')
            finally:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
