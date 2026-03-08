# another-notepad-clone
Pure 100% vibe coded, AI generated python PySide6 Notepad clone
Created with Claude Sonnet 4.6
It has:

Editing

    Unlimited tabbed documents
    Full undo/redo per tab
    Find / Find Next / Find Previous
    Find & Replace with Replace All
    Go To Line
    Select All, Cut, Copy, Paste, Delete
    Insert Time/Date (F5)
    Word wrap toggle
    Middle-click to close tab

Spell Check

    Red squiggly underlines
    Right-click suggestions (up to 8)
    Add to personal dictionary (persists)
    Requires pip install pyspellchecker

Formula Calculator

    Auto-evaluate on = keypress (toggleable)
    Ctrl+E to evaluate all / selection
    Named variables (x = 5+3)
    Colon syntax (area: w*h)
    Full math functions (sqrt, sin, cos, tan, log, exp, abs…)
    ! Warning: log is natural log. use log10 for base-10 log
    Constants: pi, e
    Variable inspector & clear

Files & Session

    Open / Save / Save As / Save All
    Export to PDF (preserves font & theme)
    Autosave with configurable interval
    Session restore — all tabs reopen on next launch
    Recent files list (up to 20, keyboard accessible)
    Reopen closed tabs (Ctrl+Shift+T + history menu)
    New Window
    Command-line / double-click file opening

Appearance

    Light and Dark themes
    Any system font (searchable picker with live preview)
    Custom fonts via %APPDATA%\EnhancedNotepad\fonts\
    Font size 6–96pt
    Zoom in/out (Ctrl+=/−, RMB + scroll wheel)
    Reset zoom (Ctrl+0)
    Line numbers
    Syntax highlighting (Off / Code / Text)
    Fullscreen — F11, Esc to exit

Split View

    Ctrl+Shift+2 or View menu
    Pick any tab to show alongside current
    Both panes fully editable, shared live document
    Draggable divider

Status Bar

    Line & column
    Character count
    Word count
    Selection count (chars + words)
    Spell check indicator

Navigation

    Ctrl+Tab / Ctrl+Shift+Tab between tabs
    Up/Down boundary teleport
    Middle-click close

Storage

    All config, session, dictionary, fonts → %APPDATA%\EnhancedNotepad\
    Exe can live anywhere

Pull requests are much appreciated.
