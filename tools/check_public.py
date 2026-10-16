"""Reject private projects, source photos and credentials in the Git index."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_JSON = {'examples/house.json', 'tests/fixtures/polygon-draft.json'}
PUBLIC_IMAGES = {'examples/house-day.png', 'examples/house-night.png', 'examples/layout.png'}
PRIVATE_FIELDS = {'observations', 'photo_registration', 'photo_sha256', 'observations_sha256',
                  'camera_intrinsics', 'projector_intrinsics', 'lens_photo_reference',
                  'bay_detail_reference', 'initial_photo_trace', 'dataUrl'}
SECRETS = re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b')


def inspect_json(value, location):
    errors = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in PRIVATE_FIELDS:
                errors.append(f'{location}: private or embedded-image field {key}')
            errors.extend(inspect_json(child, location))
    elif isinstance(value, list):
        for child in value:
            errors.extend(inspect_json(child, location))
    return errors


def check(paths, root=ROOT):
    errors = []
    for name in paths:
        path = Path(name)
        if path.parts[0] in {'private', '.aws', '.codex', '.agents', '.venv', 'renders', 'videos', 'prototype'}:
            errors.append(f'{name}: local/private directory')
        if path.name.startswith('.env') or path.suffix.lower() in {'.pem', '.key', '.mp4', '.mov', '.heic', '.dng', '.raw', '.jpg', '.jpeg'}:
            errors.append(f'{name}: private media or credential file')
        if path.suffix.lower() == '.png' and not (name in PUBLIC_IMAGES or path.parts[0] == 'assets'):
            errors.append(f'{name}: unreviewed image')
        full_path = root/path
        if full_path.is_symlink():
            errors.append(f'{name}: symlinks are not allowed in the public tree')
            continue
        raw = full_path.read_bytes()
        if SECRETS.search(raw):
            errors.append(f'{name}: possible credential')
        if path.suffix.lower() == '.json':
            if name not in PUBLIC_JSON:
                errors.append(f'{name}: unreviewed configuration')
            errors.extend(inspect_json(json.loads(raw), name))
    return errors


def main():
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True)
    if result.returncode:
        raise SystemExit('Run this check in the clean public Git checkout.')
    paths = result.stdout.decode().strip('\0').split('\0')
    paths = [p for p in paths if p]
    errors = check(paths)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f'Public-file audit passed ({len(paths)} tracked files).')


if __name__ == '__main__':
    main()
