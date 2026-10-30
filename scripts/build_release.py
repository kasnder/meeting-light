"""Build locally on the target OS; CI uses the identical commands."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'source'))
from meetinglight.icon import icon_image

build = root / 'build'
build.mkdir(exist_ok=True)
mac = sys.platform == 'darwin'
icon = build / ('icon.icns' if mac else 'icon.ico')
icon_image(1024, padded=mac).save(icon)
args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--name', 'MeetingLight', '--icon', str(icon), '--paths', str(root / 'source'),
        '--collect-all', 'tzdata', '--collect-all', 'sv_ttk', '--hidden-import', 'PIL._tkinter_finder',
        '--distpath', str(root / 'dist'), '--workpath', str(build / 'pyinstaller'), '--specpath', str(build)]
if mac:
    args += ['--windowed', '--osx-bundle-identifier', 'net.kollnig.MeetingLight',
             '--hidden-import', 'keyring.backends.macOS', '--hidden-import', 'pystray._darwin',
             '--collect-all', 'cryptography']
else:
    args += ['--windowed', '--hidden-import', 'pystray._win32']
args.append(str(root / 'source' / 'run.py'))
subprocess.run(args, check=True, cwd=root)
bundle = root / 'dist' / ('MeetingLight.app' if mac else 'MeetingLight')
documentation = bundle / 'Contents/Resources' if mac else bundle
for name in ('LICENSE', 'README.md', 'MACOS.md'):
    shutil.copyfile(root / name, documentation / name)
shutil.copytree(root / 'licenses', documentation / 'licenses', dirs_exist_ok=True)
if mac:
    import plistlib
    plist = bundle / 'Contents/Info.plist'
    data = plistlib.loads(plist.read_bytes())
    data.update(CFBundleShortVersionString='1.1.2', CFBundleVersion='1.1.2',
                NSHighResolutionCapable=True)
    plist.write_bytes(plistlib.dumps(data))
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(bundle)], check=True)
    executable = bundle / 'Contents/MacOS/MeetingLight'
else:
    executable = bundle / 'MeetingLight.exe'
check_report = build / 'selfcheck.json'
try:
    subprocess.run([str(executable), '--self-check'], check=True, timeout=90,
                   env=dict(os.environ, MEETINGLIGHT_CHECK_REPORT=str(check_report)))
finally:
    print(check_report.read_text() if check_report.exists() else 'Self-check did not reach application entry point', flush=True)
artifact = root / 'artifacts'
artifact.mkdir(exist_ok=True)
arch = platform.machine().lower().replace('amd64', 'x86_64')
archive = artifact / f'MeetingLight-{ "macOS" if mac else "Windows" }-{arch}.zip'
if mac:
    subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(bundle), str(archive)], check=True)
else:
    shutil.make_archive(str(archive.with_suffix('')), 'zip', bundle.parent, bundle.name)
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(artifact / (archive.name + '.sha256')).write_text(f'{digest}  {archive.name}\n')
print(json.dumps({'asset': archive.name, 'sha256': digest}))
