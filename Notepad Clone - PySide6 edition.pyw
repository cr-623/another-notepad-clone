import sys
import os
import json
import re
import ast
import operator
import math
import datetime
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Tuple, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QPlainTextEdit, QFileDialog, QMessageBox,
    QInputDialog, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QTabWidget, QWidget, QStatusBar, QMenu,
    QMenuBar, QSpinBox, QDialogButtonBox, QListWidget,
    QListWidgetItem, QSplitter, QFrame, QSizePolicy, QComboBox
)
from PySide6.QtGui import (
    QFont, QFontDatabase, QAction, QKeySequence, QIcon, QTextCursor,
    QTextCharFormat, QColor, QPalette, QSyntaxHighlighter, QTextDocument,
    QActionGroup, QWheelEvent, QTextBlockUserData, QPainter, QPageSize,
    QPageLayout
)
from PySide6.QtCore import (
    Qt, QRegularExpression, Signal, QTimer, QSize, QMarginsF
)
from PySide6.QtPrintSupport import QPrinter

# ── Spell-check: optional dependency ─────────────────────────────────────────
try:
    from spellchecker import SpellChecker as _SpellChecker
    SPELLCHECK_AVAILABLE = True
except ImportError:
    SPELLCHECK_AVAILABLE = False

# Constants
ICON_PATH = "notepad.ico"

def _appdata_dir() -> Path:
    """Return a writable AppData directory, creating it if needed."""
    base = Path(os.environ.get("APPDATA") or os.path.expanduser("~/.config"))
    d = base / "EnhancedNotepad"
    d.mkdir(parents=True, exist_ok=True)
    return d

APP_DIR      = _appdata_dir()
PREFS_FILE   = str(APP_DIR / "notepad_prefs.json")
SESSION_FILE = str(APP_DIR / "notepad_session.json")
DICT_FILE    = str(APP_DIR / "notepad_dict.txt")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ClosedTab:
    title: str
    content: str
    current_file: Optional[str] = None
    cursor_position: int = 0


@dataclass
class Preferences:
    font_size: int = 11
    word_wrap: bool = True
    status_bar: bool = True
    recent_files: list = None
    theme: str = "light"
    font_family: str = ""
    line_numbers: bool = False
    highlight_syntax: str = "off"
    max_recent_files: int = 10
    autosave_enabled: bool = True
    autosave_interval: int = 60
    restore_session: bool = True
    spellcheck_enabled: bool = False
    auto_eval_enabled: bool = True

    def __post_init__(self):
        if self.recent_files is None:
            self.recent_files = []


@dataclass
class TabSession:
    content: str
    current_file: Optional[str] = None
    cursor_position: int = 0
    scroll_position: int = 0


@dataclass
class AppSession:
    tabs: List[TabSession] = None
    active_tab_index: int = 0

    def __post_init__(self):
        if self.tabs is None:
            self.tabs = []


# =============================================================================
# SAFE EXPRESSION EVALUATOR
# =============================================================================

class SafeExpressionEvaluator:
    SAFE_OPERATORS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
    }
    SAFE_FUNCTIONS = {
        'abs': abs, 'round': round, 'min': min, 'max': max,
        'sum': sum, 'pow': pow, 'sqrt': math.sqrt, 'sin': math.sin,
        'cos': math.cos, 'tan': math.tan, 'log': math.log,
        'log10': math.log10, 'exp': math.exp, 'pi': math.pi, 'e': math.e,
    }

    def __init__(self):
        self.variables = {}

    def clear_variables(self):
        self.variables = {}

    def _eval_node(self, node):
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
                raise ValueError(f"Operator {op_type.__name__} not allowed")
            return self.SAFE_OPERATORS[op_type](
                self._eval_node(node.left), self._eval_node(node.right))
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Operator {op_type.__name__} not allowed")
            return self.SAFE_OPERATORS[op_type](self._eval_node(node.operand))
        elif isinstance(node, ast.Call):
            func = self._eval_node(node.func)
            args = [self._eval_node(a) for a in node.args]
            return func(*args)
        elif isinstance(node, ast.List):
            return [self._eval_node(e) for e in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_node(e) for e in node.elts)
        else:
            raise ValueError(f"Unsupported: {type(node).__name__}")

    def evaluate(self, expression: str) -> Tuple[bool, Optional[float], Optional[str]]:
        try:
            tree = ast.parse(expression, mode='eval')
            result = self._eval_node(tree.body)
            return True, result, None
        except (SyntaxError, ValueError, NameError, TypeError, ZeroDivisionError) as e:
            return False, None, str(e)


# =============================================================================
# SPELL CHECK HIGHLIGHTER MIXIN DATA
# =============================================================================


def _re_matches(pattern: str, text: str):
    """Yield QRegularExpressionMatch objects — works around PySide6 iterator quirk."""
    it = QRegularExpression(pattern).globalMatch(text)
    while it.hasNext():
        yield it.next()


class SpellCheckData(QTextBlockUserData):
    def __init__(self, misspelled: list):
        super().__init__()
        self.misspelled = misspelled  # list of (start, length) tuples


# =============================================================================
# SYNTAX + SPELL HIGHLIGHTER
# =============================================================================

class SyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document, mode="off", theme="light",
                 spell_checker=None, spellcheck_enabled=False):
        super().__init__(document)
        self.mode = mode
        self.theme = theme
        self.spell_checker = spell_checker
        self.spellcheck_enabled = spellcheck_enabled
        self._misspelled_format = QTextCharFormat()
        self._misspelled_format.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self._misspelled_format.setUnderlineColor(QColor("#e53935"))
        self.setup_formats()

    def setup_formats(self):
        self.formats = {}
        if self.mode == "off":
            return
        if self.mode == "code":
            colors = {
                'number': '#445ad4', 'variable': '#e06c75', 'operator': '#44ccd4',
                'string': '#21ad4d', 'function': '#ffeb3b', 'bracket': '#1400eb',
                'bracket_err': ('#ef4444', '#ffffff'), 'punct': '#484848'
            }
        else:
            colors = {
                'number': '#898989', 'variable': '#484848', 'operator': '#898989',
                'string': '#b3b3b3', 'function': '#484848', 'bracket': '#000000',
                'bracket_err': ('#000000', '#ffffff'), 'punct': '#000000'
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
        if self.mode != "off":
            self._highlight_syntax(text)
        if self.spellcheck_enabled and self.spell_checker:
            self._highlight_spelling(text)

    def _highlight_syntax(self, text):
        for pattern, key in [
            (r'\b\d+\.?\d*([eE][+-]?\d+)?\b', 'number'),
            (r'"[^"]*"|\'[^\']*\'', 'string'),
            (r'[\+\-\*\/\=\%\^]', 'operator'),
            (r'[\,\!\:\;\&\.]', 'punct'),
        ]:
            for m in _re_matches(pattern, text):
                self.setFormat(m.capturedStart(), m.capturedLength(),
                               self.formats.get(key, QTextCharFormat()))
        for m in _re_matches(r'\b[a-zA-Z_][a-zA-Z0-9_]*(?=\()', text):
            self.setFormat(m.capturedStart(), m.capturedLength(),
                           self.formats.get('function', QTextCharFormat()))
        for m in _re_matches(
                r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text):
            if self.format(m.capturedStart()) == QTextCharFormat():
                self.setFormat(m.capturedStart(), m.capturedLength(),
                               self.formats.get('variable', QTextCharFormat()))
        self._highlight_brackets(text)

    def _highlight_brackets(self, text):
        stack = []
        pairs = {')': '(', ']': '[', '}': '{'}
        for i, char in enumerate(text):
            if char in '([{':
                stack.append((char, i))
            elif char in ')]}':
                if stack and stack[-1][0] == pairs[char]:
                    _, open_pos = stack.pop()
                    self.setFormat(open_pos, 1,
                                   self.formats.get('bracket', QTextCharFormat()))
                    self.setFormat(i, 1,
                                   self.formats.get('bracket', QTextCharFormat()))
                else:
                    self.setFormat(i, 1,
                                   self.formats.get('bracket_err', QTextCharFormat()))
        for _, pos in stack:
            self.setFormat(pos, 1,
                           self.formats.get('bracket_err', QTextCharFormat()))

    def _highlight_spelling(self, text):
        misspelled_ranges = []
        word_pattern = QRegularExpression(r"\b[a-zA-Z']+\b")
        it = word_pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            word = m.captured().strip("'")
            if len(word) > 1 and word.lower() not in self.spell_checker:
                self.setFormat(m.capturedStart(), m.capturedLength(),
                               self._misspelled_format)
                misspelled_ranges.append((m.capturedStart(), m.capturedLength()))
        self.currentBlock().setUserData(SpellCheckData(misspelled_ranges))

    def set_mode(self, mode):
        self.mode = mode
        self.setup_formats()
        self.rehighlight()

    def set_theme(self, theme):
        self.theme = theme
        self.setup_formats()
        self.rehighlight()

    def set_spellcheck(self, enabled, checker=None):
        self.spellcheck_enabled = enabled
        if checker:
            self.spell_checker = checker
        self.rehighlight()


# =============================================================================
# LINE NUMBER AREA
# =============================================================================

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


# =============================================================================
# CODE EDITOR
# =============================================================================

class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.show_line_numbers = False
        self.highlighter = None
        self.current_theme = "light"
        self._notepad_app = None
        self._rmb_held = False
        self._rmb_zoom_accum = 0

        self.document().blockCountChanged.connect(self.update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(self.update_line_number_area)
        self.textChanged.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)

    def line_number_area_width(self):
        if not self.show_line_numbers:
            return 0
        digits = len(str(max(1, self.document().blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, *args):
        self.line_number_area.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            0, cr.top(), self.line_number_area_width(), cr.height())

    def line_number_area_paint_event(self, event):
        if not self.show_line_numbers:
            return
        try:
            painter = QPainter(self.line_number_area)
            bg = QColor("#252526") if self.current_theme == "dark" else QColor("#f0f0f0")
            fg = QColor("#858585") if self.current_theme == "dark" else QColor("#666666")
            painter.fillRect(event.rect(), bg)
            block = self.firstVisibleBlock()
            if not block.isValid():
                return
            block_number = block.blockNumber()
            top = int(self.blockBoundingGeometry(block)
                      .translated(self.contentOffset()).top())
            bottom = top + int(self.blockBoundingRect(block).height())
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    painter.setPen(fg)
                    painter.drawText(
                        0, top, self.line_number_area.width() - 5,
                        self.fontMetrics().height(),
                        Qt.AlignmentFlag.AlignRight, str(block_number + 1))
                block = block.next()
                top = bottom
                bottom = top + int(self.blockBoundingRect(block).height())
                block_number += 1
            painter.end()
        except Exception as e:
            print(f"Line number paint error: {e}")

    def set_line_numbers_visible(self, visible):
        self.show_line_numbers = visible
        self.line_number_area.setVisible(visible)
        self.update_line_number_area_width(0)
        self.line_number_area.update()

    def set_syntax_highlighting(self, mode, theme="light",
                                 spell_checker=None, spellcheck_enabled=False):
        if mode == "off" and not spellcheck_enabled:
            if self.highlighter:
                self.highlighter.setDocument(None)
                self.highlighter = None
        else:
            if self.highlighter:
                self.highlighter.set_mode(mode)
                self.highlighter.set_theme(theme)
                self.highlighter.set_spellcheck(spellcheck_enabled, spell_checker)
            else:
                self.highlighter = SyntaxHighlighter(
                    self.document(), mode, theme,
                    spell_checker, spellcheck_enabled)

    def update_syntax_theme(self, theme):
        if self.highlighter:
            self.highlighter.set_theme(theme)

    def get_misspelled_word_at(self, pos):
        """Return (word, start, suggestions) if cursor is on a misspelled word."""
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        data = block.userData()
        if not isinstance(data, SpellCheckData):
            return None
        col = cursor.positionInBlock()
        text = block.text()
        for start, length in data.misspelled:
            if start <= col <= start + length:
                word = text[start:start + length]
                return word, block.position() + start, length
        return None

    # ------------------------------------------------------------------
    # RMB + scroll → zoom
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._rmb_held = True
            self._rmb_zoom_accum = 0
            self._rmb_press_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self._rmb_held and self._rmb_zoom_accum == 0:
                self._show_context_menu(event.globalPosition().toPoint(),
                                        event.position().toPoint())
            self._rmb_held = False
            self._rmb_zoom_accum = 0
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if self._rmb_held and self._notepad_app is not None:
            delta = event.angleDelta().y()
            self._rmb_zoom_accum += delta
            steps = self._rmb_zoom_accum // 120
            if steps != 0:
                self._rmb_zoom_accum -= steps * 120
                fn = self._notepad_app._zoom_in if steps > 0 else self._notepad_app._zoom_out
                for _ in range(abs(steps)):
                    fn()
            event.accept()
            return
        super().wheelEvent(event)

    def _show_context_menu(self, global_pos, local_pos):
        menu = QMenu(self)

        # Spell-check suggestions
        if (self._notepad_app and
                self._notepad_app.preferences.spellcheck_enabled and
                self._notepad_app.spell_checker):
            result = self.get_misspelled_word_at(local_pos)
            if result:
                word, word_pos, word_len = result
                suggestions = self._notepad_app.spell_checker.candidates(word)
                suggestions = list(suggestions)[:8] if suggestions else []
                if suggestions:
                    for sug in suggestions:
                        act = menu.addAction(sug)
                        act.triggered.connect(
                            lambda _, s=sug, p=word_pos, l=word_len:
                            self._replace_word(p, l, s))
                else:
                    no_act = menu.addAction("(no suggestions)")
                    no_act.setEnabled(False)
                add_act = menu.addAction(f'Add "{word}" to dictionary')
                add_act.triggered.connect(
                    lambda _, w=word: self._notepad_app._add_to_dictionary(w))
                menu.addSeparator()

        menu.addAction("Undo", self.undo)
        menu.addAction("Redo", self.redo)
        menu.addSeparator()
        menu.addAction("Cut", self.cut)
        menu.addAction("Copy", self.copy)
        menu.addAction("Paste", self.paste)
        menu.addSeparator()
        menu.addAction("Select All", self.selectAll)
        if self._notepad_app:
            menu.addSeparator()
            menu.addAction("Evaluate Formula\tCtrl+E",
                           self._notepad_app._evaluate_formula)
        menu.exec(global_pos)

    def _replace_word(self, pos, length, replacement):
        cursor = QTextCursor(self.document())
        cursor.setPosition(pos)
        cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replacement)

    # ------------------------------------------------------------------
    # Boundary key navigation
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        key = event.key()
        mod = event.modifiers()
        if key == Qt.Key.Key_Up and mod == Qt.KeyboardModifier.NoModifier:
            cursor = self.textCursor()
            if cursor.blockNumber() == 0:
                cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
                self.setTextCursor(cursor)
                return
        if key == Qt.Key.Key_Down and mod == Qt.KeyboardModifier.NoModifier:
            cursor = self.textCursor()
            if cursor.blockNumber() == self.document().blockCount() - 1:
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                self.setTextCursor(cursor)
                return
        super().keyPressEvent(event)
        if key == Qt.Key.Key_Equal and mod == Qt.KeyboardModifier.NoModifier:
            if (self._notepad_app is not None and
                    self._notepad_app.preferences.auto_eval_enabled):
                if self.textCursor().block().text().rstrip().endswith('='):
                    self._notepad_app._evaluate_current_line()


# =============================================================================
# TAB DATA
# =============================================================================

@dataclass
class TabData:
    text_widget: CodeEditor
    current_file: Optional[str] = None
    modified: bool = False
    evaluator: SafeExpressionEvaluator = None
    last_saved_content: str = ""

    def __post_init__(self):
        if self.evaluator is None:
            self.evaluator = SafeExpressionEvaluator()


# =============================================================================
# FIND DIALOG
# =============================================================================

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
        row = QHBoxLayout()
        row.addWidget(QLabel("Find what:"))
        self.search_entry = QLineEdit(self.app.last_find_term)
        self.search_entry.selectAll()
        row.addWidget(self.search_entry)
        btn = QPushButton("Find Next")
        btn.clicked.connect(self.find_next)
        row.addWidget(btn)
        layout.addLayout(row)
        opts = QHBoxLayout()
        self.match_case_cb = QCheckBox("Match case")
        self.match_case_cb.setChecked(self.app.last_find_case_sensitive)
        opts.addWidget(self.match_case_cb)
        opts.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        opts.addWidget(cancel)
        layout.addLayout(opts)
        self.setLayout(layout)
        self.search_entry.returnPressed.connect(self.find_next)
        self.search_entry.setFocus()

    def find_next(self):
        term = self.search_entry.text()
        if not term:
            return
        self.app.last_find_term = term
        self.app.last_find_case_sensitive = self.match_case_cb.isChecked()
        flags = QTextDocument.FindFlag(0)
        if self.match_case_cb.isChecked():
            flags = QTextDocument.FindFlag.FindCaseSensitively
        cursor = self.text_widget.textCursor()
        found = self.text_widget.document().find(term, cursor, flags)
        if found.isNull():
            found = self.text_widget.document().find(term, 0, flags)
        if found.isNull():
            QMessageBox.information(self, "Find", f'Cannot find "{term}"')
        else:
            self.text_widget.setTextCursor(found)


# =============================================================================
# REPLACE DIALOG
# =============================================================================

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
        fr = QHBoxLayout()
        fr.addWidget(QLabel("Find what:"))
        self.find_entry = QLineEdit()
        fr.addWidget(self.find_entry)
        fb = QPushButton("Find Next")
        fb.clicked.connect(self.find_next)
        fr.addWidget(fb)
        layout.addLayout(fr)
        rr = QHBoxLayout()
        rr.addWidget(QLabel("Replace with:"))
        self.replace_entry = QLineEdit()
        rr.addWidget(self.replace_entry)
        rb = QPushButton("Replace")
        rb.clicked.connect(self.replace)
        rr.addWidget(rb)
        layout.addLayout(rr)
        opts = QHBoxLayout()
        self.match_case_cb = QCheckBox("Match case")
        opts.addWidget(self.match_case_cb)
        opts.addStretch()
        rab = QPushButton("Replace All")
        rab.clicked.connect(self.replace_all)
        opts.addWidget(rab)
        layout.addLayout(opts)
        self.setLayout(layout)
        self.find_entry.returnPressed.connect(self.find_next)
        self.find_entry.setFocus()

    def _flags(self):
        flags = QTextDocument.FindFlag(0)
        if self.match_case_cb.isChecked():
            flags = QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def find_next(self):
        term = self.find_entry.text()
        if not term:
            return
        found = self.text_widget.document().find(
            term, self.text_widget.textCursor(), self._flags())
        if found.isNull():
            QMessageBox.information(self, "Replace", f'Cannot find "{term}"')
        else:
            self.text_widget.setTextCursor(found)

    def replace(self):
        cursor = self.text_widget.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_entry.text())
            self.find_next()

    def replace_all(self):
        term = self.find_entry.text()
        repl = self.replace_entry.text()
        if not term:
            return
        count = 0
        cursor = QTextCursor(self.text_widget.document())
        cursor.beginEditBlock()
        while True:
            cursor = self.text_widget.document().find(term, cursor, self._flags())
            if cursor.isNull():
                break
            cursor.insertText(repl)
            count += 1
        cursor.endEditBlock()
        QMessageBox.information(self, "Replace All", f"Replaced {count} occurrence(s)")


