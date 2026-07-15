import os
import sys

if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(app_dir)
