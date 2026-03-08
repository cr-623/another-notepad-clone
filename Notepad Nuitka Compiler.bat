@echo off
REM Requires nuitka installed and notepad.ico in the same directory
python -m nuitka --onefile --enable-plugin=pyside6 --windows-icon-from-ico=notepad.ico --windows-console-mode=disable --include-data-files=notepad.ico=notepad.ico --output-filename=Notepad+++++ --lto=yes "Notepad Clone - PySide6 edition.pyw"
pause
