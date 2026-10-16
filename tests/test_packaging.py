"""Windows media packaging and conservative render resource limits."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from nightfall.parallel_render import default_workers
from tools.build import bundle_windows_media
from tools.fetch_windows_ffmpeg import unpack


class PackagingTests(unittest.TestCase):
    def test_media_archive_contains_only_needed_tools_and_original_notices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'provider.zip';destination=root/'media'
            with ZipFile(archive,'w') as package:
                for name in ['bin/ffmpeg.exe','bin/ffprobe.exe','LICENSE','README.txt','bin/ffplay.exe']:
                    package.writestr('ffmpeg-test/'+name,name.encode())
            unpack(archive,destination)
            self.assertTrue((destination/'bin/ffmpeg.exe').is_file())
            self.assertFalse((destination/'bin/ffplay.exe').exists())
            with patch('tools.build.subprocess.check_output',return_value=' V....D libx264  H.264 encoder'),patch('tools.build.subprocess.run'):
                bundle_windows_media(destination/'bin',root/'app')
            self.assertEqual((root/'app/bin/ffprobe.exe').read_bytes(),b'bin/ffprobe.exe')
            self.assertTrue((root/'app/licenses/ffmpeg/LICENSE').is_file())
            self.assertTrue((root/'app/licenses/ffmpeg/PROVENANCE.txt').is_file())

    def test_windows_build_rejects_missing_media_and_missing_encoder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source/bin';source.mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):bundle_windows_media(source,root/'app')
            for name in ['ffmpeg.exe','ffprobe.exe']:(source/name).write_bytes(b'MZ')
            (source.parent/'LICENSE').write_text('provider license')
            with patch('tools.build.subprocess.check_output',return_value=' V..... mpeg4 '):
                with self.assertRaisesRegex(RuntimeError,'libx264'):bundle_windows_media(source,root/'app')
            self.assertFalse((root/'app').exists())

    def test_render_workers_respect_cpu_and_memory_limits(self):
        for cpus,memory,expected in [(1,8192,1),(2,8192,1),(4,8192,2),(32,8192,2),(32,1024,1),(32,None,1)]:
            with self.subTest(cpus=cpus,memory=memory),patch('nightfall.parallel_render.os.process_cpu_count',return_value=cpus),patch('nightfall.parallel_render.available_memory_mb',return_value=memory):
                self.assertEqual(default_workers(),expected)
