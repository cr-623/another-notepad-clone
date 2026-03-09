@echo off
python -m nuitka --onefile --enable-plugin=pyqt6 --windows-icon-from-ico=notepad.ico --windows-console-mode=disable --include-data-files=notepad.ico=notepad.ico --output-filename=Notepad++++ --lto=yes "Notepad Premium++ (PyQt6 edition).pyw"
pause