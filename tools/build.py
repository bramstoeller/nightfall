"""Build a portable application folder and archive for the current platform."""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def bundle_windows_media(source, output):
    """Copy the actual static tools, never Chocolatey command shims."""
    source = Path(source)
    for name in ['ffmpeg.exe', 'ffprobe.exe']:
        if not (source/name).is_file():
            raise FileNotFoundError(f'{source/name} is missing. Run tools/fetch_windows_ffmpeg.py first.')
    license_file = source.parent/'LICENSE'
    if not license_file.is_file():
        raise FileNotFoundError(f'{license_file} is missing from the FFmpeg distribution.')
    encoder_list = subprocess.check_output(
        [str(source/'ffmpeg.exe'), '-hide_banner', '-encoders'], text=True)
    if ' libx264 ' not in encoder_list:
        raise RuntimeError('The bundled FFmpeg must include the libx264 encoder.')
    subprocess.run([str(source/'ffprobe.exe'), '-version'], check=True, capture_output=True)
    target = output/'bin'
    target.mkdir(parents=True, exist_ok=True)
    for name in ['ffmpeg.exe', 'ffprobe.exe']:
        shutil.copy2(source/name, target/name)
    notices = output/'licenses/ffmpeg'
    notices.mkdir(parents=True, exist_ok=True)
    for name in ['LICENSE', 'README.txt', 'PROVENANCE.txt']:
        if (source.parent/name).is_file():
            shutil.copy2(source.parent/name, notices/name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg-dir', type=Path, default=ROOT/'build/ffmpeg-win64/bin',
                        help='Windows static FFmpeg bin directory, with its original LICENSE in the parent directory.')
    args = parser.parse_args()
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    str(ROOT/'nightfall.spec')], cwd=ROOT, check=True)
    output = ROOT/'dist/nightfall'
    shutil.copy2(ROOT/'README.md', output/'README.md')
    if sys.platform == 'win32':
        bundle_windows_media(args.ffmpeg_dir, output)
    # The build never copies personal projects or local render output.
    platform = 'windows' if sys.platform == 'win32' else 'linux'
    format = 'zip' if sys.platform == 'win32' else 'gztar'
    archive = shutil.make_archive(str(ROOT/f'dist/nightfall-{platform}'), format,
                                  root_dir=ROOT/'dist', base_dir='nightfall')
    print(archive)


if __name__ == '__main__':
    main()
