Qt / Qt for Python dependency notices
====================================

This application dynamically loads the unmodified Qt for Python 6.11.2
PySide6-Essentials and shiboken6 binary distributions. Their installed wheel
metadata declares LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only, but those
wheel notice directories contain only LicenseRef-Qt-Commercial.txt. The
LGPL-3.0 text and the GPL-3.0 text referenced by it are therefore included
here separately from the installed wheel notices.

These notices describe the Qt dependencies. They do not assign a new
license to the user's application code or to model weights.

Sources, consulted 2026-09-07:
- https://doc.qt.io/qtforpython-6/licenses.html
- https://www.gnu.org/licenses/lgpl-3.0.txt
- https://www.gnu.org/licenses/gpl-3.0.txt

Qt for Python source:
- https://code.qt.io/cgit/pyside/pyside-setup.git/
- https://download.qt.io/official_releases/QtForPython/

The GUI's Qt DLLs and plugins are installed under _internal/PySide6.
The onedir bundle keeps them separate and replaceable rather than statically
linking them into the application executable.
