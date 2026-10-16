"""Launch the renderer from source or a packaged executable."""
import sys
from .model import ROOT


def render_command(*args):
    prefix = ['--render'] if getattr(sys, 'frozen', False) else [str(ROOT/'calibrate.py'), '--render']
    return prefix + [str(arg) for arg in args]
