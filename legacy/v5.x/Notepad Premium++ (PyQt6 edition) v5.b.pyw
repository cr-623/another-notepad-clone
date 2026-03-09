import sys
import os
import json
import re
import ast
import operator
import math
import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Tuple, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QFileDialog, QMessageBox,
    QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QTabWidget, QWidget, QStatusBar, QMenu,
    QMenuBar, QSpinBox, QDialogButtonBox, QFontComboBox
)
from PyQt6.QtGui import (
    QFont, QFontDatabase, QAction, QKeySequence, QIcon, QTextCursor, QTextCharFormat,
    QColor, QPalette, QSyntaxHighlighter, QTextDocument, QActionGroup
)
from PyQt6.QtCore import Qt, QRegularExpression, pyqtSignal, QTimer

# Constants
ICON_PATH = "notepad.ico"
PREFS_FILE = "notepad_prefs.json"
SESSION_FILE = "notepad_session.json"


@dataclass
class Preferences:
    """User preferences for the application."""
    font_size: int = 11
    word_wrap: bool = True
    status_bar: bool = False
    recent_files: list = None
    theme: str = "light"
    font_family: str = ""
    line_numbers: bool = False
    highlight_syntax: str = "off"  # "code", "text", "off"
    max_recent_files: int = 10
    autosave_enabled: bool = True
    autosave_interval: int = 60  # seconds
    restore_session: bool = True
    
    def __post_init__(self):
        if self.recent_files is None:
            self.recent_files = []


@dataclass
class TabSession:
    """Session data for a single tab."""
    content: str
    current_file: Optional[str] = None
    cursor_position: int = 0
    scroll_position: int = 0


@dataclass
class AppSession:
    """Session data for the entire application."""
    tabs: List[TabSession] = None
    active_tab_index: int = 0
    
    def __post_init__(self):
        if self.tabs is None:
            self.tabs = []


