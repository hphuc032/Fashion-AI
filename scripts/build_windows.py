"""Build a local one-folder managed-runtime distribution; never publish it."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def copy_ignore(folder,names):
    return [n for n in names if n in {'__pycache__','.cache','.git','node_modules','PyInstaller','_pyinstaller_hooks_contrib','tests','test'}
            or n.startswith('_virtualenv') or n.endswith(('.pyc','.pyo','.onnx','.pt','.pth.tmp','.pdparams','.pdiparams','.safetensors','.gguf','.mp4','.wav','.mp3','.ogg','.db','.sqlite'))]


def build(runtime,site_packages,ffmpeg,ffprobe,notice,ffmpeg_license,output,archive=True):
    if sys.platform!='win32':raise RuntimeError('Build and test Windows artifacts on Windows.')
    from app.version import __version__
    runtime,site_packages,output=Path(runtime).resolve(),Path(site_packages).resolve(),Path(output).resolve()
    if output.exists():raise ValueError('Use a new output folder; never overwrite a previous distribution.')
    if any(output.is_relative_to(p) for p in [runtime,site_packages,ROOT/'app',ROOT/'scripts']):raise ValueError('Output must be outside source/runtime package trees.')
    if not (runtime/'python.exe').is_file() or not site_packages.is_dir():raise ValueError('Supply complete CPython3.11 runtime and pinned installed dependencies.')
    subprocess.run([str(runtime/'python.exe'),'-c','import sys,struct; assert sys.version_info[:2]==(3,11) and struct.calcsize("P")==8'],check=True)
    if any((site_packages/name).exists() for name in ['.env','secrets.toml']):raise ValueError('Unexpected secret file in package source.')
    for path in [ffmpeg,ffprobe,notice,ffmpeg_license]:
        if not Path(path).is_file():raise ValueError('FFmpeg binaries and distribution license/source notice are required.')
    subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','--onedir','--console','--noupx','--name','FashionAILocalizer',
        '--distpath',str(output.parent/('launcher-'+output.name)),'--workpath',str(ROOT/'build'/output.name),'--specpath',str(ROOT/'build'/output.name),
        str(ROOT/'app/desktop/launcher.py')],check=True,cwd=ROOT)
    launcher=output.parent/('launcher-'+output.name)/'FashionAILocalizer'
    shutil.copytree(launcher,output)
    shutil.copytree(runtime,output/'_runtime',ignore=copy_ignore)
    target=output/'_runtime/Lib/site-packages';target.mkdir(parents=True,exist_ok=True)
    shutil.copytree(site_packages,target,dirs_exist_ok=True,ignore=copy_ignore)
    code=output/'_code';code.mkdir()
    for name in ['app','scripts','.streamlit']:
        shutil.copytree(ROOT/name,code/name,ignore=copy_ignore)
    wrappers=output/'scripts';wrappers.mkdir()
    for name in ['start_windows.ps1','start_windows.bat','check_environment.ps1']:shutil.copy2(ROOT/'scripts'/name,wrappers/name)
    for name in ['.env.example','requirements.txt','requirements-m1.txt','requirements-m2.txt','requirements-m3.txt','requirements-m4.txt']:
        shutil.copy2(ROOT/name,code/name)
    tools=output/'tools';tools.mkdir()
    shutil.copy2(ffmpeg,tools/'ffmpeg.exe');shutil.copy2(ffprobe,tools/'ffprobe.exe');shutil.copy2(notice,tools/'FFMPEG-NOTICE.txt')
    shutil.copy2(ffmpeg_license,tools/'FFMPEG-LICENSE.txt')
    docs=output/'docs';docs.mkdir()
    for name in ['WINDOWS_INSTALLATION.md','WINDOWS_TROUBLESHOOTING.md','M5_IMPLEMENTATION_PLAN.md']:
        shutil.copy2(ROOT/'docs'/name,docs/name)
    licenses=output/'licenses';licenses.mkdir()
    for p in runtime.iterdir():
        if p.is_file() and any(word in p.name.lower() for word in ['license','copying','notice']):shutil.copy2(p,licenses/p.name)
    inventory=sorted([dict(name=d.metadata.get('Name'),version=d.version,license=d.metadata.get('License-Expression') or d.metadata.get('License')) for d in importlib.metadata.distributions(path=[str(site_packages)])],key=lambda d:(d['name'] or '').lower())
    (licenses/'dependencies.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    (licenses/'NOTICE.txt').write_text('CPython and third-party license files remain in _runtime and each .dist-info/licenses directory.\nFFmpeg build/license/source notice: tools/FFMPEG-NOTICE.txt.\nPyInstaller bootloader license/exceptions: https://pyinstaller.org/en/stable/license.html\nAI models are external and not included; see _code/app/desktop/models.json for model terms.\n',encoding='utf-8')
    (output/'START_HERE.txt').write_text('Run FashionAILocalizer.exe. Keep the entire folder together.\nData defaults to %LOCALAPPDATA%\\FashionAILocalizer, outside this application folder.\nUse the dashboard Desktop & Models page for explicit model installation.\nRead docs/WINDOWS_INSTALLATION.md before upgrade/removal.\nThis is a local test build, not a clean-Windows-qualified installer.\n',encoding='utf-8')
    files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
    bad=[name for name in files if Path(name).name in {'.env','secrets.toml'} or Path(name).suffix.lower() in {'.db','.sqlite','.sqlite3','.mp4','.wav','.onnx','.pdparams','.pdiparams'}]
    if bad:raise ValueError('Forbidden distribution payload paths: '+','.join(bad[:5]))
    manifest=dict(format=1,version=__version__,python='3.11',kind='PyInstaller launcher + managed CPython one-folder',models_bundled=False,files=files)
    (output/'distribution-manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2),encoding='utf-8')
    if archive:
        zipped=output.with_suffix('.zip')
        if zipped.exists():raise ValueError('Distribution archive already exists.')
        with zipfile.ZipFile(zipped,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as stream:
            for p in output.rglob('*'):
                if p.is_file():stream.write(p,output.name+'/'+p.relative_to(output).as_posix())
        zipped.with_suffix('.zip.sha256').write_text(sha(zipped)+'  '+zipped.name+'\n',encoding='ascii')
    return dict(path=str(output),version=__version__,files=len(files),bytes=sum(p.stat().st_size for p in output.rglob('*') if p.is_file()))


if __name__=='__main__':
    sys.path.insert(0,str(ROOT))
    parser=argparse.ArgumentParser();parser.add_argument('--python-home',type=Path,required=True);parser.add_argument('--site-packages',type=Path,required=True)
    parser.add_argument('--ffmpeg',type=Path,required=True);parser.add_argument('--ffprobe',type=Path,required=True);parser.add_argument('--ffmpeg-notice',type=Path,required=True)
    parser.add_argument('--ffmpeg-license',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--no-archive',action='store_true');a=parser.parse_args()
    print(json.dumps(build(a.python_home,a.site_packages,a.ffmpeg,a.ffprobe,a.ffmpeg_notice,a.ffmpeg_license,a.output,not a.no_archive)))
