@echo off
REM Requires nuitka and pyspellchecker installed and notepad.ico in the same directory
python -m nuitka --onefile --enable-plugin=pyside6 --windows-icon-from-ico=notepad.ico --windows-console-mode=disable --include-data-files=notepad.ico=notepad.ico --include-package-data=spellchecker --output-filename=Notepad+++++ --lto=yes "Notepad Clone - PySide6 edition.pyw"
REM For every major update, it is crucial to add another "+" at the end of the app
pause