# =============================================================================
# FONT DIALOG
# =============================================================================

class FontDialog(QDialog):
    def __init__(self, parent, current_family: str, current_size: int, theme: str):
        super().__init__(parent)
        self.setWindowTitle("Font")
        self.resize(520, 400)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        self.selected_family = current_family
        self.selected_size = current_size
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Search:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Type to filter fonts…")
        self.filter_edit.textChanged.connect(self._filter_fonts)
        top.addWidget(self.filter_edit, stretch=3)
        top.addWidget(QLabel("  Size:"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 96)
        self.size_spin.setValue(current_size)
        self.size_spin.setFixedWidth(60)
        self.size_spin.valueChanged.connect(self._update_preview)
        top.addWidget(self.size_spin)
        layout.addLayout(top)
        self.font_list = QListWidget()
        self.font_list.setFixedHeight(180)
        self._all_families = sorted(QFontDatabase.families())
        self._populate_list(self._all_families)
        self.font_list.currentTextChanged.connect(self._on_family_changed)
        layout.addWidget(self.font_list)
        layout.addWidget(QLabel("Preview"))
        self.preview = QLabel(
            "AaBbCc  0123  ( ) { } [ ]\nThe quick brown fox jumps over the lazy dog")
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(70)
        self.preview.setFrameShape(QFrame.Shape.StyledPanel)
        self.preview.setMargin(8)
        layout.addWidget(self.preview)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self._select_family(current_family)
        self._update_preview()

    def _populate_list(self, families):
        self.font_list.blockSignals(True)
        self.font_list.clear()
        for f in families:
            self.font_list.addItem(f)
        self.font_list.blockSignals(False)

    def _filter_fonts(self, text):
        filtered = [f for f in self._all_families if text.lower() in f.lower()]
        self._populate_list(filtered)
        if filtered:
            self.font_list.setCurrentRow(0)
            self.selected_family = filtered[0]
            self._update_preview()

    def _select_family(self, family):
        items = self.font_list.findItems(family, Qt.MatchFlag.MatchExactly)
        if items:
            self.font_list.setCurrentItem(items[0])
            self.font_list.scrollToItem(items[0])

    def _on_family_changed(self, text):
        if text:
            self.selected_family = text
            self._update_preview()

    def _update_preview(self):
        self.preview.setFont(make_font(self.selected_family, self.size_spin.value()))
        self.selected_size = self.size_spin.value()

    def get_result(self):
        return self.selected_family, self.selected_size


# =============================================================================
# SPLIT VIEW DIALOG
# =============================================================================

class SplitViewDialog(QDialog):
    """Ask the user which tab to show in the split pane."""

    def __init__(self, parent, tab_names: List[str], current_index: int):
        super().__init__(parent)
        self.setWindowTitle("Split View — Select Second Tab")
        self.resize(360, 140)
        if parent:
            self.setStyleSheet(parent.styleSheet())
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Show which tab in the split pane?"))
        self.combo = QComboBox()
        for i, name in enumerate(tab_names):
            self.combo.addItem(name, i)
        # Default to something other than current
        default = 0 if current_index != 0 else (1 if len(tab_names) > 1 else 0)
        self.combo.setCurrentIndex(default)
        layout.addWidget(self.combo)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_tab_index(self) -> int:
        return self.combo.currentData()


# =============================================================================
# HELPERS
# =============================================================================

def load_bundled_fonts():
    """Load fonts from AppData/EnhancedNotepad/fonts/ (primary)
    and script-relative fonts/ (fallback)."""
    loaded = []
    search_dirs = [
        APP_DIR / "fonts",
        Path(__file__).parent / "fonts",
    ]
    for font_dir in search_dirs:
        if not font_dir.exists():
            continue
        for ext in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
            for font_file in font_dir.glob(ext):
                fid = QFontDatabase.addApplicationFont(str(font_file))
                if fid != -1:
                    families = QFontDatabase.applicationFontFamilies(fid)
                    loaded.extend(families)
    return loaded


def resolve_font_family(preferred: str) -> str:
    preferred_order = ["Cascadia Mono", "JetBrains Mono", "Comic Neue", "Playfair Display"]
    available = QFontDatabase.families()
    if preferred and preferred in available:
        return preferred
    for family in preferred_order:
        if family in available:
            return family
    return ""


def make_font(family: str, size: int) -> QFont:
    """Create a QFont with OpenType ligatures explicitly enabled."""
    font = QFont(family, size)
    # Enable standard ligatures (calt, liga, clig) via font feature settings
    font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)
    # QFont.setFontFeatures is available in Qt6 / PySide6
    try:
        font.setFontFeatures({
            "liga": True,   # standard ligatures  (-> => != etc.)
            "calt": True,   # contextual alternates
            "clig": True,   # contextual ligatures
        })
    except AttributeError:
        # Older Qt6 build without setFontFeatures — fall back silently
        pass
    return font


# =============================================================================
# MAIN APPLICATION
# =============================================================================

