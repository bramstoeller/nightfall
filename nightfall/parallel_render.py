"""Independent Qt render processes with bounded, ordered RGB frame buffers.

Each worker owns its QApplication and effect caches. A temporary mmap avoids
pickling megabytes of pixels through pipes; only frame numbers cross the pipes.
The spawn context and file-backed mmap work on Windows as well as Linux.
"""
import mmap
import multiprocessing as mp
from multiprocessing.connection import wait
import os
from pathlib import Path
import tempfile
import traceback

from .model import WIDTH, HEIGHT

FRAME_BYTES = WIDTH * HEIGHT * 3


def default_workers():
    count = getattr(os, 'process_cpu_count', os.cpu_count)() or 1
    # Each Qt worker holds sprites, smoke fields and a 64 MB brightness table.
    # Keep older laptops responsive even when they report many logical CPUs.
    memory = available_memory_mb()
    limit = 1 if memory is None or memory < 2048 else 2
    return min(limit, max(1, count // 2))


def available_memory_mb():
    """Available RAM without requiring an extra runtime dependency."""
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD),
                            *[(name, ctypes.c_ulonglong) for name in
                              ['total', 'available', 'page_total', 'page_available',
                               'virtual_total', 'virtual_available', 'extended']]]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.available // (1024 * 1024)
        else:
            return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') // (1024 * 1024)
    except (AttributeError, OSError, ValueError):
        pass
    return None


def _worker(data, filename, commands, results):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    buffer = None
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QImage
        from .renderer import render
        app = QApplication.instance() or QApplication([])
        with open(filename, 'r+b') as handle:
            buffer = mmap.mmap(handle.fileno(), 0)
            while True:
                try:
                    job = commands.recv()
                except EOFError:
                    break
                if job is None:
                    break
                index, slot, t, show = job
                image = render(data, t, show).convertToFormat(QImage.Format_RGB888)
                offset = slot * FRAME_BYTES
                buffer[offset:offset + FRAME_BYTES] = image.constBits()
                results.send((index, None))
    except BaseException:
        try:
            results.send((-1, traceback.format_exc()))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        if buffer is not None:
            buffer.close()
        commands.close()
        results.close()


class FrameRenderer:
    def __init__(self, data, workers=None):
        self.data = data
        self.workers = default_workers() if workers is None else workers
        if not 1 <= self.workers <= 32:
            raise ValueError('Render worker count must be between 1 and 32.')
        self.children = []
        self.buffer = None
        self.directory = None

    def __enter__(self):
        if self.workers == 1:
            return self
        try:
            self.directory = tempfile.TemporaryDirectory(prefix='nightfall-frames-')
            filename = Path(self.directory.name) / 'frames.rgb'
            with filename.open('w+b') as handle:
                handle.truncate(self.workers * 2 * FRAME_BYTES)
                self.buffer = mmap.mmap(handle.fileno(), 0)
            # The photos can be tens of MB; animation never reads them.
            data = {k: v for k, v in self.data.items()
                    if k not in ('reference', 'reference_photos')}
            context = mp.get_context('spawn')
            for i in range(self.workers):
                command_in, command_out = context.Pipe(duplex=False)
                result_in, result_out = context.Pipe(duplex=False)
                process = context.Process(target=_worker,
                    args=(data, str(filename), command_in, result_out),
                    name=f'Nightfall-render-{i + 1}', daemon=True)
                try:
                    process.start()
                    self.children.append((process, command_out, result_in))
                except BaseException:
                    command_out.close()
                    result_in.close()
                    raise
                finally:
                    command_in.close()
                    result_out.close()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def frames(self, show, count, fps, start=0, check_cancel=lambda: None):
        if self.workers == 1:
            from PySide6.QtGui import QImage
            from .renderer import render
            for i in range(count):
                check_cancel()
                image = render(self.data, start + i / fps, show).convertToFormat(QImage.Format_RGB888)
                yield bytes(image.constBits())
            return

        slots = self.workers * 2

        def dispatch(i):
            self.children[i % self.workers][1].send((i, i % slots, start + i / fps, show))

        submitted = min(count, slots)
        for i in range(submitted):
            check_cancel()
            dispatch(i)
        completed = set()
        next_frame = 0
        readers = [r for _, _, r in self.children]
        while next_frame < count:
            check_cancel()
            if next_frame in completed:
                completed.remove(next_frame)
                offset = (next_frame % slots) * FRAME_BYTES
                # A bounded copy keeps mmap lifetime independent of the caller.
                yield self.buffer[offset:offset + FRAME_BYTES]
                check_cancel()
                next_frame += 1
                if submitted < count:
                    dispatch(submitted)
                    submitted += 1
                continue
            for reader in wait(readers, timeout=.05):
                try:
                    index, error = reader.recv()
                except (EOFError, OSError) as exc:
                    raise RuntimeError('A render worker stopped unexpectedly.') from exc
                if error:
                    raise RuntimeError('Render worker failed:\n' + error)
                completed.add(index)

    def __exit__(self, exc_type, exc_value, tb):
        # On cancellation kill busy workers immediately, then reap every child.
        for process, commands, results in self.children:
            if process.is_alive():
                process.terminate()
        for process, commands, results in self.children:
            process.join()
            process.close()
            commands.close()
            results.close()
        self.children.clear()
        if self.buffer is not None:
            self.buffer.close()
            self.buffer = None
        if self.directory is not None:
            self.directory.cleanup()
            self.directory = None
