# Yet another notepad clone
**Pure 100% vibe coded, AI generated Python PySide6 Notepad clone** *Created with Claude 3.5 Sonnet / 3.7 Sonnet*

![Main Interface](example%20screenshots/main%20interface.png)

## Key Features

###  Editing & Navigation
* **Unlimited tabbed documents** with middle-click to close.
* **Full undo/redo** per tab.
* **Navigation:** Ctrl+Tab / Ctrl+Shift+Tab switching, Up/Down boundary teleport.
* **Standard Tools:** Find/Replace (Next/Previous), Go To Line, Insert Time/Date (F5).

###  Appearance & UI
* **Themes:** Light and Dark mode toggle.
* **Fonts:** Any system font with a searchable picker and live preview. 
* **Fullscreen:** F11 for focus mode, Esc to exit.
![Fullscreen Mode](example%20screenshots/Fullscreen.png)
* **Customization:** Font size 6–96pt, Zoom in/out (Ctrl+Plus/Minus or Scroll wheel).
* **Line Numbers & Highlighting:** Supports "Off", "Code", and "Text" modes.
![Syntax Highlighting](example%20screenshots/Code%20highlighting.png)
![Text Highlighting](example%20screenshots/Text%20highlighting.png)

###  Formula Calculator
* **Live Evaluation:** Auto-evaluate on `=` keypress.
* **Ctrl+E** to evaluate selection or all.
* **Math:** Supports variables (`x = 5+3`), constants (`pi`, `e`), and functions (`sqrt`, `sin`, `log10`, etc.).
* **WARNING:** Log is natural log, use log10 for base-10 log
* **Variable Inspector:** Keep track of your defined variables.

###  Spell Check
* **Visual Feedback:** Red squiggly underlines for typos.
* **Smart Suggestions:** Right-click suggestions (up to 8).
* **Personal Dictionary:** Add words that persist across sessions.
* *Requires:* `pip install pyspellchecker`
* **WARNING:** Does not work after compiled with nuitka.
![Typo Highlighting/Spelling check](example%20screenshots/Unfortunately%20thicc%20is%20not%20a%20word.png)

###  Split View Mode
* **Dual Editing:** Show any tab alongside your current one (Ctrl+Shift+2).
* **Live Sync:** Both panes are fully editable and share the same live document.
* **Adjustable:** Draggable divider to set your preferred width.
![Split View](example%20screenshots/Split%20view%20mode.png)

###  Files & Session
* **Session Restore:** All tabs reopen exactly where you left them on next launch.
* **Recent Files:** Access up to 20 recent documents via keyboard.
* **Reopen Closed Tabs:** Ctrl+Shift+T to rescue accidentally closed work.
* **Export:** Professional PDF export that preserves your font and theme.

###  Technical Details
* **Storage:** All config, session data, and dictionaries are stored in `%APPDATA%\EnhancedNotepad\`.
* **Portable:** The compiled EXE can run from anywhere.
* **Ligature Support:** Looks great with coding fonts like Cascadia Code.
![Ligatures](example%20screenshots/Cascadia%20code%20ligatures.png)

---
*Pull requests are much appreciated.
