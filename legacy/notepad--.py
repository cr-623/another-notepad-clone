import tkinter as tk
from tkinter import filedialog, messagebox, font, simpledialog
import datetime
import os
import ast
import operator
import math
import json
import re
from typing import Tuple, Optional
from dataclasses import dataclass, asdict

# Define the icon file path relative to the script
ICON_PATH = "notepad.ico"
PREFS_FILE = "notepad_prefs.json"

def set_window_icon(window):
    """Sets the application icon for a given Tk/Toplevel window."""
    if os.path.exists(ICON_PATH):
        try:
            window.iconbitmap(ICON_PATH)
        except tk.TclError:
            pass

@dataclass
class Preferences:
    """User preferences for the application."""
    font_size: int = 11
    word_wrap: bool = True
    status_bar: bool = False
    recent_files: list = None
    theme: str = "light"
    font_family: str = "Consolas"
    line_numbers: bool = False
    
    def __post_init__(self):
        if self.recent_files is None:
            self.recent_files = []

class SafeExpressionEvaluator:
    """Safely evaluates mathematical expressions without arbitrary code execution."""
    SAFE_OPERATORS = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos,
    }
    
    SAFE_FUNCTIONS = {
        'abs': abs, 'round': round, 'min': min, 'max': max, 'sum': sum,
        'pow': pow, 'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos,
        'tan': math.tan, 'log': math.log, 'log10': math.log10,
        'exp': math.exp, 'pi': math.pi, 'e': math.e,
    }
    
    def __init__(self):
        self.variables = {}
    
    def clear_variables(self):
        self.variables = {}
    
    def _eval_node(self, node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in self.variables:
                return self.variables[node.id]
            elif node.id in self.SAFE_FUNCTIONS:
                return self.SAFE_FUNCTIONS[node.id]
            raise NameError(f"Variable '{node.id}' not defined")
        elif isinstance(node, ast.BinOp):
            return self.SAFE_OPERATORS[type(node.op)](self._eval_node(node.left), self._eval_node(node.right))
        elif isinstance(node, ast.UnaryOp):
            return self.SAFE_OPERATORS[type(node.op)](self._eval_node(node.operand))
        elif isinstance(node, ast.Call):
            func = self._eval_node(node.func)
            return func(*[self._eval_node(arg) for arg in node.args])
        raise ValueError(f"Unsupported operation: {type(node).__name__}")

    def evaluate(self, expression: str) -> Tuple[bool, Optional[float], Optional[str]]:
        try:
            tree = ast.parse(expression, mode='eval')
            return True, self._eval_node(tree.body), None
        except Exception as e:
            return False, None, str(e)

class LineNumbers(tk.Canvas):
    """Canvas widget that displays line numbers for a Text widget."""
    def __init__(self, parent, text_widget, **kwargs):
        super().__init__(parent, width=50, bg='#f0f0f0', highlightthickness=0, **kwargs)
        self.text_widget = text_widget
        
    def redraw(self, event=None):
        self.delete('all')
        i = self.text_widget.index('@0,0')
        while True:
            dline = self.text_widget.dlineinfo(i)
            if dline is None: break
            y = dline[1]
            linenum = str(i).split('.')[0]
            self.create_text(2, y, anchor='nw', text=linenum, font=('Consolas', 10), fill='#666666')
            i = self.text_widget.index(f'{i}+1line')

class FindDialog:
    def __init__(self, parent, text_widget, app):
        self.parent = parent
        self.text_widget = text_widget
        self.app = app
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Find")
        self.dialog.geometry("400x120")
        tk.Label(self.dialog, text="Find what:").grid(row=0, column=0, padx=5, pady=5)
        self.search_entry = tk.Entry(self.dialog, width=30)
        self.search_entry.grid(row=0, column=1, padx=5, pady=5)
        self.search_entry.insert(0, self.app.last_find_term)
        self.match_case_var = tk.BooleanVar(value=self.app.last_find_case_sensitive)
        tk.Checkbutton(self.dialog, text="Match case", variable=self.match_case_var).grid(row=1, column=1)
        tk.Button(self.dialog, text="Find Next", command=self.find_next).grid(row=0, column=2, padx=5)

    def find_next(self):
        term = self.search_entry.get()
        if not term: return
        self.app.last_find_term = term
        self.app.last_find_case_sensitive = self.match_case_var.get()
        pos = self.text_widget.search(term, tk.INSERT, tk.END, nocase=not self.match_case_var.get())
        if pos:
            self.text_widget.tag_remove(tk.SEL, "1.0", tk.END)
            end_pos = f"{pos}+{len(term)}c"
            self.text_widget.tag_add(tk.SEL, pos, end_pos)
            self.text_widget.mark_set(tk.INSERT, end_pos)
            self.text_widget.see(pos)

class NotepadApp:
    def __init__(self, master):
        self.master = master
        set_window_icon(master)
        master.title("Untitled - Notepad")
        
        self.current_file = None
        self.modified = False
        self.preferences = self._load_preferences()
        self.current_font_size = self.preferences.font_size
        self.evaluator = SafeExpressionEvaluator()
        self.last_find_term = ""
        self.last_find_case_sensitive = False

        # UI Layout
        main_frame = tk.Frame(master)
        main_frame.pack(fill=tk.BOTH, expand=1)
        
        self.line_numbers_frame = tk.Frame(main_frame)
        text_frame = tk.Frame(main_frame)
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
        
        self.text_area = tk.Text(text_frame, wrap='word', undo=True, font=('Consolas', self.current_font_size))
        self.scrollbar = tk.Scrollbar(text_frame, command=self.text_area.yview)
        self.text_area.config(yscrollcommand=self.scrollbar.set)
        self.line_numbers = LineNumbers(self.line_numbers_frame, self.text_area)
        
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_area.pack(fill=tk.BOTH, expand=1)
        self.status_bar = tk.Label(master, text="Ln 1, Col 1", bd=1, relief=tk.SUNKEN, anchor=tk.W)

        # Menus
        self.menu_bar = tk.Menu(master)
        master.config(menu=self.menu_bar)
        self._create_menus()
        self._setup_key_bindings()
        self._apply_preferences()
        
        self.text_area.bind('<<Modified>>', self._on_text_modified)
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _create_menus(self):
        # File Menu
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Files", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing)

        # Edit Menu
        edit_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Find", command=lambda: FindDialog(self.master, self.text_area, self), accelerator="Ctrl+F")
        edit_menu.add_command(label="Evaluate Formula", command=self._evaluate_formula, accelerator="Ctrl+E")
        
        # View Menu
        view_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="View", menu=view_menu)
        self.status_bar_var = tk.BooleanVar()
        view_menu.add_checkbutton(label="Status Bar", variable=self.status_bar_var, command=self._toggle_status_bar)
        self.line_numbers_var = tk.BooleanVar()
        view_menu.add_checkbutton(label="Line Numbers", variable=self.line_numbers_var, command=self._toggle_line_numbers)

    def _setup_key_bindings(self):
        self.master.bind('<Control-n>', lambda e: self.new_file())
        self.master.bind('<Control-o>', lambda e: self.open_file())
        self.master.bind('<Control-s>', lambda e: self.save_file())
        self.master.bind('<Control-e>', lambda e: self._evaluate_formula())
        self.text_area.bind('<KeyRelease>', self._on_key_release)
        self.text_area.bind('<ButtonRelease-1>', self._update_status_bar)

    def _on_key_release(self, event=None):
        """Triggers live UI updates on every key press."""
        self._update_status_bar()
        self._apply_live_features()
        if self.line_numbers_var.get():
            self.line_numbers.redraw()

    def _add_regex_tags(self, pattern, tag_name):
        """Internal helper to find and tag all regex matches using accurate counts."""
        start = "1.0"
        while True:
            count = tk.IntVar()
            pos = self.text_area.search(pattern, start, stopindex=tk.END, regexp=True, count=count)
            if not pos or count.get() == 0: 
                break
            end_pos = f"{pos} + {count.get()} chars"
            self.text_area.tag_add(tag_name, pos, end_pos)
            start = end_pos

    def _apply_live_features(self, event=None):
        """Handles syntax coloring and bracket matching."""
        # Configure Colors
        self.text_area.tag_configure("math_num", foreground="#d19a66")  # Orange
        self.text_area.tag_configure("math_var", foreground="#e06c75")  # Red-ish
        self.text_area.tag_configure("bracket_match", foreground="#3b82f6", font=('Consolas', self.current_font_size, 'bold'))
        self.text_area.tag_configure("bracket_err", background="#ef4444", foreground="white")
        
        # Clear Tags
        for tag in ["math_num", "math_var", "bracket_match", "bracket_err"]:
            self.text_area.tag_remove(tag, "1.0", tk.END)

        # 1. Syntax Highlighting
        self._add_regex_tags(r'\b\d+(\.\d+)?\b', "math_num")
        self._add_regex_tags(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', "math_var")

        # 2. Bracket Matching
        content = self.text_area.get("1.0", tk.END)
        stack = []
        pairs = {')': '(', ']': '[', '}': '{'}
        for i, char in enumerate(content):
            idx = f"1.0 + {i} chars"
            if char in "([{":
                stack.append((char, idx))
            elif char in ")]}":
                if stack and stack[-1][0] == pairs[char]:
                    _, open_idx = stack.pop()
                    self.text_area.tag_add("bracket_match", open_idx, f"{open_idx} + 1 chars")
                    self.text_area.tag_add("bracket_match", idx, f"{idx} + 1 chars")
                else:
                    self.text_area.tag_add("bracket_err", idx, f"{idx} + 1 chars")

    def _evaluate_formula(self):
        """Processes lines ending with '=' and calculates results."""
        content = self.text_area.get("1.0", tk.END).splitlines()
        new_content = []
        for line in content:
            if line.rstrip().endswith('='):
                expr = line.rstrip()[:-1].replace('^', '**')
                success, result, err = self.evaluator.evaluate(expr)
                if success:
                    line = f"{line.rstrip()} {result}"
            new_content.append(line)
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", "\n".join(new_content))

    def _load_preferences(self):
        if os.path.exists(PREFS_FILE):
            with open(PREFS_FILE, 'r') as f:
                return Preferences(**json.load(f))
        return Preferences()

    def _save_preferences(self):
        with open(PREFS_FILE, 'w') as f:
            json.dump(asdict(self.preferences), f)

    def _apply_preferences(self):
        self.status_bar_var.set(self.preferences.status_bar)
        self._toggle_status_bar()
        self.line_numbers_var.set(self.preferences.line_numbers)
        self._toggle_line_numbers()

    def _toggle_status_bar(self):
        if self.status_bar_var.get(): self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        else: self.status_bar.pack_forget()

    def _toggle_line_numbers(self):
        if self.line_numbers_var.get():
            self.line_numbers_frame.pack(side=tk.LEFT, fill=tk.Y)
            self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
            self.line_numbers.redraw()
        else:
            self.line_numbers_frame.pack_forget()

    def _update_status_bar(self):
        line, col = self.text_area.index(tk.INSERT).split('.')
        self.status_bar.config(text=f"Ln {line}, Col {int(col) + 1}")

    def _on_text_modified(self, event=None):
        if self.text_area.edit_modified():
            self.modified = True
            self.text_area.edit_modified(False)

    def new_file(self):
        self.text_area.delete("1.0", tk.END)
        self.current_file = None
        self.modified = False

    def open_file(self):
        path = filedialog.askopenfilename()
        if path:
            with open(path, 'r') as f:
                self.text_area.delete("1.0", tk.END)
                self.text_area.insert("1.0", f.read())
            self.current_file = path
            self.modified = False

    def save_file(self):
        path = self.current_file or filedialog.asksaveasfilename()
        if path:
            with open(path, 'w') as f:
                f.write(self.text_area.get("1.0", tk.END))
            self.current_file = path
            self.modified = False

    def _on_closing(self):
        self._save_preferences()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x600")
    app = NotepadApp(root)
    root.mainloop()
