"""Fetch the pinned static Windows x64 media tools at build time only."""
from hashlib import sha256
from pathlib import Path
import shutil
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
VERSION = '8.1.2'
URL = f'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-{VERSION}-essentials_build.zip'
SHA256 = 'db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec'


def unpack(archive, destination):
    """Extract only the runtime executables and their original notices."""
    with ZipFile(archive) as package:
        for name in ['bin/ffmpeg.exe', 'bin/ffprobe.exe', 'LICENSE', 'README.txt']:
            matches = [entry for entry in package.namelist() if entry.endswith('/'+name)]
            if len(matches) != 1:
                raise ValueError(f'FFmpeg archive must contain exactly one {name}.')
            target = destination/name
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(matches[0]) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
    (destination/'PROVENANCE.txt').write_text(
        f'Static Windows x64 FFmpeg essentials build {VERSION}\n'
        f'Archive: {URL}\nSHA-256: {SHA256}\n'
        'Provider, build information and source links: https://www.gyan.dev/ffmpeg/builds/\n'
        'FFmpeg source: https://github.com/FFmpeg/FFmpeg/tree/n8.1.2\n'
        'The original LICENSE and README.txt accompany these unmodified executables.\n',
        encoding='utf8')


def main():
    cache = ROOT/'build'
    cache.mkdir(exist_ok=True)
    archive = cache/f'ffmpeg-{VERSION}-windows-x64.zip'
    if not archive.exists() or sha256(archive.read_bytes()).hexdigest() != SHA256:
        temporary = archive.with_suffix('.partial')
        try:
            with urlopen(URL, timeout=120) as source, temporary.open('wb') as output:
                shutil.copyfileobj(source, output)
            if sha256(temporary.read_bytes()).hexdigest() != SHA256:
                raise ValueError('FFmpeg archive checksum does not match the pinned build.')
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    destination = cache/'ffmpeg-win64'
    unpack(archive, destination)
    print(destination/'bin')


if __name__ == '__main__':
    main()
