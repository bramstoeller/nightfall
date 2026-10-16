"""Desktop and offline renderer entry point."""
import os
import sys
from multiprocessing import freeze_support


def main():
    freeze_support()
    rules = os.environ.get('QT_LOGGING_RULES', '')
    os.environ['QT_LOGGING_RULES'] = ';'.join(filter(None, [rules,
        'qt.qpa.wayland.textinput.debug=false;qt.qpa.wayland.textinput.info=false;qt.qpa.wayland.textinput.warning=false']))
    if '--render' in sys.argv:
        sys.argv.remove('--render')
        from nightfall.export import run
        run()
    elif '--smoke-test' in sys.argv:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from nightfall.smoke_test import main as check
        check()
    else:
        from nightfall.gui import main as desktop
        desktop()


if __name__ == '__main__':
    main()