class NotepadApp(QMainWindow):
    MAX_CLOSED_TABS = 20

    def __init__(self, files_to_open=None):
        super().__init__()
        self.loaded_font_families = load_bundled_fonts()
        self.preferences = self._load_preferences()
        self.active_font_family = resolve_font_family(self.preferences.font_family)
        self.current_font_size = self.preferences.font_size
        self.highlight_syntax = self.preferences.highlight_syntax
        self.last_find_term = ""
        self.last_find_case_sensitive = False
        self.tabs: Dict[int, TabData] = {}
        self.tab_counter = 0
        self.closed_tabs: List[ClosedTab] = []
        self._is_fullscreen = False
        self._split_widget = None
        self._split_second_editor: Optional[CodeEditor] = None
        self._split_tab_id: Optional[int] = None

        # Spell checker
        self.spell_checker = None
        self._init_spell_checker()

        # Autosave
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self._autosave_all)
        if self.preferences.autosave_enabled:
            self.autosave_timer.start(self.preferences.autosave_interval * 1000)

        self._init_ui()
        self._create_menus()
        self._setup_shortcuts()
        self._apply_theme(self.preferences.theme)

        if files_to_open:
            for fp in files_to_open:
                self._open_file_path(fp)
            if not self.tabs:
                self._new_tab()
        elif self.preferences.restore_session:
            if not self._restore_session():
                self._new_tab()
        else:
            self._new_tab()

        self._apply_preferences()
        self.setWindowTitle("Untitled - Enhanced Notepad")
        self.resize(900, 650)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

    # -------------------------------------------------------------------------
    # SPELL CHECKER INIT
    # -------------------------------------------------------------------------

    def _init_spell_checker(self):
        if SPELLCHECK_AVAILABLE:
            try:
                self.spell_checker = _SpellChecker()
                # Load personal dictionary if exists
                personal_dict = Path(DICT_FILE)
                if personal_dict.exists():
                    with open(personal_dict, "r", encoding="utf-8") as f:
                        words = [w.strip().lower() for w in f if w.strip()]
                    self.spell_checker.word_frequency.load_words(words)
            except Exception as e:
                print(f"Spell checker init failed: {e}")
                self.spell_checker = None

    def _add_to_dictionary(self, word: str):
        if self.spell_checker:
            self.spell_checker.word_frequency.load_words([word.lower()])
            # Persist
            personal_dict = Path(DICT_FILE)
            with open(personal_dict, "a", encoding="utf-8") as f:
                f.write(word.lower() + "\n")
            # Rehighlight all tabs
            for tab_data in self.tabs.values():
                if tab_data.text_widget.highlighter:
                    tab_data.text_widget.highlighter.rehighlight()

    # -------------------------------------------------------------------------
    # UI INIT
    # -------------------------------------------------------------------------

    def _init_ui(self):
        # Central widget holds the tab widget (and optionally a splitter)
        self._central_container = QWidget()
        self._central_layout = QHBoxLayout(self._central_container)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._central_layout.setSpacing(0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab_by_index)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabBar().installEventFilter(self)
        self._central_layout.addWidget(self.tab_widget)

        self.setCentralWidget(self._central_container)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.show()

    def eventFilter(self, obj, event):
        if obj == self.tab_widget.tabBar():
            if event.type() == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.MiddleButton:
                    index = self.tab_widget.tabBar().tabAt(event.pos())
                    if index >= 0:
                        self._close_tab_by_index(index)
                        return True
        return super().eventFilter(obj, event)

    # -------------------------------------------------------------------------
    # MENUS
    # -------------------------------------------------------------------------

    def _create_menus(self):
        mb = self.menuBar()

        # ── File ─────────────────────────────────────────────────────────────
        fm = mb.addMenu("&File")
        self._add_action(fm, "New &Tab", "Ctrl+T", lambda: self._new_tab())
        self._add_action(fm, "New &Window", "Ctrl+Shift+N", self.new_window)
        self._add_action(fm, "&Open...", QKeySequence.StandardKey.Open, self.open_file)
        self.recent_menu = QMenu("&Recent Files", self)
        fm.addMenu(self.recent_menu)
        self._update_recent_files_menu()
        fm.addSeparator()
        self._add_action(fm, "&Save", QKeySequence.StandardKey.Save, lambda: self._save_file())
        self._add_action(fm, "Save &As...", "Ctrl+Shift+S", lambda: self._save_file_as())
        self._add_action(fm, "Save A&ll", None, self._save_all)
        fm.addSeparator()
        autosave_menu = fm.addMenu("&Autosave")
        self.autosave_enabled_action = QAction("&Enable Autosave", self)
        self.autosave_enabled_action.setCheckable(True)
        self.autosave_enabled_action.setChecked(self.preferences.autosave_enabled)
        self.autosave_enabled_action.triggered.connect(self._toggle_autosave)
        autosave_menu.addAction(self.autosave_enabled_action)
        self._add_action(autosave_menu, "Autosave &Settings...", None, self._autosave_settings)
        autosave_menu.addSeparator()
        self._add_action(autosave_menu, "Save &Now", "Ctrl+Alt+S", self._autosave_all)
        fm.addSeparator()
        self._add_action(fm, "&Export to PDF...", None, self._export_pdf)
        fm.addSeparator()
        self._add_action(fm, "&Close Tab", "Ctrl+W", lambda: self._close_tab())
        self.reopen_action = QAction("&Reopen Closed Tab", self)
        self.reopen_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self.reopen_action.triggered.connect(self._reopen_closed_tab)
        self.reopen_action.setEnabled(False)
        fm.addAction(self.reopen_action)
        self.reopen_menu = QMenu("Reopen &History", self)
        fm.addMenu(self.reopen_menu)
        self._add_action(fm, "Close &All Tabs", None, self._close_all_tabs)
        fm.addSeparator()
        self._add_action(fm, "E&xit", "Ctrl+Q", self.close)

        # ── Edit ─────────────────────────────────────────────────────────────
        em = mb.addMenu("&Edit")
        self._add_action(em, "&Undo", QKeySequence.StandardKey.Undo, self._undo)
        self._add_action(em, "&Redo", QKeySequence.StandardKey.Redo, self._redo)
        em.addSeparator()
        self._add_action(em, "Cu&t", QKeySequence.StandardKey.Cut, self._cut)
        self._add_action(em, "&Copy", QKeySequence.StandardKey.Copy, self._copy)
        self._add_action(em, "&Paste", QKeySequence.StandardKey.Paste, self._paste)
        self._add_action(em, "&Delete", "Del", self._delete)
        em.addSeparator()
        self._add_action(em, "&Find...", QKeySequence.StandardKey.Find, self._find_dialog)
        self._add_action(em, "Find &Next", "F3", self._find_next)
        self._add_action(em, "Find &Previous", "Shift+F3", self._find_prev)
        self._add_action(em, "&Replace...", QKeySequence.StandardKey.Replace, self._replace_dialog)
        self._add_action(em, "&Go To...", "Ctrl+G", self._goto_line)
        em.addSeparator()
        self._add_action(em, "Select &All", QKeySequence.StandardKey.SelectAll, self._select_all)
        self._add_action(em, "&Time/Date", "F5", self._insert_time_date)
        em.addSeparator()
        self._add_action(em, "&Evaluate Formula", "Ctrl+E", self._evaluate_formula)
        self._add_action(em, "&List Variables", None, self._list_variables)
        self._add_action(em, "&Clear Variables", None, self._clear_variables)
        em.addSeparator()
        self.auto_eval_action = QAction("&Auto-Evaluate on '='", self)
        self.auto_eval_action.setCheckable(True)
        self.auto_eval_action.setChecked(True)
        self.auto_eval_action.triggered.connect(self._toggle_auto_eval)
        em.addAction(self.auto_eval_action)

        # ── Format ───────────────────────────────────────────────────────────
        fom = mb.addMenu("F&ormat")
        self.word_wrap_action = QAction("&Word Wrap", self)
        self.word_wrap_action.setCheckable(True)
        self.word_wrap_action.setChecked(True)
        self.word_wrap_action.triggered.connect(self._toggle_word_wrap)
        fom.addAction(self.word_wrap_action)
        self._add_action(fom, "&Font...", None, self._font_dialog)

        # ── View ─────────────────────────────────────────────────────────────
        vm = mb.addMenu("&View")
        zoom_menu = vm.addMenu("&Zoom")
        self._add_action(zoom_menu, "Zoom &In", QKeySequence.StandardKey.ZoomIn, self._zoom_in)
        self._add_action(zoom_menu, "Zoom &Out", QKeySequence.StandardKey.ZoomOut, self._zoom_out)
        self._add_action(zoom_menu, "&Restore Default Zoom", "Ctrl+0", self._zoom_reset)

        self.status_bar_action = QAction("&Status Bar", self)
        self.status_bar_action.setCheckable(True)
        self.status_bar_action.setChecked(True)
        self.status_bar_action.triggered.connect(self._toggle_status_bar)
        vm.addAction(self.status_bar_action)

        self.line_numbers_action = QAction("&Line Numbers", self)
        self.line_numbers_action.setCheckable(True)
        self.line_numbers_action.triggered.connect(self._toggle_line_numbers)
        vm.addAction(self.line_numbers_action)

        self.fullscreen_action = QAction("&Full Screen", self)
        self.fullscreen_action.setShortcut(QKeySequence("F11"))
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.triggered.connect(self._toggle_fullscreen)
        vm.addAction(self.fullscreen_action)

        # Split view
        self.split_view_action = QAction("&Split View", self)
        self.split_view_action.setShortcut(QKeySequence("Ctrl+Shift+2"))
        self.split_view_action.setCheckable(True)
        self.split_view_action.triggered.connect(self._toggle_split_view)
        vm.addAction(self.split_view_action)

        theme_menu = vm.addMenu("&Theme")
        self._add_action(theme_menu, "&Light", None, lambda: self._change_theme("light"))
        self._add_action(theme_menu, "&Dark", None, lambda: self._change_theme("dark"))

        vm.addSeparator()
        hl_menu = vm.addMenu("&Highlight Syntax")
        self.highlight_action_group = QActionGroup(self)
        self.highlight_action_group.setExclusive(True)
        self.highlight_off_action = self._checkable_action(
            hl_menu, "&Off", self.highlight_action_group,
            lambda: self._toggle_highlight_syntax("off"))
        self.highlight_code_action = self._checkable_action(
            hl_menu, "&Code", self.highlight_action_group,
            lambda: self._toggle_highlight_syntax("code"))
        self.highlight_text_action = self._checkable_action(
            hl_menu, "&Text", self.highlight_action_group,
            lambda: self._toggle_highlight_syntax("text"))
        self.highlight_off_action.setChecked(True)

        # Spell check
        vm.addSeparator()
        self.spellcheck_action = QAction("&Spell Check", self)
        self.spellcheck_action.setCheckable(True)
        self.spellcheck_action.setChecked(self.preferences.spellcheck_enabled)
        self.spellcheck_action.triggered.connect(self._toggle_spellcheck)
        if not SPELLCHECK_AVAILABLE:
            self.spellcheck_action.setEnabled(False)
            self.spellcheck_action.setText("&Spell Check (install pyspellchecker)")
        vm.addAction(self.spellcheck_action)

        vm.addSeparator()
        session_menu = vm.addMenu("&Session")
        self.restore_session_action = QAction("&Restore Session on Startup", self)
        self.restore_session_action.setCheckable(True)
        self.restore_session_action.setChecked(self.preferences.restore_session)
        self.restore_session_action.triggered.connect(self._toggle_restore_session)
        session_menu.addAction(self.restore_session_action)
        self._add_action(session_menu, "&Clear Saved Session", None, self._clear_session)

        # ── Help ─────────────────────────────────────────────────────────────
        hm = mb.addMenu("&Help")
        self._add_action(hm, "&Formula Help", None, self._show_formula_help)
        hm.addSeparator()
        self._add_action(hm, "&About", None, self._show_about)

    def _add_action(self, menu, label, shortcut, slot):
        action = QAction(label, self)
        if shortcut:
            if isinstance(shortcut, str):
                action.setShortcut(QKeySequence(shortcut))
            else:
                action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _checkable_action(self, menu, label, group, slot):
        action = QAction(label, self)
        action.setCheckable(True)
        action.setActionGroup(group)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _setup_shortcuts(self):
        for shortcut, slot in [("Ctrl+Tab", self._next_tab),
                                ("Ctrl+Shift+Tab", self._prev_tab)]:
            a = QAction(self)
            a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            self.addAction(a)

    # =========================================================================
    # SPLIT VIEW
    # =========================================================================

    def _toggle_split_view(self):
        if self._split_widget is not None:
            self._close_split_view()
        else:
            self._open_split_view()

    def _open_split_view(self):
        if self.tab_widget.count() < 2:
            QMessageBox.information(self, "Split View",
                                    "You need at least two tabs to use split view.")
            self.split_view_action.setChecked(False)
            return

        tab_names = [self.tab_widget.tabText(i) for i in range(self.tab_widget.count())]
        current_index = self.tab_widget.currentIndex()
        dlg = SplitViewDialog(self, tab_names, current_index)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.split_view_action.setChecked(False)
            return

        split_tab_index = dlg.selected_tab_index()
        split_tab_id = self._get_tab_id_from_index(split_tab_index)
        if split_tab_id is None:
            self.split_view_action.setChecked(False)
            return

        self._split_tab_id = split_tab_id

        # Second tab widget — fully independent, shows the chosen tab's editor directly
        self._split_tab_widget = QTabWidget()
        self._split_tab_widget.setTabsClosable(False)
        self._split_tab_widget.setMovable(False)

        # Add the chosen tab's actual text widget into the second tab bar
        chosen_tw = self.tabs[split_tab_id].text_widget
        chosen_title = tab_names[split_tab_index]

        # We can't put the same widget in two tab widgets simultaneously,
        # so we create a thin wrapper that shares the same QTextDocument.
        second_editor = CodeEditor()
        second_editor.setDocument(chosen_tw.document())   # shared document = live sync, both editable
        second_editor.setFont(chosen_tw.font())
        second_editor._notepad_app = self
        second_editor.current_theme = self.preferences.theme
        second_editor.set_line_numbers_visible(self.line_numbers_action.isChecked())
        self._apply_theme_to_widget(second_editor, self.preferences.theme)

        self._split_second_editor = second_editor
        self._split_tab_widget.addTab(second_editor, chosen_title)

        # Build splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tab_widget)
        splitter.addWidget(self._split_tab_widget)
        splitter.setSizes([500, 400])

        # Swap central layout
        for i in reversed(range(self._central_layout.count())):
            self._central_layout.itemAt(i).widget().setParent(None)
        self._central_layout.addWidget(splitter)

        self._split_widget = splitter
        self.split_view_action.setChecked(True)

    def _close_split_view(self):
        if self._split_widget is None:
            return

        # The second editor shares the document — just discard it safely
        if hasattr(self, '_split_second_editor') and self._split_second_editor:
            # Detach document so original is untouched
            self._split_second_editor.setDocument(
                self._split_second_editor.document().__class__())
            self._split_second_editor = None

        self._split_widget.setParent(None)
        self._split_widget = None
        self._split_tab_id = None

        # Restore tab widget to central layout
        self._central_layout.addWidget(self.tab_widget)
        self.split_view_action.setChecked(False)

    # =========================================================================
    # EXPORT TO PDF
    # =========================================================================

    def _export_pdf(self):
        tab_data = self._get_current_tab()
        if not tab_data:
            return
        default_name = ""
        if tab_data.current_file:
            default_name = str(Path(tab_data.current_file).with_suffix(".pdf"))
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export to PDF", default_name, "PDF Files (*.pdf)")
        if not filepath:
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(filepath)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)

        # Use a temporary QTextEdit with the same font/colors to render
        temp_edit = QTextEdit()  # QTextEdit kept here for print_() support
        temp_edit.setFont(tab_data.text_widget.font())
        temp_edit.setPlainText(tab_data.text_widget.toPlainText())

        # Apply theme colors
        theme = self.preferences.theme
        if theme == "dark":
            palette = temp_edit.palette()
            palette.setColor(QPalette.ColorRole.Base, QColor("#1e1e1e"))
            palette.setColor(QPalette.ColorRole.Text, QColor("#d4d4d4"))
            temp_edit.setPalette(palette)

        temp_edit.print_(printer)

        QMessageBox.information(self, "Export to PDF",
                                f"Exported successfully to:\n{filepath}")

    # =========================================================================
    # FULLSCREEN
    # =========================================================================

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        self._is_fullscreen = True
        self.fullscreen_action.setChecked(True)
        self.menuBar().hide()
        self.tab_widget.tabBar().hide()
        if not self.status_bar_action.isChecked():
            self.status_bar.hide()
        self.showFullScreen()

    def _exit_fullscreen(self):
        self._is_fullscreen = False
        self.fullscreen_action.setChecked(False)
        self.menuBar().show()
        self.tab_widget.tabBar().show()
        if self.status_bar_action.isChecked():
            self.status_bar.show()
        self.showNormal()

    def keyPressEvent(self, event):
        if self._is_fullscreen and event.key() in (Qt.Key.Key_F11, Qt.Key.Key_Escape):
            self._exit_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    # =========================================================================
    # SPELL CHECK
    # =========================================================================

    def _toggle_spellcheck(self):
        enabled = self.spellcheck_action.isChecked()
        self.preferences.spellcheck_enabled = enabled
        self._save_preferences()
        for tab_data in self.tabs.values():
            tab_data.text_widget.set_syntax_highlighting(
                self.highlight_syntax, self.preferences.theme,
                self.spell_checker, enabled)
        self._update_status_bar()

    # =========================================================================
    # REOPEN CLOSED TABS
    # =========================================================================

    def _push_closed_tab(self, tab_data: TabData, tab_id: int):
        title = (os.path.basename(tab_data.current_file)
                 if tab_data.current_file else f"Untitled {tab_id}")
        self.closed_tabs.append(ClosedTab(
            title=title,
            content=tab_data.text_widget.toPlainText(),
            current_file=tab_data.current_file,
            cursor_position=tab_data.text_widget.textCursor().position()))
        if len(self.closed_tabs) > self.MAX_CLOSED_TABS:
            self.closed_tabs.pop(0)
        self.reopen_action.setEnabled(True)
        self._update_reopen_menu()

    def _reopen_closed_tab(self):
        if not self.closed_tabs:
            return
        self._restore_closed_tab(self.closed_tabs.pop())
        self.reopen_action.setEnabled(bool(self.closed_tabs))
        self._update_reopen_menu()

    def _restore_closed_tab(self, closed: ClosedTab):
        tab_id = self._new_tab(filename=closed.current_file, content=closed.content)
        if tab_id in self.tabs:
            tw = self.tabs[tab_id].text_widget
            cursor = tw.textCursor()
            cursor.setPosition(min(closed.cursor_position, len(closed.content)))
            tw.setTextCursor(cursor)

    def _update_reopen_menu(self):
        self.reopen_menu.clear()
        if not self.closed_tabs:
            a = QAction("(empty)", self)
            a.setEnabled(False)
            self.reopen_menu.addAction(a)
            return
        for i, closed in enumerate(reversed(self.closed_tabs)):
            label = f"{'&' + str(i+1) if i < 9 else ''} {closed.title}"
            idx = len(self.closed_tabs) - 1 - i
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked, ix=idx: self._reopen_specific(ix))
            self.reopen_menu.addAction(action)

    def _reopen_specific(self, index: int):
        if 0 <= index < len(self.closed_tabs):
            self._restore_closed_tab(self.closed_tabs.pop(index))
            self.reopen_action.setEnabled(bool(self.closed_tabs))
            self._update_reopen_menu()

    # =========================================================================
    # SESSION
    # =========================================================================

    def _save_session(self):
        try:
            session_tabs = []
            for i in range(self.tab_widget.count()):
                tab_id = self._get_tab_id_from_index(i)
                if tab_id and tab_id in self.tabs:
                    td = self.tabs[tab_id]
                    tw = td.text_widget
                    session_tabs.append(asdict(TabSession(
                        content=tw.toPlainText(),
                        current_file=td.current_file,
                        cursor_position=tw.textCursor().position(),
                        scroll_position=tw.verticalScrollBar().value())))
            with open(SESSION_FILE, 'w') as f:
                json.dump(asdict(AppSession(
                    tabs=session_tabs,
                    active_tab_index=self.tab_widget.currentIndex())), f, indent=2)
        except Exception as e:
            print(f"Could not save session: {e}")

    def _restore_session(self) -> bool:
        try:
            if not os.path.exists(SESSION_FILE):
                return False
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
            app_session = AppSession(**data)
            if not app_session.tabs:
                return False
            for ts_dict in app_session.tabs:
                ts = TabSession(**ts_dict)
                tab_id = self._new_tab(filename=ts.current_file, content=ts.content)
                if tab_id in self.tabs:
                    tw = self.tabs[tab_id].text_widget
                    cursor = tw.textCursor()
                    cursor.setPosition(min(ts.cursor_position, len(ts.content)))
                    tw.setTextCursor(cursor)
                    QTimer.singleShot(100,
                        lambda w=tw, p=ts.scroll_position: w.verticalScrollBar().setValue(p))
                    if ts.current_file:
                        self.tabs[tab_id].modified = False
                        self.tabs[tab_id].last_saved_content = ts.content
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
                QMessageBox.information(self, "Clear Session", "Saved session cleared.")
            else:
                QMessageBox.information(self, "Clear Session", "No saved session found.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not clear session: {e}")

    def _toggle_restore_session(self):
        self.preferences.restore_session = self.restore_session_action.isChecked()
        self._save_preferences()

    # =========================================================================
    # AUTOSAVE
    # =========================================================================

    def _toggle_autosave(self):
        enabled = self.autosave_enabled_action.isChecked()
        self.preferences.autosave_enabled = enabled
        self._save_preferences()
        if enabled:
            self.autosave_timer.start(self.preferences.autosave_interval * 1000)
        else:
            self.autosave_timer.stop()

    def _autosave_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Autosave Settings")
        dialog.resize(400, 180)
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout()
        enable_cb = QCheckBox("Enable autosave")
        enable_cb.setChecked(self.preferences.autosave_enabled)
        layout.addWidget(enable_cb)
        layout.addWidget(QLabel("Autosave interval (seconds):"))
        row = QHBoxLayout()
        spinbox = QSpinBox()
        spinbox.setRange(10, 600)
        spinbox.setValue(self.preferences.autosave_interval)
        row.addWidget(spinbox)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(QLabel("Note: only saves files that have been saved at least once."))
        layout.addStretch()
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dialog.accept)
        bb.rejected.connect(dialog.reject)
        layout.addWidget(bb)
        dialog.setLayout(layout)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.preferences.autosave_enabled = enable_cb.isChecked()
            self.preferences.autosave_interval = spinbox.value()
            self.autosave_enabled_action.setChecked(self.preferences.autosave_enabled)
            self.autosave_timer.stop()
            if self.preferences.autosave_enabled:
                self.autosave_timer.start(self.preferences.autosave_interval * 1000)
            self._save_preferences()

    def _autosave_all(self):
        saved = 0
        for tab_id, td in self.tabs.items():
            if td.current_file:
                content = td.text_widget.toPlainText()
                if content != td.last_saved_content:
                    try:
                        with open(td.current_file, "w", encoding='utf-8') as f:
                            f.write(content)
                        td.last_saved_content = content
                        td.modified = False
                        self._update_tab_title(tab_id, modified=False)
                        saved += 1
                    except Exception as e:
                        print(f"Autosave failed for {td.current_file}: {e}")
        if saved > 0:
            self.status_bar.showMessage(f"Autosaved {saved} file(s)", 2000)

    # =========================================================================
    # TAB MANAGEMENT
    # =========================================================================

    def _new_tab(self, filename=None, content=""):
        self.tab_counter += 1
        tw = CodeEditor()
        tw.setFont(make_font(self.active_font_family, self.current_font_size))
        tw._notepad_app = self
        tw.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if self.word_wrap_action.isChecked()
            else QPlainTextEdit.LineWrapMode.NoWrap)
        td = TabData(text_widget=tw, current_file=filename)
        self.tabs[self.tab_counter] = td
        self._apply_theme_to_tab(td, self.preferences.theme)
        tw.set_line_numbers_visible(self.line_numbers_action.isChecked())
        tw.set_syntax_highlighting(
            self.highlight_syntax, self.preferences.theme,
            self.spell_checker, self.preferences.spellcheck_enabled)
        if content:
            tw.setPlainText(content)
            td.last_saved_content = content if filename else ""
        tab_title = os.path.basename(filename) if filename else f"Untitled {self.tab_counter}"
        index = self.tab_widget.addTab(tw, tab_title)
        self.tab_widget.setCurrentIndex(index)
        tab_id = self.tab_counter
        tw.textChanged.connect(lambda: self._on_text_modified(tab_id))
        tw.cursorPositionChanged.connect(self._update_status_bar)
        tw.setFocus()
        return self.tab_counter

    def _close_tab(self, tab_id=None):
        if tab_id is None:
            tab_id = self._get_current_tab_id()
        if tab_id is None or tab_id not in self.tabs:
            return False
        td = self.tabs[tab_id]
        if td.modified:
            fname = os.path.basename(td.current_file) if td.current_file else "Untitled"
            reply = QMessageBox.question(
                self, "Save Changes",
                f"Do you want to save changes to '{fname}'?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Yes:
                self._save_file(tab_id)
            elif reply == QMessageBox.StandardButton.Cancel:
                return False
        self._push_closed_tab(td, tab_id)
        # Close split if this tab is the split target
        if self._split_tab_id == tab_id:
            self._close_split_view()
        for i in range(self.tab_widget.count()):
            if self._get_tab_id_from_index(i) == tab_id:
                self.tab_widget.removeTab(i)
                break
        del self.tabs[tab_id]
        if not self.tabs:
            self._save_preferences()
            self._save_session()
            QTimer.singleShot(0, QApplication.quit)
            return True
        self._update_window_title()
        return True

    def _close_tab_by_index(self, index):
        tab_id = self._get_tab_id_from_index(index)
        if tab_id:
            self._close_tab(tab_id)

    def _get_tab_id_from_index(self, index):
        widget = self.tab_widget.widget(index)
        for tid, td in self.tabs.items():
            if td.text_widget == widget:
                return tid
        return None

    def _get_current_tab_id(self):
        return self._get_tab_id_from_index(self.tab_widget.currentIndex())

    def _get_current_tab(self) -> Optional[TabData]:
        tid = self._get_current_tab_id()
        return self.tabs.get(tid) if tid else None

    def _on_tab_changed(self, index):
        self._update_window_title()
        self._update_status_bar()
        td = self._get_current_tab()
        if td:
            td.text_widget.setFocus()

    def _update_tab_title(self, tab_id, modified=None):
        if tab_id not in self.tabs:
            return
        td = self.tabs[tab_id]
        if modified is not None:
            td.modified = modified
        for i in range(self.tab_widget.count()):
            if self._get_tab_id_from_index(i) == tab_id:
                marker = "*" if td.modified else ""
                base = (os.path.basename(td.current_file)
                        if td.current_file else f"Untitled {tab_id}")
                self.tab_widget.setTabText(i, marker + base)
                break
        self._update_window_title()

    def _update_window_title(self):
        td = self._get_current_tab()
        if td:
            marker = "*" if td.modified else ""
            base = (os.path.basename(td.current_file)
                    if td.current_file
                    else f"Untitled {self._get_current_tab_id()}")
            self.setWindowTitle(f"{marker}{base} - Enhanced Notepad")

    def _next_tab(self):
        n = self.tab_widget.count()
        self.tab_widget.setCurrentIndex((self.tab_widget.currentIndex() + 1) % n)

    def _prev_tab(self):
        n = self.tab_widget.count()
        self.tab_widget.setCurrentIndex((self.tab_widget.currentIndex() - 1) % n)

    # =========================================================================
    # PREFERENCES
    # =========================================================================

    def _load_preferences(self) -> Preferences:
        try:
            if os.path.exists(PREFS_FILE):
                with open(PREFS_FILE, 'r') as f:
                    data = json.load(f)
                    # Remove unknown keys so old prefs files don't crash
                    valid = {k: v for k, v in data.items()
                             if k in Preferences.__dataclass_fields__}
                    return Preferences(**valid)
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
        {
            "off": self.highlight_off_action,
            "code": self.highlight_code_action,
            "text": self.highlight_text_action,
        }.get(self.highlight_syntax, self.highlight_off_action).setChecked(True)
        if SPELLCHECK_AVAILABLE:
            self.spellcheck_action.setChecked(self.preferences.spellcheck_enabled)
        self.auto_eval_action.setChecked(self.preferences.auto_eval_enabled)

    # =========================================================================
    # THEME
    # =========================================================================

    def _apply_theme(self, theme: str):
        for td in self.tabs.values():
            self._apply_theme_to_tab(td, theme)
        if theme == "dark":
            self.setStyleSheet("""
            QMainWindow, QDialog, QMessageBox { background-color:#1e1e1e; color:#d4d4d4; }
            QTextEdit, QPlainTextEdit { background-color:#1e1e1e; color:#d4d4d4;
                selection-background-color:#264f78; selection-color:#ffffff; border:none; }
            QMenuBar { background-color:#2d2d30; color:#d4d4d4; border-bottom:1px solid #3e3e42; }
            QMenuBar::item { background:transparent; padding:4px 8px; }
            QMenuBar::item:selected { background:#3e3e42; }
            QMenuBar::item:pressed { background:#007acc; }
            QMenu { background:#252526; color:#d4d4d4; border:1px solid #3e3e42; }
            QMenu::item { padding:5px 25px 5px 20px; }
            QMenu::item:selected { background:#094771; }
            QMenu::separator { height:1px; background:#3e3e42; margin:4px 0; }
            QTabWidget::pane { border:1px solid #3e3e42; background:#1e1e1e; }
            QTabBar::tab { background:#2d2d30; color:#969696; padding:8px 16px;
                border:1px solid #3e3e42; border-bottom:none; margin-right:2px;
                border-top-left-radius:10px; border-top-right-radius:10px; }
            QTabBar::tab:selected { background:#1e1e1e; color:#d4d4d4; border-bottom:2px solid #007acc; }
            QTabBar::tab:hover { background:#3e3e42; }
            QStatusBar { background:#007acc; color:#ffffff; }
            QDialog { background:#2d2d30; }
            QLabel { color:#d4d4d4; }
            QLineEdit { background:#3c3c3c; color:#d4d4d4; border:1px solid #3e3e42; padding:4px; }
            QPushButton { background:#0e639c; color:#fff; border:1px solid #0e639c;
                padding:5px 15px; border-radius:2px; }
            QPushButton:hover { background:#1177bb; }
            QPushButton:pressed { background:#094771; }
            QPushButton:disabled { background:#3e3e42; color:#656565; }
            QCheckBox { color:#d4d4d4; }
            QCheckBox::indicator { width:13px; height:13px; border:1px solid #3e3e42; background:#3c3c3c; }
            QCheckBox::indicator:checked { background:#007acc; border:1px solid #007acc; }
            QSpinBox { background:#3c3c3c; color:#d4d4d4; border:1px solid #3e3e42; padding:3px; }
            QScrollBar:vertical { background:#1e1e1e; width:14px; border:none; }
            QScrollBar::handle:vertical { background:#424242; min-height:20px; border-radius:2px; }
            QScrollBar::handle:vertical:hover { background:#4e4e4e; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background:#1e1e1e; height:14px; border:none; }
            QScrollBar::handle:horizontal { background:#424242; min-width:20px; border-radius:2px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            QListWidget { background:#252526; color:#d4d4d4; border:1px solid #3e3e42; }
            QListWidget::item:selected { background:#094771; }
            QComboBox { background:#3c3c3c; color:#d4d4d4; border:1px solid #3e3e42; padding:3px; }
            QSplitter::handle { background:#3e3e42; width:3px; }
            """)
        else:
            self.setStyleSheet("""
            QTextEdit, QPlainTextEdit { background:#ffffff; color:#000000;
                selection-background-color:#0078d7; selection-color:#fff; border:none; }
            QTabWidget::pane { border:1px solid #d0d0d0; background:#ffffff; }
            QTabBar::tab { background:#f0f0f0; color:#404040; padding:8px 16px;
                border:1px solid #d0d0d0; border-bottom:none; margin-right:2px;
                border-top-left-radius:10px; border-top-right-radius:10px; }
            QTabBar::tab:selected { background:#fff; color:#000; border-bottom:2px solid #0078d7; }
            QTabBar::tab:hover { background:#e0e0e0; }
            QSplitter::handle { background:#d0d0d0; width:3px; }
            """)

    def _apply_theme_to_tab(self, td: TabData, theme: str):
        self._apply_theme_to_widget(td.text_widget, theme)

    def _apply_theme_to_widget(self, widget: CodeEditor, theme: str):
        widget.current_theme = theme
        widget.update_syntax_theme(theme)
        if widget.show_line_numbers:
            widget.line_number_area.update()
        widget.update()
        widget.viewport().update()

    # =========================================================================
    # RECENT FILES
    # =========================================================================

    def _update_recent_files(self, filepath: str):
        if filepath in self.preferences.recent_files:
            self.preferences.recent_files.remove(filepath)
        self.preferences.recent_files.insert(0, filepath)
        self.preferences.recent_files = \
            self.preferences.recent_files[:self.preferences.max_recent_files]
        self._save_preferences()
        self._update_recent_files_menu()

    def _update_recent_files_menu(self):
        self.recent_menu.clear()
        if not self.preferences.recent_files:
            a = QAction("(No recent files)", self)
            a.setEnabled(False)
            self.recent_menu.addAction(a)
        else:
            keys = '123456789ABCDEF'
            for i, fp in enumerate(self.preferences.recent_files):
                if os.path.exists(fp):
                    a = QAction(
                        f"&{keys[i] if i < len(keys) else i+1}. {os.path.basename(fp)}", self)
                    a.triggered.connect(lambda checked, f=fp: self._open_recent_file(f))
                    self.recent_menu.addAction(a)
            self.recent_menu.addSeparator()
            self._add_action(self.recent_menu, "&Recent Files Settings...",
                             None, self._recent_files_settings)
            self._add_action(self.recent_menu, "C&lear Recent Files",
                             None, self._clear_recent_files)

    def _open_recent_file(self, filepath: str):
        if not os.path.exists(filepath):
            QMessageBox.critical(self, "File Not Found",
                                 f"'{filepath}' no longer exists.")
            self.preferences.recent_files.remove(filepath)
            self._save_preferences()
            self._update_recent_files_menu()
            return
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                content = f.read()
            self._new_tab(filename=filepath, content=content)
            self._update_recent_files(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Open File Error", str(e))

    def _clear_recent_files(self):
        self.preferences.recent_files = []
        self._save_preferences()
        self._update_recent_files_menu()

    def _recent_files_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Recent Files Settings")
        dialog.resize(350, 130)
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(QLabel("Maximum number of recent files:"))
        sb = QSpinBox()
        sb.setRange(5, 20)
        sb.setValue(self.preferences.max_recent_files)
        row.addWidget(sb)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dialog.accept)
        bb.rejected.connect(dialog.reject)
        layout.addWidget(bb)
        dialog.setLayout(layout)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.preferences.max_recent_files = sb.value()
            self.preferences.recent_files = \
                self.preferences.recent_files[:self.preferences.max_recent_files]
            self._save_preferences()
            self._update_recent_files_menu()

    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================

    def _open_file_path(self, filepath: str):
        filepath = os.path.abspath(filepath)
        if not os.path.exists(filepath):
            QMessageBox.critical(self, "File Not Found", f"'{filepath}' does not exist.")
            return
        try:
            with open(filepath, "r", encoding='utf-8') as f:
                content = f.read()
            self._new_tab(filename=filepath, content=content)
            self._update_recent_files(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Open File Error", str(e))

    def new_window(self):
        NotepadApp().show()

    def open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", "Text Files (*.txt);;All Files (*.*)")
        if filepath:
            self._open_file_path(filepath)

    def _save_file(self, tab_id=None):
        if tab_id is None:
            tab_id = self._get_current_tab_id()
        if tab_id is None:
            return
        td = self.tabs[tab_id]
        if td.current_file:
            self._write_file(tab_id, td.current_file)
        else:
            self._save_file_as(tab_id)

    def _save_file_as(self, tab_id=None):
        if tab_id is None:
            tab_id = self._get_current_tab_id()
        if tab_id is None:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save File", "", "Text Files (*.txt);;All Files (*.*)")
        if not filepath:
            return
        self._write_file(tab_id, filepath)
        self.tabs[tab_id].current_file = filepath
        self._update_tab_title(tab_id)
        self._update_recent_files(filepath)

    def _write_file(self, tab_id, filepath):
        td = self.tabs[tab_id]
        try:
            text = td.text_widget.toPlainText()
            with open(filepath, "w", encoding='utf-8') as f:
                f.write(text)
            td.last_saved_content = text
            self._update_tab_title(tab_id, modified=False)
        except Exception as e:
            QMessageBox.critical(self, "Save File Error", str(e))

    def _save_all(self):
        for tid in list(self.tabs.keys()):
            self._save_file(tid)

    def _close_all_tabs(self):
        for tid in list(self.tabs.keys()):
            if not self._close_tab(tid):
                return

    # =========================================================================
    # EDIT OPERATIONS
    # =========================================================================

    def _undo(self):
        td = self._get_current_tab()
        if td: td.text_widget.undo()

    def _redo(self):
        td = self._get_current_tab()
        if td: td.text_widget.redo()

    def _cut(self):
        td = self._get_current_tab()
        if td: td.text_widget.cut()

    def _copy(self):
        td = self._get_current_tab()
        if td: td.text_widget.copy()

    def _paste(self):
        td = self._get_current_tab()
        if td: td.text_widget.paste()

    def _delete(self):
        td = self._get_current_tab()
        if td: td.text_widget.textCursor().removeSelectedText()

    def _select_all(self):
        td = self._get_current_tab()
        if td: td.text_widget.selectAll()

    def _insert_time_date(self):
        td = self._get_current_tab()
        if td:
            td.text_widget.insertPlainText(
                datetime.datetime.now().strftime("%H:%M %m/%d/%Y"))

    def _find_dialog(self):
        td = self._get_current_tab()
        if td:
            FindDialog(self, td.text_widget, self).show()

    def _find_next(self):
        td = self._get_current_tab()
        if not td or not self.last_find_term:
            return
        flags = QTextDocument.FindFlag(0)
        if self.last_find_case_sensitive:
            flags = QTextDocument.FindFlag.FindCaseSensitively
        cursor = td.text_widget.textCursor()
        found = td.text_widget.document().find(self.last_find_term, cursor, flags)
        if found.isNull():
            found = td.text_widget.document().find(self.last_find_term, 0, flags)
        if found.isNull():
            QMessageBox.information(self, "Find Next",
                                    f'Cannot find "{self.last_find_term}"')
        else:
            td.text_widget.setTextCursor(found)

    def _find_prev(self):
        td = self._get_current_tab()
        if not td or not self.last_find_term:
            return
        flags = QTextDocument.FindFlag.FindBackward
        if self.last_find_case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        found = td.text_widget.document().find(
            self.last_find_term, td.text_widget.textCursor(), flags)
        if found.isNull():
            QMessageBox.information(self, "Find Previous",
                                    f'Cannot find "{self.last_find_term}"')
        else:
            td.text_widget.setTextCursor(found)

    def _replace_dialog(self):
        td = self._get_current_tab()
        if td:
            ReplaceDialog(self, td.text_widget).show()

    def _goto_line(self):
        td = self._get_current_tab()
        if not td:
            return
        line_num, ok = QInputDialog.getInt(self, "Go To Line", "Line number:", 1, 1, 1000000)
        if ok:
            cursor = QTextCursor(
                td.text_widget.document().findBlockByLineNumber(line_num - 1))
            td.text_widget.setTextCursor(cursor)

    # =========================================================================
    # FORMULA EVALUATION
    # =========================================================================

    def pre_process_expression(self, expr: str) -> str:
        expr = expr.replace('^', '**')
        # Insert * between digit and letter/bracket ONLY when the digit is not
        # part of a known function name (e.g. log10, log2).
        # Strategy: protect known function names, do substitution, restore.
        _known = ['log10', 'log2']
        _placeholders = {}
        for i, fn in enumerate(_known):
            ph = f'__FN{i}__'
            _placeholders[ph] = fn
            expr = expr.replace(fn, ph)
        expr = re.sub(r'(\d)(?![eE][+-]?\d)([a-zA-Z\(])', r'\1*\2', expr)
        expr = re.sub(r'(\))([0-9a-zA-Z])', r'\1*\2', expr)
        for ph, fn in _placeholders.items():
            expr = expr.replace(ph, fn)
        return expr

    def _parse_formula_line(self, content, evaluator):
        var_name = var_separator = formula_to_eval = None
        prefix = ''
        if ':' in content:
            parts = content.split(':', 1)
            pv = parts[0].strip()
            if (pv.replace(' ', '').replace('_', '').isalnum()
                    and not pv[0].isdigit()):
                var_name = pv.replace(' ', '_')
                var_separator = ':'
                remainder = parts[1].strip()
                if '=' in remainder:
                    cp = remainder.split('=')
                    formula_to_eval = cp[-1].strip()
                    prefix = '='.join(cp[:-1]).strip() + ' = ' if len(cp) > 1 else ''
                else:
                    formula_to_eval = remainder
        if var_name is None:
            parts = content.split('=')
            fp = parts[0].strip()
            if (fp.replace('_', '').replace(' ', '').isalnum()
                    and not fp[0].isdigit()
                    and not any(op in fp for op in '+-*/()')):
                var_name = fp.replace(' ', '_')
                var_separator = '='
                if len(parts) > 1:
                    remainder = '='.join(parts[1:]).strip()
                    if '=' in remainder:
                        cp = remainder.split('=')
                        formula_to_eval = cp[-1].strip()
                        prefix = '='.join(cp[:-1]).strip() + ' = ' if len(cp) > 1 else ''
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
        if isinstance(result, (float, int)):
            if abs(result) >= 1e10 or (abs(result) < 1e-4 and result != 0):
                return f"{result:.4e}"
            return f"{result:.10f}".rstrip('0').rstrip('.')
        return str(result)

    def _evaluate_current_line(self):
        td = self._get_current_tab()
        if not td:
            return
        tw = td.text_widget
        cursor = tw.textCursor()
        block = cursor.block()
        stripped = block.text().rstrip()
        if not stripped.endswith('='):
            return
        content = stripped[:-1].strip()
        var_name, sep, formula, prefix = self._parse_formula_line(content, td.evaluator)
        if not formula:
            return
        ok, result, _ = td.evaluator.evaluate(self.pre_process_expression(formula))
        if not ok:
            return
        rs = self._format_result(result)
        if var_name:
            td.evaluator.variables[var_name] = result
            new_line = (f"{var_name}{sep} {prefix}{rs}" if prefix
                        else f"{var_name} {sep} {rs}")
        else:
            new_line = f"{prefix}{rs}" if prefix else f"{formula} = {rs}"
        bs, be = block.position(), block.position() + block.length() - 1
        cursor.setPosition(bs)
        cursor.setPosition(be, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(new_line)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
        tw.setTextCursor(cursor)

    def _evaluate_formula(self):
        td = self._get_current_tab()
        if not td:
            return
        tw = td.text_widget
        cursor = tw.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            start, end = cursor.selectionStart(), cursor.selectionEnd()
        else:
            text = tw.toPlainText()
            start, end = 0, len(text)
        lines = text.split('\n')
        new_lines = []
        modified = False
        last_idx = -1
        for i, line in enumerate(lines):
            stripped = line.rstrip()
            if stripped.endswith('='):
                content = stripped[:-1].strip()
                vn, sep, formula, prefix = self._parse_formula_line(content, td.evaluator)
                if formula:
                    ok, result, _ = td.evaluator.evaluate(
                        self.pre_process_expression(formula))
                    if ok:
                        rs = self._format_result(result)
                        if vn:
                            td.evaluator.variables[vn] = result
                            new_lines.append(f"{vn}{sep} {prefix}{rs}" if prefix
                                             else f"{vn} {sep} {rs}")
                        else:
                            new_lines.append(f"{prefix}{rs}" if prefix
                                             else f"{formula} = {rs}")
                        last_idx = i
                        modified = True
                        continue
            new_lines.append(line)
        if modified:
            if cursor.hasSelection():
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText('\n'.join(new_lines))
            else:
                tw.setPlainText('\n'.join(new_lines))
            if last_idx >= 0:
                b = tw.document().findBlockByLineNumber(last_idx)
                if b.isValid():
                    nc = QTextCursor(b)
                    nc.movePosition(QTextCursor.MoveOperation.EndOfLine)
                    tw.setTextCursor(nc)

    def _list_variables(self):
        td = self._get_current_tab()
        if not td:
            return
        variables = td.evaluator.variables
        if not variables:
            QMessageBox.information(self, "Variables", "No variables currently defined.")
            return
        lines = []
        for name, val in sorted(variables.items()):
            vs = (f"{val:.10f}".rstrip('0').rstrip('.')
                  if isinstance(val, float) else str(val))
            lines.append(f"{name} = {vs}")
        QMessageBox.information(self, "Variable Inspector",
                                "Current Variables:\n" + "-" * 20 + "\n" + "\n".join(lines))

    def _clear_variables(self):
        td = self._get_current_tab()
        if td:
            td.evaluator.clear_variables()
            QMessageBox.information(self, "Clear Variables",
                                    "All formula variables have been cleared.")

    def _toggle_auto_eval(self):
        self.preferences.auto_eval_enabled = self.auto_eval_action.isChecked()
        self._save_preferences()

    # =========================================================================
    # VIEW OPERATIONS
    # =========================================================================

    def _toggle_word_wrap(self):
        mode = (QPlainTextEdit.LineWrapMode.WidgetWidth
                if self.word_wrap_action.isChecked()
                else QPlainTextEdit.LineWrapMode.NoWrap)
        for td in self.tabs.values():
            td.text_widget.setLineWrapMode(mode)
        self._save_preferences()

    def _font_dialog(self):
        dlg = FontDialog(self, self.active_font_family,
                         self.current_font_size, self.preferences.theme)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            family, size = dlg.get_result()
            self.active_font_family = family
            self.preferences.font_family = family
            self.current_font_size = size
            font = make_font(family, size)
            for td in self.tabs.values():
                td.text_widget.setFont(font)
            self._save_preferences()

    def _toggle_status_bar(self):
        if self.status_bar_action.isChecked():
            if not self._is_fullscreen:
                self.status_bar.show()
            self._update_status_bar()
        else:
            self.status_bar.hide()
        self._save_preferences()

    def _toggle_line_numbers(self):
        visible = self.line_numbers_action.isChecked()
        for td in self.tabs.values():
            td.text_widget.set_line_numbers_visible(visible)
        self._save_preferences()

    def _toggle_highlight_syntax(self, mode):
        self.highlight_syntax = mode
        self.preferences.highlight_syntax = mode
        for td in self.tabs.values():
            td.text_widget.set_syntax_highlighting(
                mode, self.preferences.theme,
                self.spell_checker, self.preferences.spellcheck_enabled)
        self._save_preferences()

    def _update_status_bar(self):
        if not self.status_bar_action.isChecked():
            return
        td = self._get_current_tab()
        if not td:
            return
        tw = td.text_widget
        cursor = tw.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        text = tw.toPlainText()
        # Word and char count
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        sel = cursor.selectedText()
        if sel:
            sel_words = len(sel.split()) if sel.strip() else 0
            sel_chars = len(sel)
            self.status_bar.showMessage(
                f"Ln {line}, Col {col}  │  "
                f"Sel: {sel_chars} chars, {sel_words} words  │  "
                f"Total: {chars} chars, {words} words")
        else:
            self.status_bar.showMessage(
                f"Ln {line}, Col {col}  │  {chars} chars, {words} words"
                + ("  │  Spell check ON" if self.preferences.spellcheck_enabled else ""))

    def _zoom_in(self):
        if self.current_font_size < 72:
            self.current_font_size += 1
            font = make_font(self.active_font_family, self.current_font_size)
            for td in self.tabs.values():
                td.text_widget.setFont(font)
            self._save_preferences()

    def _zoom_out(self):
        if self.current_font_size > 6:
            self.current_font_size -= 1
            font = make_font(self.active_font_family, self.current_font_size)
            for td in self.tabs.values():
                td.text_widget.setFont(font)
            self._save_preferences()

    def _zoom_reset(self):
        self.current_font_size = 11
        font = make_font(self.active_font_family, self.current_font_size)
        for td in self.tabs.values():
            td.text_widget.setFont(font)
        self._save_preferences()

    def _change_theme(self, theme: str):
        self.preferences.theme = theme
        self._apply_theme(theme)
        self._save_preferences()

    # =========================================================================
    # HELP / ABOUT
    # =========================================================================

    def _show_formula_help(self):
        QMessageBox.information(self, "Formula Help", """Formula Evaluation Help

Type any expression ending with '=' — it evaluates instantly.
Ctrl+E evaluates all formulas in the document (or selection).

Operators:  + - * / // % ** ^
Functions:  sqrt, sin, cos, tan, log, log10, exp, abs, round, min, max, sum, pow
Constants:  pi, e

Variables:
  x = 5+3=        → stores x=8
  area: w*h=       → colon syntax

Zoom:
  RMB + scroll wheel, or Ctrl+=/−, or Ctrl+0 to reset""")

    def _show_about(self):
        QMessageBox.about(self, "About Enhanced Notepad", """Enhanced Notepad  —  Version 6.0 (PySide6)

EDITING
  • Unlimited tabbed documents
  • Full undo / redo history per tab
  • Find, Find Next/Prev (F3 / Shift+F3)
  • Find & Replace with Replace All
  • Go To Line (Ctrl+G)
  • Select All, Cut, Copy, Paste, Delete
  • Insert Time/Date (F5)
  • Word wrap toggle

SPELL CHECK
  • Red underline on misspelled words
  • Right-click for suggestions
  • Add words to personal dictionary
  • Toggle via View > Spell Check
    (requires: pip install pyspellchecker)

FORMULA CALCULATOR
  • Auto-evaluate on '=' keypress (toggle: Edit > Auto-Evaluate)
  • Ctrl+E → evaluate all / selection
  • Named variables  (x = 5+3)
  • Colon syntax  (area: w * h)
  • sqrt, sin, cos, tan, log, exp, abs…
  • Constants: pi, e

FILES & SESSION
  • Open / Save / Save As / Save All
  • Export to PDF — preserves font & theme colors
  • Autosave (configurable interval)
  • Session restore — reopens all tabs on next launch
  • Recent files list (up to 20)
  • Reopen closed tabs — Ctrl+Shift+T
  • New Window (Ctrl+Shift+N)
  • Command-line / double-click file opening

APPEARANCE
  • Light and Dark themes
  • Any font installed on your system (Format > Font)
  • Drop .ttf/.otf into %APPDATA%\\EnhancedNotepad\\fonts to bundle fonts
  • Searchable font picker with live preview
  • Font size 6–96 pt
  • Zoom In/Out (Ctrl+=/−, or RMB + scroll wheel)
  • Restore Default Zoom (Ctrl+0)
  • Line numbers toggle
  • Syntax highlighting — Off / Code / Text
  • Status bar: line, column, word count, char count
  • Fullscreen — F11 (hides menu & tab bar)
    Esc or F11 to exit

SPLIT VIEW
  • View > Split View (Ctrl+Shift+2)
  • Halves the window; pick any other tab to mirror
  • Draggable divider, read-only mirror pane

NAVIGATION
  • Tab switching — Ctrl+Tab / Ctrl+Shift+Tab
  • Middle-click tab to close
  • Up/Down boundary teleport (first/last line)

Built with Python 3 and PySide6""")

    # =========================================================================
    # MODIFICATION TRACKING
    # =========================================================================

    def _on_text_modified(self, tab_id):
        if tab_id in self.tabs and not self.tabs[tab_id].modified:
            self._update_tab_title(tab_id, modified=True)

    # =========================================================================
    # CLOSE EVENT
    # =========================================================================

    def closeEvent(self, event):
        self._save_session()
        for tab_id in list(self.tabs.keys()):
            td = self.tabs.get(tab_id)
            if td and td.modified:
                fname = (os.path.basename(td.current_file)
                         if td.current_file else "Untitled")
                reply = QMessageBox.question(
                    self, "Save Changes",
                    f"Do you want to save changes to '{fname}'?",
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No |
                    QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.Yes:
                    self._save_file(tab_id)
                elif reply == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
        self._save_preferences()
        event.accept()


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Enhanced Notepad v6.0 — tabbed text editor.",
        epilog="Associate with file types for double-click opening.")
    parser.add_argument("files", nargs="*", metavar="FILE",
                        help="Files to open on startup.")
    args, qt_args = parser.parse_known_args()
    qt_argv = [sys.argv[0]] + qt_args

    app = QApplication(qt_argv)
    files = [f for f in args.files if f]
    window = NotepadApp(files_to_open=files or None)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