class SafeExpressionEvaluator:
    """Safely evaluates mathematical expressions without arbitrary code execution."""
    
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    SAFE_FUNCTIONS = {
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'sum': sum,
        'pow': pow,
        'sqrt': math.sqrt,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'log': math.log,
        'log10': math.log10,
        'exp': math.exp,
        'pi': math.pi,
        'e': math.e,
    }
    
    def __init__(self):
        self.variables = {}
    
    def clear_variables(self):
        """Clear all stored variables."""
        self.variables = {}
    
    def _eval_node(self, node):
        """Recursively evaluate an AST node."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Name):
            if node.id in self.variables:
                return self.variables[node.id]
            elif node.id in self.SAFE_FUNCTIONS:
                return self.SAFE_FUNCTIONS[node.id]
            else:
                raise NameError(f"Variable '{node.id}' is not defined")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Operator {op_type.__name__} is not allowed")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return self.SAFE_OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Operator {op_type.__name__} is not allowed")
            operand = self._eval_node(node.operand)
            return self.SAFE_OPERATORS[op_type](operand)
        elif isinstance(node, ast.Call):
            func = self._eval_node(node.func)
            args = [self._eval_node(arg) for arg in node.args]
            return func(*args)
        elif isinstance(node, ast.List):
            return [self._eval_node(elem) for elem in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elem) for elem in node.elts)
        else:
            raise ValueError(f"Unsupported operation: {type(node).__name__}")
    
    def evaluate(self, expression: str) -> Tuple[bool, Optional[float], Optional[str]]:
        """Safely evaluate a mathematical expression."""
        try:
            tree = ast.parse(expression, mode='eval')
            result = self._eval_node(tree.body)
            return True, result, None
        except (SyntaxError, ValueError, NameError, TypeError, ZeroDivisionError) as e:
            return False, None, str(e)


class SyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for code and text modes."""
    
    def __init__(self, document, mode="off", theme="light"):
        super().__init__(document)
        self.mode = mode
        self.theme = theme
        self.setup_formats()
    
    def setup_formats(self):
        """Set up text formats based on mode and theme."""
        self.formats = {}
        
        if self.mode == "off":
            return
        
        if self.mode == "code":
            if self.theme == "dark":
                colors = {
                    'number': '#445ad4', 'variable': '#e06c75', 'operator': '#44ccd4',
                    'string': '#21ad4d', 'function': '#ffeb3b', 'bracket': '#1400eb',
                    'bracket_text': '#7da8ff', 'bracket_err': ('#ef4444', '#ffffff'),
                    'punct': '#484848'
                }
            else:
                colors = {
                    'number': '#445ad4', 'variable': '#e06c75', 'operator': '#44ccd4',
                    'string': '#21ad4d', 'function': '#ffeb3b', 'bracket': '#1400eb',
                    'bracket_text': '#7da8ff', 'bracket_err': ('#ef4444', '#ffffff'),
                    'punct': '#484848'
                }
        else:  # text mode
            colors = {
                'number': '#898989', 'variable': '#484848', 'operator': '#898989',
                'string': '#b3b3b3', 'function': '#484848', 'bracket': '#000000',
                'bracket_text': '#000000', 'bracket_err': ('#000000', '#ffffff'),
                'punct': '#000000'
            }
        
        for name, color in colors.items():
            fmt = QTextCharFormat()
            if isinstance(color, tuple):
                fmt.setBackground(QColor(color[0]))
                fmt.setForeground(QColor(color[1]))
            else:
                fmt.setForeground(QColor(color))
            self.formats[name] = fmt
    
    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text."""
        if self.mode == "off":
            return
        
        number_pattern = QRegularExpression(r'\b\d+\.?\d*([eE][+-]?\d+)?\b')
        iterator = number_pattern.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(),
                          self.formats.get('number', QTextCharFormat()))
        
        for pattern in [r'"[^"]*"', r"'[^']*'"]:
            string_pattern = QRegularExpression(pattern)
            iterator = string_pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(),
                              self.formats.get('string', QTextCharFormat()))
        
        operator_pattern = QRegularExpression(r'[\+\-\*\/\=\%\^]')
        iterator = operator_pattern.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(),
                          self.formats.get('operator', QTextCharFormat()))
        
        punct_pattern = QRegularExpression(r'[\,\!\:\;\&\.]')
        iterator = punct_pattern.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(),
                          self.formats.get('punct', QTextCharFormat()))
        
        func_pattern = QRegularExpression(r'\b[a-zA-Z_][a-zA-Z0-9_]*(?=\()')
        iterator = func_pattern.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            self.setFormat(match.capturedStart(), match.capturedLength(),
                          self.formats.get('function', QTextCharFormat()))
        
        var_pattern = QRegularExpression(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b')
        iterator = var_pattern.globalMatch(text)
        while iterator.hasNext():
            match = iterator.next()
            if self.format(match.capturedStart()) == QTextCharFormat():
                self.setFormat(match.capturedStart(), match.capturedLength(),
                              self.formats.get('variable', QTextCharFormat()))
        
        self.highlight_brackets(text)
    
    def highlight_brackets(self, text):
        stack = []
        pairs = {')': '(', ']': '[', '}': '{'}
        for i, char in enumerate(text):
            if char in '([{':
                stack.append((char, i))
            elif char in ')]}':
                if stack and stack[-1][0] == pairs[char]:
                    open_char, open_pos = stack.pop()
                    self.setFormat(open_pos, 1, self.formats.get('bracket', QTextCharFormat()))
                    self.setFormat(i, 1, self.formats.get('bracket', QTextCharFormat()))
                else:
                    self.setFormat(i, 1, self.formats.get('bracket_err', QTextCharFormat()))
        for char, pos in stack:
            self.setFormat(pos, 1, self.formats.get('bracket_err', QTextCharFormat()))
    
    def set_mode(self, mode):
        self.mode = mode
        self.setup_formats()
        self.rehighlight()
    
    def set_theme(self, theme):
        self.theme = theme
        self.setup_formats()
        self.rehighlight()


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        
    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(self.editor.line_number_area_width(), 0)
    
    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QTextEdit):
    """Text editor with line numbers, auto-evaluation, and boundary navigation."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.show_line_numbers = False
        self.highlighter = None
        self.current_theme = "light"
        self._notepad_app = None  # Reference to NotepadApp for auto-evaluation
        
        self.document().blockCountChanged.connect(self.update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(self.update_line_number_area)
        self.textChanged.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.update_line_number_area)
        
        self.update_line_number_area_width(0)
    
    def line_number_area_width(self):
        if not self.show_line_numbers:
            return 0
        digits = len(str(max(1, self.document().blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
    
    def update_line_number_area(self, *args):
        self.line_number_area.update()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(0, cr.top(), self.line_number_area_width(), cr.height())
    
    def line_number_area_paint_event(self, event):
        from PyQt6.QtGui import QPainter
        if not self.show_line_numbers:
            return
        try:
            painter = QPainter(self.line_number_area)
            if self.current_theme == "dark":
                bg_color = QColor("#252526")
                fg_color = QColor("#858585")
            else:
                bg_color = QColor("#f0f0f0")
                fg_color = QColor("#666666")
            painter.fillRect(event.rect(), bg_color)
            block = self.firstVisibleBlock()
            if not block.isValid():
                return
            block_number = block.blockNumber()
            top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
            bottom = top + int(self.blockBoundingRect(block).height())
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    number = str(block_number + 1)
                    painter.setPen(fg_color)
                    painter.drawText(0, top, self.line_number_area.width() - 5,
                                   self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, number)
                block = block.next()
                top = bottom
                bottom = top + int(self.blockBoundingRect(block).height())
                block_number += 1
            painter.end()
        except Exception as e:
            print(f"Line number painting error: {e}")
    
    def set_line_numbers_visible(self, visible):
        self.show_line_numbers = visible
        if visible:
            self.line_number_area.show()
        else:
            self.line_number_area.hide()
        self.update_line_number_area_width(0)
        self.line_number_area.update()
    
    def set_syntax_highlighting(self, mode, theme="light"):
        if mode == "off":
            if self.highlighter:
                self.highlighter.setDocument(None)
                self.highlighter = None
        else:
            if self.highlighter:
                self.highlighter.set_mode(mode)
                self.highlighter.set_theme(theme)
            else:
                self.highlighter = SyntaxHighlighter(self.document(), mode, theme)
    
    def update_syntax_theme(self, theme):
        if self.highlighter:
            self.highlighter.set_theme(theme)

    def keyPressEvent(self, event):
        """Handle Up/Down boundary teleport, then auto-evaluate on '='."""
        key = event.key()
        modifiers = event.modifiers()

        # Up arrow on first line → jump to start of that line
        if key == Qt.Key.Key_Up and modifiers == Qt.KeyboardModifier.NoModifier:
            cursor = self.textCursor()
            if cursor.blockNumber() == 0:
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                self.setTextCursor(cursor)
                return

        # Down arrow on last line → jump to end of that line
        if key == Qt.Key.Key_Down and modifiers == Qt.KeyboardModifier.NoModifier:
            cursor = self.textCursor()
            last_block = self.document().blockCount() - 1
            if cursor.blockNumber() == last_block:
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                self.setTextCursor(cursor)
                return

        # Let the base class handle the key
        super().keyPressEvent(event)

        # After '=' is inserted, auto-evaluate the current line
        if key == Qt.Key.Key_Equal and modifiers == Qt.KeyboardModifier.NoModifier:
            if self._notepad_app is not None:
                cursor = self.textCursor()
                block_text = cursor.block().text()
                if block_text.rstrip().endswith('='):
                    self._notepad_app._evaluate_current_line()


@dataclass
class TabData:
    """Data structure to hold information about each tab."""
    text_widget: CodeEditor
    current_file: Optional[str] = None
    modified: bool = False
    evaluator: SafeExpressionEvaluator = None
    last_saved_content: str = ""
    
    def __post_init__(self):
        if self.evaluator is None:
            self.evaluator = SafeExpressionEvaluator()


class FindDialog(QDialog):
    def __init__(self, parent, text_widget, app):
        super().__init__(parent)
        self.text_widget = text_widget
        self.app = app
        self.setWindowTitle("Find")
        self.setModal(False)
        self.resize(400, 120)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Find what:"))
        self.search_entry = QLineEdit()
        self.search_entry.setText(self.app.last_find_term)
        self.search_entry.selectAll()
        search_layout.addWidget(self.search_entry)
        find_btn = QPushButton("Find Next")
        find_btn.clicked.connect(self.find_next)
        search_layout.addWidget(find_btn)
        layout.addLayout(search_layout)
        options_layout = QHBoxLayout()
        self.match_case_cb = QCheckBox("Match case")
        self.match_case_cb.setChecked(self.app.last_find_case_sensitive)
        options_layout.addWidget(self.match_case_cb)
        options_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        options_layout.addWidget(cancel_btn)
        layout.addLayout(options_layout)
        self.setLayout(layout)
        self.search_entry.returnPressed.connect(self.find_next)
        self.search_entry.setFocus()
    
    def find_next(self):
        search_term = self.search_entry.text()
        if not search_term:
            return
        self.app.last_find_term = search_term
        self.app.last_find_case_sensitive = self.match_case_cb.isChecked()
        flags = QTextDocument.FindFlag(0)
        if self.match_case_cb.isChecked():
            flags = QTextDocument.FindFlag.FindCaseSensitively
        cursor = self.text_widget.textCursor()
        found_cursor = self.text_widget.document().find(search_term, cursor, flags)
        if found_cursor.isNull():
            found_cursor = self.text_widget.document().find(search_term, 0, flags)
            if found_cursor.isNull():
                QMessageBox.information(self, "Find", f'Cannot find "{search_term}"')
                return
        self.text_widget.setTextCursor(found_cursor)


class ReplaceDialog(QDialog):
    def __init__(self, parent, text_widget):
        super().__init__(parent)
        self.text_widget = text_widget
        self.setWindowTitle("Replace")
        self.setModal(False)
        self.resize(400, 150)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        layout = QVBoxLayout()
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("Find what:"))
        self.find_entry = QLineEdit()
        find_layout.addWidget(self.find_entry)
        find_btn = QPushButton("Find Next")
        find_btn.clicked.connect(self.find_next)
        find_layout.addWidget(find_btn)
        layout.addLayout(find_layout)
        replace_layout = QHBoxLayout()
        replace_layout.addWidget(QLabel("Replace with:"))
        self.replace_entry = QLineEdit()
        replace_layout.addWidget(self.replace_entry)
        replace_btn = QPushButton("Replace")
        replace_btn.clicked.connect(self.replace)
        replace_layout.addWidget(replace_btn)
        layout.addLayout(replace_layout)
        options_layout = QHBoxLayout()
        self.match_case_cb = QCheckBox("Match case")
        options_layout.addWidget(self.match_case_cb)
        options_layout.addStretch()
        replace_all_btn = QPushButton("Replace All")
        replace_all_btn.clicked.connect(self.replace_all)
        options_layout.addWidget(replace_all_btn)
        layout.addLayout(options_layout)
        self.setLayout(layout)
        self.find_entry.returnPressed.connect(self.find_next)
        self.find_entry.setFocus()
    
    def find_next(self):
        search_term = self.find_entry.text()
        if not search_term:
            return
        flags = QTextDocument.FindFlag(0)
        if self.match_case_cb.isChecked():
            flags = QTextDocument.FindFlag.FindCaseSensitively
        cursor = self.text_widget.textCursor()
        found_cursor = self.text_widget.document().find(search_term, cursor, flags)
        if found_cursor.isNull():
            QMessageBox.information(self, "Replace", f'Cannot find "{search_term}"')
        else:
            self.text_widget.setTextCursor(found_cursor)
    
    def replace(self):
        cursor = self.text_widget.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_entry.text())
            self.find_next()
    
    def replace_all(self):
        search_term = self.find_entry.text()
        replace_term = self.replace_entry.text()
        if not search_term:
            return
        count = 0
        cursor = QTextCursor(self.text_widget.document())
        cursor.beginEditBlock()
        flags = QTextDocument.FindFlag(0)
        if self.match_case_cb.isChecked():
            flags = QTextDocument.FindFlag.FindCaseSensitively
        while True:
            cursor = self.text_widget.document().find(search_term, cursor, flags)
            if cursor.isNull():
                break
            cursor.insertText(replace_term)
            count += 1
        cursor.endEditBlock()
        QMessageBox.information(self, "Replace All", f"Replaced {count} occurrence(s)")

def load_bundled_fonts():
    """Load fonts from fonts/ folder next to the script."""
    loaded = []
    font_dir = Path(__file__).parent / "fonts"
    if not font_dir.exists():
        return loaded
    for ext in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
        for font_file in font_dir.glob(ext):
            fid = QFontDatabase.addApplicationFont(str(font_file))
            if fid != -1:
                families = QFontDatabase.applicationFontFamilies(fid)
                loaded.extend(families)
                print(f"Loaded: {font_file.name} → {families}")
            else:
                print(f"Failed: {font_file.name}")
    return loaded


def resolve_font_family(preferred: str) -> str:
    """Pick best available font, falling back gracefully."""
    preferred_order = [
        "Cascadia Mono",
        "JetBrains Mono",
        "Comic Neue",
        "Playfair Display"
    ]
    available = QFontDatabase.families()
    # Honour saved preference if still available
    if preferred and preferred in available:
        return preferred
    # Otherwise pick best from list
    for family in preferred_order:
        if family in available:
            return family
    return ""

class NotepadApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.loaded_font_families = load_bundled_fonts()
        self.preferences = self._load_preferences()
        self.active_font_family = resolve_font_family(self.preferences.font_family)  # ← add
        self.current_font_size = self.preferences.font_size
        self.highlight_syntax = self.preferences.highlight_syntax
        self.last_find_term = ""
        self.last_find_case_sensitive = False
        self.tabs: Dict[int, TabData] = {}
        self.tab_counter = 0
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self._autosave_all)
        if self.preferences.autosave_enabled:
            self.autosave_timer.start(self.preferences.autosave_interval * 1000)
        self._init_ui()
        self._create_menus()
        self._setup_shortcuts()
        self._apply_theme(self.preferences.theme)
        if self.preferences.restore_session:
            if not self._restore_session():
                self._new_tab()
        else:
            self._new_tab()
        self._apply_preferences()
        self.setWindowTitle("Untitled - Enhanced Notepad")
        self.resize(800, 600)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
    
    def _init_ui(self):
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab_by_index)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabBar().installEventFilter(self)
        self.setCentralWidget(self.tab_widget)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.hide()
    
    def eventFilter(self, obj, event):
        if obj == self.tab_widget.tabBar():
            if event.type() == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.MiddleButton:
                    index = self.tab_widget.tabBar().tabAt(event.pos())
                    if index >= 0:
                        self._close_tab_by_index(index)
                        return True
        return super().eventFilter(obj, event)
    
    def _create_menus(self):
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("&File")
        new_tab_action = QAction("New &Tab", self)
        new_tab_action.setShortcut(QKeySequence("Ctrl+T"))
        new_tab_action.triggered.connect(lambda: self._new_tab())
        file_menu.addAction(new_tab_action)
        new_window_action = QAction("New &Window", self)
        new_window_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_window_action.triggered.connect(self.new_window)
        file_menu.addAction(new_window_action)
        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        self.recent_menu = QMenu("&Recent Files", self)
        file_menu.addMenu(self.recent_menu)
        self._update_recent_files_menu()
        file_menu.addSeparator()
        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(lambda: self._save_file())
        file_menu.addAction(save_action)
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(lambda: self._save_file_as())
        file_menu.addAction(save_as_action)
        save_all_action = QAction("Save A&ll", self)
        save_all_action.triggered.connect(self._save_all)
        file_menu.addAction(save_all_action)
        file_menu.addSeparator()
        autosave_menu = file_menu.addMenu("&Autosave")
        self.autosave_enabled_action = QAction("&Enable Autosave", self)
        self.autosave_enabled_action.setCheckable(True)
        self.autosave_enabled_action.setChecked(self.preferences.autosave_enabled)
        self.autosave_enabled_action.triggered.connect(self._toggle_autosave)
        autosave_menu.addAction(self.autosave_enabled_action)
        autosave_settings_action = QAction("Autosave &Settings...", self)
        autosave_settings_action.triggered.connect(self._autosave_settings)
        autosave_menu.addAction(autosave_settings_action)
        autosave_menu.addSeparator()
        autosave_now_action = QAction("Save &Now", self)
        autosave_now_action.setShortcut(QKeySequence("Ctrl+Alt+S"))
        autosave_now_action.triggered.connect(self._autosave_all)
        autosave_menu.addAction(autosave_now_action)
        file_menu.addSeparator()
        close_tab_action = QAction("&Close Tab", self)
        close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
        close_tab_action.triggered.connect(lambda: self._close_tab())
        file_menu.addAction(close_tab_action)
        close_all_action = QAction("Close &All Tabs", self)
        close_all_action.triggered.connect(self._close_all_tabs)
        file_menu.addAction(close_all_action)
        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)
        edit_menu.addSeparator()
        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        cut_action.triggered.connect(self._cut)
        edit_menu.addAction(cut_action)
        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self._copy)
        edit_menu.addAction(copy_action)
        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.triggered.connect(self._paste)
        edit_menu.addAction(paste_action)
        delete_action = QAction("&Delete", self)
        delete_action.setShortcut(QKeySequence("Del"))
        delete_action.triggered.connect(self._delete)
        edit_menu.addAction(delete_action)
        edit_menu.addSeparator()
        find_action = QAction("&Find...", self)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self._find_dialog)
        edit_menu.addAction(find_action)
        find_next_action = QAction("Find &Next", self)
        find_next_action.setShortcut(QKeySequence("F3"))
        find_next_action.triggered.connect(self._find_next)
        edit_menu.addAction(find_next_action)
        find_prev_action = QAction("Find &Previous", self)
        find_prev_action.setShortcut(QKeySequence("Shift+F3"))
        find_prev_action.triggered.connect(self._find_prev)
        edit_menu.addAction(find_prev_action)
        replace_action = QAction("&Replace...", self)
        replace_action.setShortcut(QKeySequence.StandardKey.Replace)
        replace_action.triggered.connect(self._replace_dialog)
        edit_menu.addAction(replace_action)
        goto_action = QAction("&Go To...", self)
        goto_action.setShortcut(QKeySequence("Ctrl+G"))
        goto_action.triggered.connect(self._goto_line)
        edit_menu.addAction(goto_action)
        edit_menu.addSeparator()
        select_all_action = QAction("Select &All", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self._select_all)
        edit_menu.addAction(select_all_action)
        time_date_action = QAction("&Time/Date", self)
        time_date_action.setShortcut(QKeySequence("F5"))
        time_date_action.triggered.connect(self._insert_time_date)
        edit_menu.addAction(time_date_action)
        edit_menu.addSeparator()
        eval_action = QAction("&Evaluate Formula", self)
        eval_action.setShortcut(QKeySequence("Ctrl+E"))
        eval_action.triggered.connect(self._evaluate_formula)
        edit_menu.addAction(eval_action)
        list_vars_action = QAction("&List Variables", self)
        list_vars_action.triggered.connect(self._list_variables)
        edit_menu.addAction(list_vars_action)
        clear_vars_action = QAction("&Clear Variables", self)
        clear_vars_action.triggered.connect(self._clear_variables)
        edit_menu.addAction(clear_vars_action)
        
        # Format Menu
        format_menu = menubar.addMenu("F&ormat")
        self.word_wrap_action = QAction("&Word Wrap", self)
        self.word_wrap_action.setCheckable(True)
        self.word_wrap_action.setChecked(True)
        self.word_wrap_action.triggered.connect(self._toggle_word_wrap)
        format_menu.addAction(self.word_wrap_action)
        font_action = QAction("&Font...", self)
        font_action.triggered.connect(self._font_dialog)
        format_menu.addAction(font_action)
        
        # View Menu
        view_menu = menubar.addMenu("&View")
        zoom_menu = view_menu.addMenu("&Zoom")
        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_action.triggered.connect(self._zoom_in)
        zoom_menu.addAction(zoom_in_action)
        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_action.triggered.connect(self._zoom_out)
        zoom_menu.addAction(zoom_out_action)
        zoom_reset_action = QAction("&Restore Default Zoom", self)
        zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
        zoom_reset_action.triggered.connect(self._zoom_reset)
        zoom_menu.addAction(zoom_reset_action)
        self.status_bar_action = QAction("&Status Bar", self)
        self.status_bar_action.setCheckable(True)
        self.status_bar_action.triggered.connect(self._toggle_status_bar)
        view_menu.addAction(self.status_bar_action)
        self.line_numbers_action = QAction("&Line Numbers", self)
        self.line_numbers_action.setCheckable(True)
        self.line_numbers_action.triggered.connect(self._toggle_line_numbers)
        view_menu.addAction(self.line_numbers_action)
        theme_menu = view_menu.addMenu("&Theme")
        light_theme_action = QAction("&Light", self)
        light_theme_action.triggered.connect(lambda: self._change_theme("light"))
        theme_menu.addAction(light_theme_action)
        dark_theme_action = QAction("&Dark", self)
        dark_theme_action.triggered.connect(lambda: self._change_theme("dark"))
        theme_menu.addAction(dark_theme_action)
        view_menu.addSeparator()
        highlight_menu = view_menu.addMenu("&Highlight Syntax")
        self.highlight_action_group = QActionGroup(self)
        self.highlight_action_group.setExclusive(True)
        self.highlight_off_action = QAction("&Off", self)
        self.highlight_off_action.setCheckable(True)
        self.highlight_off_action.setActionGroup(self.highlight_action_group)
        self.highlight_off_action.triggered.connect(lambda: self._toggle_highlight_syntax("off"))
        highlight_menu.addAction(self.highlight_off_action)
        self.highlight_code_action = QAction("&Code", self)
        self.highlight_code_action.setCheckable(True)
        self.highlight_code_action.setActionGroup(self.highlight_action_group)
        self.highlight_code_action.triggered.connect(lambda: self._toggle_highlight_syntax("code"))
        highlight_menu.addAction(self.highlight_code_action)
        self.highlight_text_action = QAction("&Text", self)
        self.highlight_text_action.setCheckable(True)
        self.highlight_text_action.setActionGroup(self.highlight_action_group)
        self.highlight_text_action.triggered.connect(lambda: self._toggle_highlight_syntax("text"))
        highlight_menu.addAction(self.highlight_text_action)
        self.highlight_off_action.setChecked(True)
        view_menu.addSeparator()
        session_menu = view_menu.addMenu("&Session")
        self.restore_session_action = QAction("&Restore Session on Startup", self)
        self.restore_session_action.setCheckable(True)
        self.restore_session_action.setChecked(self.preferences.restore_session)
        self.restore_session_action.triggered.connect(self._toggle_restore_session)
        session_menu.addAction(self.restore_session_action)
        clear_session_action = QAction("&Clear Saved Session", self)
        clear_session_action.triggered.connect(self._clear_session)
        session_menu.addAction(clear_session_action)
        
        # Help Menu
        help_menu = menubar.addMenu("&Help")
        formula_help_action = QAction("&Formula Help", self)
        formula_help_action.triggered.connect(self._show_formula_help)
        help_menu.addAction(formula_help_action)
        help_menu.addSeparator()
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_shortcuts(self):
        next_tab_action = QAction(self)
        next_tab_action.setShortcut(QKeySequence("Ctrl+Tab"))
        next_tab_action.triggered.connect(self._next_tab)
        self.addAction(next_tab_action)
        prev_tab_action = QAction(self)
        prev_tab_action.setShortcut(QKeySequence("Ctrl+Shift+Tab"))
        prev_tab_action.triggered.connect(self._prev_tab)
        self.addAction(prev_tab_action)
    
    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================
    
    def _save_session(self):
        try:
            session_tabs = []
            for i in range(self.tab_widget.count()):
                tab_id = self._get_tab_id_from_index(i)
                if tab_id and tab_id in self.tabs:
                    tab_data = self.tabs[tab_id]
                    text_widget = tab_data.text_widget
                    cursor = text_widget.textCursor()
                    tab_session = TabSession(
                        content=text_widget.toPlainText(),
                        current_file=tab_data.current_file,
                        cursor_position=cursor.position(),
                        scroll_position=text_widget.verticalScrollBar().value()
                    )
                    session_tabs.append(asdict(tab_session))
            app_session = AppSession(tabs=session_tabs, active_tab_index=self.tab_widget.currentIndex())
            with open(SESSION_FILE, 'w') as f:
                json.dump(asdict(app_session), f, indent=2)
        except Exception as e:
            print(f"Could not save session: {e}")
    
    def _restore_session(self) -> bool:
        try:
            if not os.path.exists(SESSION_FILE):
                return False
            with open(SESSION_FILE, 'r') as f:
                session_data = json.load(f)
            app_session = AppSession(**session_data)
            if not app_session.tabs:
                return False
            for tab_session_dict in app_session.tabs:
                tab_session = TabSession(**tab_session_dict)
                tab_id = self._new_tab(filename=tab_session.current_file, content=tab_session.content)
                if tab_id in self.tabs:
                    tab_data = self.tabs[tab_id]
                    text_widget = tab_data.text_widget
                    cursor = text_widget.textCursor()
                    cursor.setPosition(min(tab_session.cursor_position, len(tab_session.content)))
                    text_widget.setTextCursor(cursor)
                    QTimer.singleShot(100, lambda w=text_widget, pos=tab_session.scroll_position:
                                     w.verticalScrollBar().setValue(pos))
                    if tab_session.current_file:
                        tab_data.modified = False
                        tab_data.last_saved_content = tab_session.content
                        self._update_tab_title(tab_id, modified=False)
            if 0 <= app_session.active_tab_index < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(app_session.active_tab_index)
            return True
        except Exception as e:
            print(f"Could not restore session: {e}")
            return False
    
    def _clear_session(self):
        try:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
                QMessageBox.information(self, "Clear Session", "Saved session has been cleared.")
            else:
                QMessageBox.information(self, "Clear Session", "No saved session found.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not clear session: {e}")
    
    def _toggle_restore_session(self):
        self.preferences.restore_session = self.restore_session_action.isChecked()
        self._save_preferences()
    
    # =========================================================================
    # AUTOSAVE MANAGEMENT
    # =========================================================================
    
    def _toggle_autosave(self):
        enabled = self.autosave_enabled_action.isChecked()
        self.preferences.autosave_enabled = enabled
        self._save_preferences()
        if enabled:
            self.autosave_timer.start(self.preferences.autosave_interval * 1000)
            self.status_bar.showMessage("Autosave enabled", 2000)
        else:
            self.autosave_timer.stop()
            self.status_bar.showMessage("Autosave disabled", 2000)
    
    def _autosave_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Autosave Settings")
        dialog.resize(400, 180)
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout()
        enable_cb = QCheckBox("Enable autosave")
        enable_cb.setChecked(self.preferences.autosave_enabled)
        layout.addWidget(enable_cb)
        layout.addWidget(QLabel("\nAutosave interval (seconds):"))
        interval_layout = QHBoxLayout()
        spinbox = QSpinBox()
        spinbox.setRange(10, 600)
        spinbox.setValue(self.preferences.autosave_interval)
        interval_layout.addWidget(spinbox)
        interval_layout.addStretch()
        layout.addLayout(interval_layout)
        layout.addWidget(QLabel("\nNote: Autosave only affects files that have been\nsaved at least once. Untitled tabs are not autosaved."))
        layout.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        dialog.setLayout(layout)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            old_enabled = self.preferences.autosave_enabled
            old_interval = self.preferences.autosave_interval
            self.preferences.autosave_enabled = enable_cb.isChecked()
            self.preferences.autosave_interval = spinbox.value()
            self.autosave_enabled_action.setChecked(self.preferences.autosave_enabled)
            if self.preferences.autosave_enabled:
                self.autosave_timer.stop()
                self.autosave_timer.start(self.preferences.autosave_interval * 1000)
                if not old_enabled:
                    QMessageBox.information(self, "Autosave", "Autosave has been enabled.")
                elif old_interval != self.preferences.autosave_interval:
                    QMessageBox.information(self, "Autosave", f"Autosave interval changed to {self.preferences.autosave_interval} seconds.")
            else:
                self.autosave_timer.stop()
                if old_enabled:
                    QMessageBox.information(self, "Autosave", "Autosave has been disabled.")
            self._save_preferences()
    
    def _autosave_all(self):
        saved_count = 0
        for tab_id, tab_data in self.tabs.items():
            if tab_data.current_file:
                current_content = tab_data.text_widget.toPlainText()
                if current_content != tab_data.last_saved_content:
                    try:
                        with open(tab_data.current_file, "w", encoding='utf-8') as output_file:
                            output_file.write(current_content)
                        tab_data.last_saved_content = current_content
                        tab_data.modified = False
                        self._update_tab_title(tab_id, modified=False)
                        saved_count += 1
                    except Exception as e:
                        print(f"Autosave failed for {tab_data.current_file}: {e}")
        if saved_count > 0:
            self.status_bar.showMessage(f"Autosaved {saved_count} file(s)", 2000)
    
    # =========================================================================
    # TAB MANAGEMENT
    # =========================================================================
    
    def _new_tab(self, filename=None, content=""):
        self.tab_counter += 1
        text_widget = CodeEditor()
        text_widget.setFont(QFont(self.active_font_family, self.current_font_size))
        text_widget.setAcceptRichText(False)
        text_widget._notepad_app = self  # Link back to app for auto-eval
        if self.word_wrap_action.isChecked():
            text_widget.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        else:
            text_widget.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        tab_data = TabData(text_widget=text_widget, current_file=filename)
        self.tabs[self.tab_counter] = tab_data
        self._apply_theme_to_tab(tab_data, self.preferences.theme)
        text_widget.set_line_numbers_visible(self.line_numbers_action.isChecked())
        text_widget.set_syntax_highlighting(self.highlight_syntax, self.preferences.theme)
        if content:
            text_widget.setPlainText(content)
            tab_data.last_saved_content = content if filename else ""
        tab_title = os.path.basename(filename) if filename else f"Untitled {self.tab_counter}"
        index = self.tab_widget.addTab(text_widget, tab_title)
        self.tab_widget.setCurrentIndex(index)
        text_widget.textChanged.connect(lambda: self._on_text_modified(self.tab_counter))
        text_widget.cursorPositionChanged.connect(self._update_status_bar)
        text_widget.setFocus()
        return self.tab_counter
    
    def _close_tab(self, tab_id=None):
        if tab_id is None:
            index = self.tab_widget.currentIndex()
            tab_id = self._get_tab_id_from_index(index)
        if tab_id is None or tab_id not in self.tabs:
            return False
        tab_data = self.tabs[tab_id]
        if tab_data.modified:
            filename = os.path.basename(tab_data.current_file) if tab_data.current_file else "Untitled"
            reply = QMessageBox.question(
                self, "Save Changes",
                f"Do you want to save changes to '{filename}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._save_file(tab_id)
            elif reply == QMessageBox.StandardButton.Cancel:
                return False
        for i in range(self.tab_widget.count()):
            if self._get_tab_id_from_index(i) == tab_id:
                self.tab_widget.removeTab(i)
                break
        del self.tabs[tab_id]
        if len(self.tabs) == 0:
            self._save_preferences()
            self._save_session()
            QApplication.quit()
            return True
        self._update_window_title()
        return True
    
    def _close_tab_by_index(self, index):
        tab_id = self._get_tab_id_from_index(index)
        if tab_id:
            self._close_tab(tab_id)
    
    def _get_tab_id_from_index(self, index):
        widget = self.tab_widget.widget(index)
        for tab_id, tab_data in self.tabs.items():
            if tab_data.text_widget == widget:
                return tab_id
        return None
    
    def _get_current_tab_id(self):
        index = self.tab_widget.currentIndex()
        return self._get_tab_id_from_index(index)
    
    def _get_current_tab(self) -> Optional[TabData]:
        tab_id = self._get_current_tab_id()
        if tab_id:
            return self.tabs.get(tab_id)
        return None
    
    def _on_tab_changed(self, index):
        self._update_window_title()
        self._update_status_bar()
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.setFocus()
    
    def _update_tab_title(self, tab_id, modified=None):
        if tab_id not in self.tabs:
            return
        tab_data = self.tabs[tab_id]
        if modified is not None:
            tab_data.modified = modified
        for i in range(self.tab_widget.count()):
            if self._get_tab_id_from_index(i) == tab_id:
                modified_marker = "*" if tab_data.modified else ""
                if tab_data.current_file:
                    title = f"{modified_marker}{os.path.basename(tab_data.current_file)}"
                else:
                    title = f"{modified_marker}Untitled {tab_id}"
                self.tab_widget.setTabText(i, title)
                break
        self._update_window_title()
    
    def _update_window_title(self):
        tab_data = self._get_current_tab()
        if tab_data:
            base_title = " - Enhanced Notepad"
            modified_marker = "*" if tab_data.modified else ""
            if tab_data.current_file:
                self.setWindowTitle(f"{modified_marker}{os.path.basename(tab_data.current_file)}{base_title}")
            else:
                tab_id = self._get_current_tab_id()
                self.setWindowTitle(f"{modified_marker}Untitled {tab_id}{base_title}")
    
    def _next_tab(self):
        current = self.tab_widget.currentIndex()
        total = self.tab_widget.count()
        self.tab_widget.setCurrentIndex((current + 1) % total)
    
    def _prev_tab(self):
        current = self.tab_widget.currentIndex()
        total = self.tab_widget.count()
        self.tab_widget.setCurrentIndex((current - 1) % total)
    
    # =========================================================================
    # PREFERENCES MANAGEMENT
    # =========================================================================
    
    def _load_preferences(self) -> Preferences:
        try:
            if os.path.exists(PREFS_FILE):
                with open(PREFS_FILE, 'r') as f:
                    data = json.load(f)
                    return Preferences(**data)
        except Exception as e:
            print(f"Could not load preferences: {e}")
        return Preferences()
    
    def _save_preferences(self):
        try:
            self.preferences.font_size = self.current_font_size
            self.preferences.word_wrap = self.word_wrap_action.isChecked()
            self.preferences.status_bar = self.status_bar_action.isChecked()
            self.preferences.line_numbers = self.line_numbers_action.isChecked()
            with open(PREFS_FILE, 'w') as f:
                json.dump(asdict(self.preferences), f, indent=2)
        except Exception as e:
            print(f"Could not save preferences: {e}")
    
    def _apply_preferences(self):
        self.word_wrap_action.setChecked(self.preferences.word_wrap)
        self._toggle_word_wrap()
        self.status_bar_action.setChecked(self.preferences.status_bar)
        self._toggle_status_bar()
        self.line_numbers_action.setChecked(self.preferences.line_numbers)
        self._toggle_line_numbers()
        self.highlight_syntax = self.preferences.highlight_syntax
        if self.highlight_syntax == "off":
            self.highlight_off_action.setChecked(True)
        elif self.highlight_syntax == "code":
            self.highlight_code_action.setChecked(True)
        elif self.highlight_syntax == "text":
            self.highlight_text_action.setChecked(True)
    
    def _apply_theme(self, theme: str):
        for tab_data in self.tabs.values():
            self._apply_theme_to_tab(tab_data, theme)
        if theme == "dark":
            dark_stylesheet = """
            QMainWindow, QDialog, QMessageBox {
                background-color: #1e1e1e; color: #d4d4d4;
            }
            QTextEdit {
                background-color: #1e1e1e; color: #d4d4d4;
                selection-background-color: #264f78; selection-color: #ffffff; border: none;
            }
            QMenuBar {
                background-color: #2d2d30; color: #d4d4d4; border-bottom: 1px solid #3e3e42;
            }
            QMenuBar::item { background-color: transparent; padding: 4px 8px; }
            QMenuBar::item:selected { background-color: #3e3e42; }
            QMenuBar::item:pressed { background-color: #007acc; }
            QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #3e3e42; }
            QMenu::item { padding: 5px 25px 5px 20px; border: 1px solid transparent; }
            QMenu::item:selected { background-color: #094771; }
            QMenu::separator { height: 1px; background-color: #3e3e42; margin: 4px 0px; }
            QMenu::indicator { width: 13px; height: 13px; margin-left: 5px; }
            QTabWidget::pane { border: 1px solid #3e3e42; background-color: #1e1e1e; }
            QTabBar::tab {
                background-color: #2d2d30; color: #969696; padding: 8px 16px;
                border: 1px solid #3e3e42; border-bottom: none; margin-right: 2px;
                border-top-left-radius: 10px; border-top-right-radius: 10px;
            }
            QTabBar::tab:selected { background-color: #1e1e1e; color: #d4d4d4; border-bottom: 2px solid #007acc; }
            QTabBar::tab:hover { background-color: #3e3e42; }
            QStatusBar { background-color: #007acc; color: #ffffff; }
            QDialog { background-color: #2d2d30; }
            QLabel { color: #d4d4d4; }
            QLineEdit {
                background-color: #3c3c3c; color: #d4d4d4; border: 1px solid #3e3e42;
                padding: 4px; selection-background-color: #094771;
            }
            QPushButton {
                background-color: #0e639c; color: #ffffff; border: 1px solid #0e639c;
                padding: 5px 15px; border-radius: 2px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:pressed { background-color: #094771; }
            QPushButton:disabled { background-color: #3e3e42; color: #656565; }
            QCheckBox { color: #d4d4d4; spacing: 5px; }
            QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #3e3e42; background-color: #3c3c3c; }
            QCheckBox::indicator:checked { background-color: #007acc; border: 1px solid #007acc; }
            QSpinBox { background-color: #3c3c3c; color: #d4d4d4; border: 1px solid #3e3e42; padding: 3px; }
            QSpinBox::up-button, QSpinBox::down-button { background-color: #333337; border: 1px solid #3e3e42; }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #3e3e42; }
            QMessageBox { background-color: #2d2d30; }
            QMessageBox QLabel { color: #d4d4d4; }
            QScrollBar:vertical { background-color: #1e1e1e; width: 14px; border: none; }
            QScrollBar::handle:vertical { background-color: #424242; min-height: 20px; border-radius: 2px; }
            QScrollBar::handle:vertical:hover { background-color: #4e4e4e; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal { background-color: #1e1e1e; height: 14px; border: none; }
            QScrollBar::handle:horizontal { background-color: #424242; min-width: 20px; border-radius: 2px; }
            QScrollBar::handle:horizontal:hover { background-color: #4e4e4e; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            """
            self.setStyleSheet(dark_stylesheet)
        else:
            light_stylesheet = """
            QTextEdit {
                background-color: #ffffff; color: #000000;
                selection-background-color: #0078d7; selection-color: #ffffff; border: none;
            }
            QTabWidget::pane { border: 1px solid #d0d0d0; background-color: #ffffff; }
            QTabBar::tab {
                background-color: #f0f0f0; color: #404040; padding: 8px 16px;
                border: 1px solid #d0d0d0; border-bottom: none; margin-right: 2px;
                border-top-left-radius: 10px; border-top-right-radius: 10px;
            }
            QTabBar::tab:selected { background-color: #ffffff; color: #000000; border-bottom: 2px solid #0078d7; }
            QTabBar::tab:hover { background-color: #e0e0e0; }
            """
            self.setStyleSheet(light_stylesheet)
    
    def _apply_theme_to_tab(self, tab_data, theme: str):
        tab_data.text_widget.current_theme = theme
        tab_data.text_widget.update_syntax_theme(theme)
        if tab_data.text_widget.show_line_numbers:
            tab_data.text_widget.line_number_area.update()
        tab_data.text_widget.update()
        tab_data.text_widget.viewport().update()
    
    # =========================================================================
    # RECENT FILES MANAGEMENT
    # =========================================================================
    
    def _update_recent_files(self, filepath: str):
        if filepath in self.preferences.recent_files:
            self.preferences.recent_files.remove(filepath)
        self.preferences.recent_files.insert(0, filepath)
        self.preferences.recent_files = self.preferences.recent_files[:self.preferences.max_recent_files]
        self._save_preferences()
        self._update_recent_files_menu()
    
    def _update_recent_files_menu(self):
        self.recent_menu.clear()
        if not self.preferences.recent_files:
            action = QAction("(No recent files)", self)
            action.setEnabled(False)
            self.recent_menu.addAction(action)
        else:
            shortcut_keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']
            for i, filepath in enumerate(self.preferences.recent_files):
                if os.path.exists(filepath):
                    display_name = os.path.basename(filepath)
                    action = QAction(f"&{shortcut_keys[i] if i < len(shortcut_keys) else i+1}. {display_name}", self)
                    action.triggered.connect(lambda checked, f=filepath: self._open_recent_file(f))
                    self.recent_menu.addAction(action)
            self.recent_menu.addSeparator()
            settings_action = QAction("&Recent Files Settings...", self)
            settings_action.triggered.connect(self._recent_files_settings)
            self.recent_menu.addAction(settings_action)
            clear_action = QAction("C&lear Recent Files", self)
            clear_action.triggered.connect(self._clear_recent_files)
            self.recent_menu.addAction(clear_action)
    
    def _open_recent_file(self, filepath: str):
        if not os.path.exists(filepath):
            QMessageBox.critical(self, "File Not Found", f"The file '{filepath}' no longer exists.")
            self.preferences.recent_files.remove(filepath)
            self._save_preferences()
            self._update_recent_files_menu()
            return
        try:
            with open(filepath, "r", encoding='utf-8') as input_file:
                content = input_file.read()
            self._new_tab(filename=filepath, content=content)
            self._update_recent_files(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Open File Error", f"Could not read file: {e}")
    
    def _clear_recent_files(self):
        self.preferences.recent_files = []
        self._save_preferences()
        self._update_recent_files_menu()
    
    def _recent_files_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Recent Files Settings")
        dialog.resize(350, 150)
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout()
        max_layout = QHBoxLayout()
        max_layout.addWidget(QLabel("Maximum number of recent files:"))
        spinbox = QSpinBox()
        spinbox.setRange(5, 20)
        spinbox.setValue(self.preferences.max_recent_files)
        max_layout.addWidget(spinbox)
        max_layout.addStretch()
        layout.addLayout(max_layout)
        layout.addWidget(QLabel("\nNote: Files can be accessed via:\nAlt → F → R → (1-9, A-F)"))
        layout.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        dialog.setLayout(layout)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            old_max = self.preferences.max_recent_files
            new_max = spinbox.value()
            self.preferences.max_recent_files = new_max
            if new_max < old_max:
                self.preferences.recent_files = self.preferences.recent_files[:new_max]
            self._save_preferences()
            self._update_recent_files_menu()
    
    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================
    
    def new_window(self):
        new_window = NotepadApp()
        new_window.show()
    
    def open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Text Files (*.txt);;All Files (*.*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding='utf-8') as input_file:
                content = input_file.read()
            self._new_tab(filename=filepath, content=content)
            self._update_recent_files(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Open File Error", f"Could not read file: {e}")
    
    def _save_file(self, tab_id=None):
        if tab_id is None:
            tab_id = self._get_current_tab_id()
        if tab_id is None:
            return
        tab_data = self.tabs[tab_id]
        if tab_data.current_file:
            self._write_file(tab_id, tab_data.current_file)
        else:
            self._save_file_as(tab_id)
    
    def _save_file_as(self, tab_id=None):
        if tab_id is None:
            tab_id = self._get_current_tab_id()
        if tab_id is None:
            return
        filepath, _ = QFileDialog.getSaveFileName(self, "Save File", "", "Text Files (*.txt);;All Files (*.*)")
        if not filepath:
            return
        self._write_file(tab_id, filepath)
        tab_data = self.tabs[tab_id]
        tab_data.current_file = filepath
        self._update_tab_title(tab_id)
        self._update_recent_files(filepath)
    
    def _write_file(self, tab_id, filepath):
        tab_data = self.tabs[tab_id]
        try:
            with open(filepath, "w", encoding='utf-8') as output_file:
                text = tab_data.text_widget.toPlainText()
                output_file.write(text)
            tab_data.last_saved_content = text
            self._update_tab_title(tab_id, modified=False)
        except Exception as e:
            QMessageBox.critical(self, "Save File Error", f"Could not save file: {e}")
    
    def _save_all(self):
        for tab_id in self.tabs.keys():
            self._save_file(tab_id)
    
    def _close_all_tabs(self):
        for tab_id in list(self.tabs.keys()):
            if not self._close_tab(tab_id):
                return
    
    # =========================================================================
    # EDIT OPERATIONS
    # =========================================================================
    
    def _undo(self):
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.undo()
    
    def _redo(self):
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.redo()
    
    def _cut(self):
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.cut()
    
    def _copy(self):
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.copy()
    
    def _paste(self):
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.paste()
    
    def _delete(self):
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.textCursor().removeSelectedText()
    
    def _select_all(self):
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.selectAll()
    
    def _insert_time_date(self):
        tab_data = self._get_current_tab()
        if tab_data:
            now = datetime.datetime.now().strftime("%H:%M %m/%d/%Y")
            tab_data.text_widget.insertPlainText(now)
    
    def _find_dialog(self):
        tab_data = self._get_current_tab()
        if tab_data:
            dialog = FindDialog(self, tab_data.text_widget, self)
            dialog.show()
    
    def _find_next(self):
        tab_data = self._get_current_tab()
        if not tab_data:
            return
        if not self.last_find_term:
            QMessageBox.information(self, "Find Next", "Use Ctrl+F to open Find dialog first.")
            return
        flags = QTextDocument.FindFlag(0)
        if self.last_find_case_sensitive:
            flags = QTextDocument.FindFlag.FindCaseSensitively
        cursor = tab_data.text_widget.textCursor()
        found_cursor = tab_data.text_widget.document().find(self.last_find_term, cursor, flags)
        if found_cursor.isNull():
            found_cursor = tab_data.text_widget.document().find(self.last_find_term, 0, flags)
            if found_cursor.isNull():
                QMessageBox.information(self, "Find Next", f'Cannot find "{self.last_find_term}"')
                return
        tab_data.text_widget.setTextCursor(found_cursor)
    
    def _find_prev(self):
        tab_data = self._get_current_tab()
        if not tab_data:
            return
        if not self.last_find_term:
            QMessageBox.information(self, "Find Previous", "Use Ctrl+F to open Find dialog first.")
            return
        flags = QTextDocument.FindFlag.FindBackward
        if self.last_find_case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        cursor = tab_data.text_widget.textCursor()
        found_cursor = tab_data.text_widget.document().find(self.last_find_term, cursor, flags)
        if found_cursor.isNull():
            QMessageBox.information(self, "Find Previous", f'Cannot find "{self.last_find_term}"')
        else:
            tab_data.text_widget.setTextCursor(found_cursor)
    
    def _replace_dialog(self):
        tab_data = self._get_current_tab()
        if tab_data:
            dialog = ReplaceDialog(self, tab_data.text_widget)
            dialog.show()
    
    def _goto_line(self):
        tab_data = self._get_current_tab()
        if not tab_data:
            return
        line_num, ok = QInputDialog.getInt(self, "Go To Line", "Line number:", 1, 1, 1000000)
        if ok:
            cursor = QTextCursor(tab_data.text_widget.document().findBlockByLineNumber(line_num - 1))
            tab_data.text_widget.setTextCursor(cursor)
    
    # =========================================================================
    # FORMULA EVALUATION
    # =========================================================================
    
    def pre_process_expression(self, expr: str) -> str:
        expr = expr.replace('^', '**')
        expr = re.sub(r'(\d)(?![eE][+-]?\d)([a-zA-Z\(])', r'\1*\2', expr)
        expr = re.sub(r'(\))([0-9a-zA-Z])', r'\1*\2', expr)
        return expr

    def _parse_formula_line(self, content, evaluator):
        """Parse a formula line and return (var_name, var_separator, formula_to_eval, prefix)."""
        var_name = None
        var_separator = None
        formula_to_eval = None
        prefix = ''

        if ':' in content:
            parts = content.split(':', 1)
            potential_var = parts[0].strip()
            if potential_var.replace(' ', '').replace('_', '').isalnum() and not potential_var[0].isdigit():
                var_name = potential_var.replace(' ', '_')
                var_separator = ':'
                remainder = parts[1].strip()
                if '=' in remainder:
                    chain_parts = remainder.split('=')
                    formula_to_eval = chain_parts[-1].strip()
                    if len(chain_parts) > 1:
                        prefix = '='.join(chain_parts[:-1]).strip() + ' = '
                else:
                    formula_to_eval = remainder

        if var_name is None:
            parts = content.split('=')
            if len(parts) >= 1:
                first_part = parts[0].strip()
                if (first_part.replace('_', '').replace(' ', '').isalnum() and
                        not first_part[0].isdigit() and
                        not any(op in first_part for op in ['+', '-', '*', '/', '(', ')', '%'])):
                    var_name = first_part.replace(' ', '_')
                    var_separator = '='
                    if len(parts) > 1:
                        remainder = '='.join(parts[1:]).strip()
                        if '=' in remainder:
                            chain_parts = remainder.split('=')
                            formula_to_eval = chain_parts[-1].strip()
                            if len(chain_parts) > 1:
                                prefix = '='.join(chain_parts[:-1]).strip() + ' = '
                        else:
                            formula_to_eval = remainder
                else:
                    formula_to_eval = parts[-1].strip()
                    if len(parts) > 1:
                        prefix = '='.join(parts[:-1]).strip() + ' = '

        if formula_to_eval is None:
            formula_to_eval = content

        return var_name, var_separator, formula_to_eval, prefix

    def _format_result(self, result) -> str:
        """Format a numeric result as a string."""
        if isinstance(result, (float, int)):
            if abs(result) >= 1e10 or (abs(result) < 1e-4 and result != 0):
                return f"{result:.4e}"
            else:
                return f"{result:.10f}".rstrip('0').rstrip('.')
        return str(result)

    def _evaluate_current_line(self):
        """Auto-evaluate the current line when '=' is typed. Cursor goes to end of line."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return

        text_widget = tab_data.text_widget
        evaluator = tab_data.evaluator
        cursor = text_widget.textCursor()
        block = cursor.block()
        line = block.text()
        stripped = line.rstrip()

        if not stripped.endswith('='):
            return

        content = stripped[:-1].strip()
        var_name, var_separator, formula_to_eval, prefix = self._parse_formula_line(content, evaluator)

        if not formula_to_eval:
            return

        success, result, error = evaluator.evaluate(self.pre_process_expression(formula_to_eval))
        if not success:
            return

        result_str = self._format_result(result)

        if var_name:
            evaluator.variables[var_name] = result
            new_line = f"{var_name}{var_separator} {prefix}{result_str}" if prefix else f"{var_name} {var_separator} {result_str}"
        else:
            new_line = f"{prefix}{result_str}" if prefix else f"{formula_to_eval} = {result_str}"

        # Replace the current line
        block_start = block.position()
        block_end = block_start + block.length() - 1  # exclude trailing newline

        cursor.setPosition(block_start)
        cursor.setPosition(block_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(new_line)

        # Place cursor at end of the replaced line
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
        text_widget.setTextCursor(cursor)

    def _evaluate_formula(self):
        """Evaluate all formulas (Ctrl+E). Cursor goes to end of last evaluated line."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return

        text_widget = tab_data.text_widget
        evaluator = tab_data.evaluator
        cursor = text_widget.textCursor()

        if cursor.hasSelection():
            selected_text = cursor.selectedText()
            start_pos = cursor.selectionStart()
            end_pos = cursor.selectionEnd()
        else:
            selected_text = text_widget.toPlainText()
            start_pos = 0
            end_pos = len(selected_text)

        lines = selected_text.split('\n')
        modified = False
        new_lines = []
        last_evaluated_line_index = -1

        for i, line in enumerate(lines):
            stripped = line.rstrip()
            if stripped.endswith('='):
                content = stripped[:-1].strip()
                var_name, var_separator, formula_to_eval, prefix = self._parse_formula_line(content, evaluator)

                if formula_to_eval:
                    success, result, error = evaluator.evaluate(self.pre_process_expression(formula_to_eval))
                    if success:
                        result_str = self._format_result(result)
                        if var_name:
                            evaluator.variables[var_name] = result
                            new_lines.append(f"{var_name}{var_separator} {prefix}{result_str}" if prefix else f"{var_name} {var_separator} {result_str}")
                        else:
                            new_lines.append(f"{prefix}{result_str}" if prefix else f"{formula_to_eval} = {result_str}")
                        last_evaluated_line_index = i
                        modified = True
                        continue
            new_lines.append(line)

        if modified:
            if cursor.hasSelection():
                cursor.setPosition(start_pos)
                cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText('\n'.join(new_lines))
            else:
                text_widget.setPlainText('\n'.join(new_lines))

            # Move cursor to end of the last evaluated line
            if last_evaluated_line_index >= 0:
                target_block = text_widget.document().findBlockByLineNumber(last_evaluated_line_index)
                if target_block.isValid():
                    new_cursor = QTextCursor(target_block)
                    new_cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                    text_widget.setTextCursor(new_cursor)
    
    def _list_variables(self):
        tab_data = self._get_current_tab()
        if not tab_data:
            return
        variables = tab_data.evaluator.variables
        if not variables:
            QMessageBox.information(self, "Variables", "No variables currently defined.")
            return
        var_list = []
        for name, value in sorted(variables.items()):
            val_str = f"{value:.10f}".rstrip('0').rstrip('.') if isinstance(value, float) else str(value)
            var_list.append(f"{name} = {val_str}")
        QMessageBox.information(self, "Variable Inspector", "Current Variables:\n" + "-" * 20 + "\n" + "\n".join(var_list))
    
    def _clear_variables(self):
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.evaluator.clear_variables()
            QMessageBox.information(self, "Clear Variables", "All formula variables have been cleared.")
    
    # =========================================================================
    # VIEW OPERATIONS
    # =========================================================================
    
    def _toggle_word_wrap(self):
        wrap_mode = QTextEdit.LineWrapMode.WidgetWidth if self.word_wrap_action.isChecked() else QTextEdit.LineWrapMode.NoWrap
        for tab_data in self.tabs.values():
            tab_data.text_widget.setLineWrapMode(wrap_mode)
        self._save_preferences()
    
    def _font_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Font")
        dialog.resize(440, 230)
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Font family:"))
        family_combo = QFontComboBox()
        family_combo.setWritingSystem(QFontDatabase.WritingSystem.Any)
        # Remove monospace filter so all bundled fonts show up
        family_combo.setCurrentFont(QFont(self.active_font_family))
        layout.addWidget(family_combo)

        layout.addWidget(QLabel("Font size:"))
        size_layout = QHBoxLayout()
        spinbox = QSpinBox()
        spinbox.setRange(8, 72)
        spinbox.setValue(self.current_font_size)
        size_layout.addWidget(spinbox)
        size_layout.addStretch()
        layout.addLayout(size_layout)

        preview = QLabel("The quick brown fox  0 1 2 3 4  ( ) { } [ ]")
        preview.setFont(QFont(self.active_font_family, 11))
        preview.setStyleSheet("padding: 8px; border: 1px solid #888;")
        layout.addWidget(preview)

        def update_preview():
            preview.setFont(QFont(family_combo.currentFont().family(), spinbox.value()))
        family_combo.currentFontChanged.connect(lambda _: update_preview())
        spinbox.valueChanged.connect(lambda _: update_preview())

        layout.addStretch()
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.active_font_family = family_combo.currentFont().family()
            self.preferences.font_family = self.active_font_family
            self.current_font_size = spinbox.value()
            new_font = QFont(self.active_font_family, self.current_font_size)
            for tab_data in self.tabs.values():
                tab_data.text_widget.setFont(new_font)
            self._save_preferences()
        
    def _toggle_status_bar(self):
        if self.status_bar_action.isChecked():
            self.status_bar.show()
            self._update_status_bar()
        else:
            self.status_bar.hide()
        self._save_preferences()
    
    def _toggle_line_numbers(self):
        visible = self.line_numbers_action.isChecked()
        for tab_data in self.tabs.values():
            tab_data.text_widget.set_line_numbers_visible(visible)
        self._save_preferences()
    
    def _toggle_highlight_syntax(self, mode):
        self.highlight_syntax = mode
        self.preferences.highlight_syntax = mode
        for tab_data in self.tabs.values():
            tab_data.text_widget.set_syntax_highlighting(mode, self.preferences.theme)
        self.highlight_off_action.setChecked(mode == "off")
        self.highlight_code_action.setChecked(mode == "code")
        self.highlight_text_action.setChecked(mode == "text")
        self._save_preferences()
    
    def _update_status_bar(self):
        if self.status_bar_action.isChecked():
            tab_data = self._get_current_tab()
            if tab_data:
                cursor = tab_data.text_widget.textCursor()
                line = cursor.blockNumber() + 1
                col = cursor.columnNumber() + 1
                self.status_bar.showMessage(f"Ln {line}, Col {col}")
    
    def _zoom_in(self):
        if self.current_font_size < 72:
            self.current_font_size += 1
            new_font = QFont(self.active_font_family, self.current_font_size)
            for tab_data in self.tabs.values():
                tab_data.text_widget.setFont(new_font)
            self._save_preferences()
    
    def _zoom_out(self):
        if self.current_font_size > 8:
            self.current_font_size -= 1
            new_font = QFont(self.active_font_family, self.current_font_size)
            for tab_data in self.tabs.values():
                tab_data.text_widget.setFont(new_font)
            self._save_preferences()
    
    def _zoom_reset(self):
        self.current_font_size = 11
        new_font = QFont(self.active_font_family, self.current_font_size)
        for tab_data in self.tabs.values():
            tab_data.text_widget.setFont(new_font)
        self._save_preferences()
    
    def _change_theme(self, theme: str):
        self.preferences.theme = theme
        self._apply_theme(theme)
        self._save_preferences()
        QMessageBox.information(self, "Theme Changed",
                               f"Theme changed to {theme.capitalize()} mode.\n\n"
                               "The new theme has been applied to menus, tabs, and text editor.")
    
    # =========================================================================
    # HELP
    # =========================================================================
    
    def _show_formula_help(self):
        help_text = """Formula Evaluation Help

How to use:
1. Type a mathematical expression followed by '='
2. The result is evaluated automatically when you press '='
3. Or press Ctrl+E to evaluate all formulas at once

Available Operators:
  +  Addition       -  Subtraction
  *  Multiplication /  Division
  // Floor Division %  Modulo
  ** Power

Available Functions:
  abs, round, min, max, sum, pow
  sqrt, sin, cos, tan
  log, log10, exp

Constants:
  pi, e

Examples:
  2 + 2 * 3 =          → evaluates instantly
  sqrt(16) =           → evaluates instantly
  sin(pi/2) =
  2**8 =

Variables:
  Results stored per tab automatically
  Use Edit > Clear Variables to reset

Selection Mode (Ctrl+E):
  Select text then Ctrl+E to evaluate only that portion

Navigation:
  Up arrow on first line → start of line
  Down arrow on last line → end of line"""
        QMessageBox.information(self, "Formula Help", help_text)
    
    def _show_about(self):
        about_text = """Enhanced Notepad
Version 5.0 (PyQt6)

A feature-rich text editor with:
- Tabbed interface
- Autosave
- Session restoration
- Formula evaluation (auto on '=', or Ctrl+E)
- Recent files
- Find & Replace
- Line numbers
- Dark mode
- Tab navigation (Ctrl+Tab)
- Boundary key teleport (Up/Down)
- And more!

Built with Python and PyQt6"""
        QMessageBox.about(self, "About Enhanced Notepad", about_text)
    
    # =========================================================================
    # MODIFICATIONS TRACKING
    # =========================================================================
    
    def _on_text_modified(self, tab_id):
        if tab_id not in self.tabs:
            return
        tab_data = self.tabs[tab_id]
        if not tab_data.modified:
            self._update_tab_title(tab_id, modified=True)
    
    # =========================================================================
    # WINDOW CLOSE EVENT
    # =========================================================================
    
    def closeEvent(self, event):
        for tab_id in list(self.tabs.keys()):
            if not self._close_tab(tab_id):
                event.ignore()
                return
        self._save_preferences()
        self._save_session()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = NotepadApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
