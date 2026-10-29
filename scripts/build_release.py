"""Build locally on the target OS; CI uses the identical commands."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
build = root / 'build'
build.mkdir(exist_ok=True)
image = Image.new('RGBA', (1024, 1024))
d = ImageDraw.Draw(image)
d.rounded_rectangle((64, 128, 960, 960), 180, fill='#2563eb')
d.rectangle((80, 320, 944, 384), fill='white')
for x in (320, 704):
    d.line((x, 64, x, 256), fill='white', width=80)
d.line((512, 496, 512, 688, 688, 688), fill='white', width=64)
mac = sys.platform == 'darwin'
icon = build / ('icon.icns' if mac else 'icon.ico')
image.save(icon)
args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--name', 'MeetingLight', '--icon', str(icon), '--paths', str(root / 'source'),
        '--collect-all', 'tzdata', '--hidden-import', 'PIL._tkinter_finder',
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
if mac:
    import plistlib
    plist = bundle / 'Contents/Info.plist'
    data = plistlib.loads(plist.read_bytes())
    data.update(CFBundleShortVersionString='1.1.0', CFBundleVersion='1.1.0',
                NSHighResolutionCapable=True)
    plist.write_bytes(plistlib.dumps(data))
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(bundle)], check=True)
    executable = bundle / 'Contents/MacOS/MeetingLight'
else:
    executable = bundle / 'MeetingLight.exe'
subprocess.run([str(executable), '--self-check'], check=True, timeout=90)
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
