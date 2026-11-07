"""Small frozen launcher; AI workers use the bundled real Python interpreter."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
import urllib.request
import webbrowser


def bundle_root():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]


def default_data():
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / '.local/share')
    return Path(base) / 'FashionAILocalizer'


class InstanceLock:
    def __init__(self, root):
        self.path = Path(root) / 'desktop.lock'
        self.stream = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        self.stream.seek(0)
        if self.path.stat().st_size == 0:
            self.stream.write(b'0'); self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.stream.close(); self.stream = None
            return False

    def close(self):
        if self.stream:
            self.stream.close(); self.stream = None


def write_status(root, payload):
    target = Path(root) / 'desktop-status.json'
    partial = target.with_suffix('.tmp')
    partial.write_text(json.dumps(payload), encoding='utf-8')
    partial.replace(target)


def read_status(root):
    try:
        return json.loads((Path(root) / 'desktop-status.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def owned_process(status):
    import psutil
    try:
        p = psutil.Process(status['server_pid'])
        command = p.cmdline()
        if abs(p.create_time() - status['server_created']) > .01:
            return None
        if str(Path(p.exe()).resolve()).casefold() != str(Path(status['python']).resolve()).casefold():
            return None
        if 'streamlit' not in command or status['token'] not in ' '.join(command):
            return None
        return p
    except (KeyError, TypeError, psutil.Error):
        return None


def healthy(status):
    token = status.get('token', '')
    port = status.get('port', 0)
    if not isinstance(port, int) or not 1024 <= port <= 65535 or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
        return False
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/{token}/_stcore/health', timeout=1) as r:
            return r.status == 200 and r.read(32).strip() == b'ok'
    except OSError:
        return False


def stop_owned(status):
    import psutil
    p = owned_process(status)
    if not p:
        return False
    children = p.children(recursive=True)
    for child in reversed(children):
        try: child.terminate()
        except psutil.Error: pass
    _, alive = psutil.wait_procs(children, timeout=3)
    for child in alive:
        try: child.kill()
        except psutil.Error: pass
    try: p.terminate(); p.wait(timeout=5)
    except psutil.NoSuchProcess: pass
    except psutil.TimeoutExpired: p.kill(); p.wait(timeout=3)
    return True


def paths(root):
    code = root / '_code' if (root / '_code').is_dir() else root
    python = root / '_runtime/python.exe'
    if not python.is_file() and not getattr(sys, 'frozen', False):
        python = Path(sys.executable)
    tools = root / 'tools'
    return code, python, tools


def child_environment(root, data, models=None):
    code, python, tools = paths(root)
    env = os.environ.copy()
    for name in ['PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', '_MEIPASS2', 'PYINSTALLER_RESET_ENVIRONMENT']:
        env.pop(name, None)
    for name in list(env):
        if name.startswith('_PYI_'): env.pop(name)
    models = Path(models).resolve() if models else data / 'models'
    env.update(PYTHONUTF8='1', PYTHONNOUSERSITE='1', PYTHONPATH=str(code), FASHION_AI_ENV_FILE=str(data/'config.env'),
               FASHION_AI_DESKTOP='1', STORAGE_ROOT=str(data/'storage'), DATABASE_URL='sqlite:///'+(data/'storage/fashion_ai.db').as_posix(),
               OCR_MODELS_DIR=str(models/'paddle'), ARGOS_MODELS_DIR=str(models/'argos'), WHISPER_MODEL_DIR=str(models/'whisper-base'),
               TTS_MODEL_DIR=str(models/'vits-piper-vi_VN-vais1000-medium'), ASR_MODEL_DIR=str(models/'funasr'),
               FASHION_AI_MODELS_DIR=str(models), FASHION_AI_DATA_DIR=str(data), OMP_NUM_THREADS='2',
               FASHION_AI_DISTRIBUTION=str(root), HF_HUB_OFFLINE='1', PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True')
    for key, name in [('FFMPEG_PATH','ffmpeg.exe'), ('FFPROBE_PATH','ffprobe.exe')]:
        if (tools/name).is_file(): env[key] = str(tools/name)
    return env


def initialize_data(data):
    for name in ['storage', 'storage/projects', 'storage/temp', 'logs', 'models']:
        (data/name).mkdir(parents=True, exist_ok=True)
    config = data/'config.env'
    if not config.exists():
        try:
            with config.open('x', encoding='utf-8') as stream:
                stream.write('ASR_PROVIDER=whisper\nTRANSLATION_PROVIDER=argos\nTTS_PROVIDER=local\n')
        except FileExistsError: pass


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fashion AI Localizer — local Windows launcher')
    parser.add_argument('--data-dir', type=Path, default=default_data())
    parser.add_argument('--models-dir', type=Path)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--clean-temp', action='store_true')
    parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args(argv)
    root, data = bundle_root(), args.data_dir.resolve()
    code, python, tools = paths(root)
    if args.stop:
        status=read_status(data)
        if not owned_process(status):return 1
        status.update(stop_requested=True,state='stopping');write_status(data,status)
        if not stop_owned(status):return 1
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            released=InstanceLock(data)
            if released.acquire():released.close();return 0
            time.sleep(.1)
        print('Server stopped; launcher lock is still releasing. Retry maintenance shortly.');return 1
    if args.restore:data.mkdir(parents=True,exist_ok=True)
    else:initialize_data(data)
    lock = InstanceLock(data)
    if not lock.acquire():
        status = read_status(data)
        if owned_process(status) and healthy(status):
            print('Application already running; reusing local dashboard.')
            if not args.no_browser: webbrowser.open(status['url'])
            return 0
        print('Another instance is starting or maintenance is active. See data/logs.'); return 2
    process = None
    env = child_environment(root, data, args.models_dir)
    try:
        if not python.is_file() or not (code/'app/main.py').is_file():
            raise RuntimeError('Distribution incomplete: restore the entire runtime/code folder.')
        # PyInstaller's DLL search path must not leak into the real Python child.
        if os.name == 'nt' and getattr(sys, 'frozen', False): ctypes.windll.kernel32.SetDllDirectoryW(None)
        command = [str(python), '-m', 'app.desktop.runtime', '--data-dir', str(data)]
        if args.backup: command += ['--backup', str(args.backup.resolve())]
        if args.restore: command += ['--restore', str(args.restore.resolve())]
        if args.clean_temp: command += ['--clean-temp']
        if args.confirm: command += ['--confirm']
        result = subprocess.run(command, cwd=code, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
        # Runtime emits only curated diagnostics, never configuration values/credentials.
        if result.stdout: print(result.stdout.strip())
        if result.returncode: raise RuntimeError('Environment/maintenance check failed. See logs and troubleshooting guide.')
        if args.check or args.backup or args.restore or args.clean_temp: return 0
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        token = uuid.uuid4().hex
        url = f'http://127.0.0.1:{port}/{token}/'
        log = data/'logs/streamlit.log'
        with log.open('ab') as output:
            process = subprocess.Popen([str(python), '-m', 'streamlit', 'run', str(code/'app/main.py'), '--server.address=127.0.0.1',
               f'--server.port={port}', f'--server.baseUrlPath={token}', '--server.headless=true', '--browser.gatherUsageStats=false'],
               cwd=code, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
               creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        import psutil
        status = dict(state='starting', launcher_pid=os.getpid(), server_pid=process.pid, server_created=psutil.Process(process.pid).create_time(),
                      python=str(python), token=token, port=port, url=url, data_dir=str(data), log=str(log))
        write_status(data,status)
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            if process.poll() is not None: raise RuntimeError('Server stopped before startup. See logs/streamlit.log.')
            if healthy(status): break
            time.sleep(.2)
        else: raise RuntimeError('Server startup timed out. Check port/runtime and logs.')
        status['state']='running'; write_status(data,status)
        print('READY — '+url+'\nData: '+str(data)+'\nLog: '+str(log)+'\nPress Ctrl+C to stop safely.')
        if not args.no_browser: webbrowser.open(url)
        while process.poll() is None: time.sleep(.5)
        return 0 if process.returncode==0 or read_status(data).get('stop_requested') else 1
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print('Startup failed ('+type(exc).__name__+'). '+str(exc) if isinstance(exc,RuntimeError) else 'Startup failed. See logs/runtime-check.log.')
        return 1
    finally:
        if process: stop_owned(read_status(data))
        status=read_status(data)
        if status.get('launcher_pid')==os.getpid(): status['state']='stopped'; write_status(data,status)
        lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
