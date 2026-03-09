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
from pathlib import Path
from dataclasses import dataclass, asdict

# Define the icon file path relative to the script
ICON_PATH = "notepad.ico"
PREFS_FILE = "notepad_prefs.json"

# Helper function to set the icon, handling potential errors
def set_window_icon(window):
    """Sets the application icon for a given Tk/Toplevel window."""
    if os.path.exists(ICON_PATH):
        try:
            window.iconbitmap(ICON_PATH)
        except tk.TclError:
            print(f"Warning: Could not set icon using iconbitmap('{ICON_PATH}').")
            pass
    else:
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
    highlight_syntax: str = "off" # "code", "text"
    
    def __post_init__(self):
        if self.recent_files is None:
            self.recent_files = []


class SafeExpressionEvaluator:
    """Safely evaluates mathematical expressions without arbitrary code execution."""
    
    # Allowed operations for safe evaluation
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
    
    # Allowed functions from math module
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
        elif isinstance(node, ast.Num):  # For Python < 3.8 compatibility
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
        """
        Safely evaluate a mathematical expression.
        
        Returns:
            Tuple of (success, result, error_message)
        """
        try:
            tree = ast.parse(expression, mode='eval')
            result = self._eval_node(tree.body)
            return True, result, None
        except (SyntaxError, ValueError, NameError, TypeError, ZeroDivisionError) as e:
            return False, None, str(e)


class LineNumbers(tk.Canvas):
    """Canvas widget that displays line numbers for a Text widget."""
    
    def __init__(self, parent, text_widget, **kwargs):
        super().__init__(parent, width=50, bg='#f0f0f0', highlightthickness=0, **kwargs)
        self.text_widget = text_widget
        self.text_widget.bind('<KeyRelease>', self.redraw)
        self.text_widget.bind('<ButtonRelease-1>', self.redraw)
        self.text_widget.bind('<MouseWheel>', self.redraw)
        self.text_widget.bind('<<Change>>', self.redraw)
        self.text_widget.bind('<<Modified>>', self.redraw)
        
    def redraw(self, event=None):
        """Redraw line numbers."""
        self.delete('all')
        
        i = self.text_widget.index('@0,0')
        while True:
            dline = self.text_widget.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            linenum = str(i).split('.')[0]
            self.create_text(2, y, anchor='nw', text=linenum, font=('Consolas', 10), fill='#666666')
            i = self.text_widget.index(f'{i}+1line')


class FindDialog:
    """Simple Find dialog window with improved search functionality."""
    def __init__(self, parent, text_widget, app):
        self.parent = parent
        self.text_widget = text_widget
        self.app = app
        self.last_pos = "1.0"
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Find")
        set_window_icon(self.dialog) 
        self.dialog.geometry("400x120")
        self.dialog.transient(parent)
        
        tk.Label(self.dialog, text="Find what:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.search_entry = tk.Entry(self.dialog, width=30)
        self.search_entry.grid(row=0, column=1, padx=5, pady=5)
        self.search_entry.insert(0, self.app.last_find_term)
        self.search_entry.focus()
        self.search_entry.select_range(0, tk.END)
        
        self.match_case_var = tk.BooleanVar(value=self.app.last_find_case_sensitive)
        tk.Checkbutton(self.dialog, text="Match case", variable=self.match_case_var).grid(row=1, column=1, sticky=tk.W)
        
        tk.Button(self.dialog, text="Find Next", command=self.find_next, width=12).grid(row=0, column=2, padx=5, pady=5)
        tk.Button(self.dialog, text="Cancel", command=self.dialog.destroy, width=12).grid(row=1, column=2, padx=5, pady=5)
        
        self.search_entry.bind('<Return>', lambda e: self.find_next())
        
    def find_next(self):
        search_term = self.search_entry.get()
        if not search_term:
            return
        
        # Update app's last search
        self.app.last_find_term = search_term
        self.app.last_find_case_sensitive = self.match_case_var.get()
        
        start_pos = self.text_widget.index(tk.INSERT)
        if self.last_pos and self.text_widget.compare(self.last_pos, ">", start_pos):
            start_pos = self.last_pos
            
        pos = self.text_widget.search(search_term, start_pos, tk.END, nocase=not self.match_case_var.get())
        
        if pos:
            self.text_widget.tag_remove(tk.SEL, "1.0", tk.END)
            end_pos = f"{pos}+{len(search_term)}c"
            self.text_widget.tag_add(tk.SEL, pos, end_pos)
            self.text_widget.mark_set(tk.INSERT, end_pos)
            self.text_widget.see(pos)
            self.last_pos = end_pos
        else:
            pos = self.text_widget.search(search_term, "1.0", start_pos, nocase=not self.match_case_var.get())
            if pos:
                self.text_widget.tag_remove(tk.SEL, "1.0", tk.END)
                end_pos = f"{pos}+{len(search_term)}c"
                self.text_widget.tag_add(tk.SEL, pos, end_pos)
                self.text_widget.mark_set(tk.INSERT, end_pos)
                self.text_widget.see(pos)
                self.last_pos = end_pos
            else:
                messagebox.showinfo("Find", f"Cannot find \"{search_term}\"", parent=self.dialog)
                self.last_pos = "1.0"


class ReplaceDialog:
    """Simple Replace dialog window."""
    def __init__(self, parent, text_widget):
        self.parent = parent
        self.text_widget = text_widget
        self.last_pos = "1.0"
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Replace")
        set_window_icon(self.dialog) 
        self.dialog.geometry("400x150")
        self.dialog.transient(parent)
        
        tk.Label(self.dialog, text="Find what:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.find_entry = tk.Entry(self.dialog, width=30)
        self.find_entry.grid(row=0, column=1, padx=5, pady=5)
        self.find_entry.focus()
        
        tk.Label(self.dialog, text="Replace with:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.replace_entry = tk.Entry(self.dialog, width=30)
        self.replace_entry.grid(row=1, column=1, padx=5, pady=5)
        
        self.match_case_var = tk.BooleanVar()
        tk.Checkbutton(self.dialog, text="Match case", variable=self.match_case_var).grid(row=2, column=1, sticky=tk.W)
        
        tk.Button(self.dialog, text="Find Next", command=self.find_next, width=12).grid(row=0, column=2, padx=5, pady=5)
        tk.Button(self.dialog, text="Replace", command=self.replace, width=12).grid(row=1, column=2, padx=5, pady=5)
        tk.Button(self.dialog, text="Replace All", command=self.replace_all, width=12).grid(row=2, column=2, padx=5, pady=5)
        
        self.find_entry.bind('<Return>', lambda e: self.find_next())
        
    def find_next(self):
        search_term = self.find_entry.get()
        if not search_term:
            return
            
        start_pos = self.last_pos if self.last_pos != "1.0" else self.text_widget.index(tk.INSERT)
        pos = self.text_widget.search(search_term, start_pos, tk.END, nocase=not self.match_case_var.get())
        
        if pos:
            self.text_widget.tag_remove(tk.SEL, "1.0", tk.END)
            end_pos = f"{pos}+{len(search_term)}c"
            self.text_widget.tag_add(tk.SEL, pos, end_pos)
            self.text_widget.mark_set(tk.INSERT, end_pos)
            self.text_widget.see(pos)
            self.last_pos = end_pos
        else:
            messagebox.showinfo("Replace", f"Cannot find \"{search_term}\"", parent=self.dialog)
            self.last_pos = "1.0"
    
    def replace(self):
        if tk.SEL in self.text_widget.tag_names():
            try:
                self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self.text_widget.insert(tk.INSERT, self.replace_entry.get())
                self.last_pos = self.text_widget.index(tk.INSERT)
                self.find_next()
            except tk.TclError:
                pass
    
    def replace_all(self):
        search_term = self.find_entry.get()
        replace_term = self.replace_entry.get()
        if not search_term:
            return
            
        count = 0
        pos = "1.0"
        while True:
            pos = self.text_widget.search(search_term, pos, tk.END, nocase=not self.match_case_var.get())
            if not pos:
                break
            end_pos = f"{pos}+{len(search_term)}c"
            self.text_widget.delete(pos, end_pos)
            self.text_widget.insert(pos, replace_term)
            count += 1
            pos = f"{pos}+{len(replace_term)}c"
        
        messagebox.showinfo("Replace All", f"Replaced {count} occurrence(s)", parent=self.dialog)


class NotepadApp:
    def __init__(self, master):
        self.master = master
        set_window_icon(master)
        
        master.title("Untitled - Notepad")
        self.current_file = None
        self.modified = False
        
        # Load preferences
        self.preferences = self._load_preferences()
        self.current_font_size = self.preferences.font_size
        self.highlight_syntax_var = tk.StringVar(value=self.preferences.highlight_syntax)

        # Initialize formula evaluator
        self.evaluator = SafeExpressionEvaluator()
        
        # Find/Replace state
        self.last_find_term = ""
        self.last_find_case_sensitive = False
        
        # Create main frame
        main_frame = tk.Frame(master)
        main_frame.pack(fill=tk.BOTH, expand=1)
        
        # Line numbers frame
        self.line_numbers_frame = tk.Frame(main_frame)
        
        # Text Area and Scrollbar Setup
        text_frame = tk.Frame(main_frame)
        text_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=1)
        
        self.text_area = tk.Text(text_frame, wrap='word', undo=True, font=('Consolas', self.current_font_size))
        self.scrollbar = tk.Scrollbar(text_frame, command=self.text_area.yview)
        self.text_area.config(yscrollcommand=self.scrollbar.set)
        
        # Line numbers
        self.line_numbers = LineNumbers(self.line_numbers_frame, self.text_area)
        
        # Track modifications
        self.text_area.bind('<<Modified>>', self._on_text_modified)
        
        # Status bar
        self.status_bar = tk.Label(master, text="Ln 1, Col 1", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_area.pack(fill=tk.BOTH, expand=1)
        
        # Menu Bar Creation
        self.menu_bar = tk.Menu(master)
        master.config(menu=self.menu_bar)
        
        self._create_file_menu()
        self._create_edit_menu()
        self._create_format_menu()
        self._create_view_menu()
        self._create_help_menu()

        # Keyboard Bindings
        self._setup_key_bindings()
        
        # Apply saved preferences
        self._apply_preferences()
        
        # Handle window close
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

    # =========================================================================
    # PREFERENCES MANAGEMENT
    # =========================================================================
    
    def _load_preferences(self) -> Preferences:
        """Load user preferences from file."""
        try:
            if os.path.exists(PREFS_FILE):
                with open(PREFS_FILE, 'r') as f:
                    data = json.load(f)
                    return Preferences(**data)
        except Exception as e:
            print(f"Could not load preferences: {e}")
        return Preferences()
    
    def _save_preferences(self):
        """Save user preferences to file."""
        try:
            self.preferences.font_size = self.current_font_size
            self.preferences.word_wrap = self.word_wrap_var.get()
            self.preferences.status_bar = self.status_bar_var.get()
            self.preferences.line_numbers = self.line_numbers_var.get()
            self.preferences.highlight_syntax = self.highlight_syntax_var.get()            
            with open(PREFS_FILE, 'w') as f:
                json.dump(asdict(self.preferences), f, indent=2)
        except Exception as e:
            print(f"Could not save preferences: {e}")
    
    def _apply_preferences(self):
        """Apply loaded preferences to the UI."""
        self.word_wrap_var.set(self.preferences.word_wrap)
        self._toggle_word_wrap()
        
        self.status_bar_var.set(self.preferences.status_bar)
        self._toggle_status_bar()
        
        self.line_numbers_var.set(self.preferences.line_numbers)
        self._toggle_line_numbers()
        
        self.highlight_syntax_var.set(self.preferences.highlight_syntax)
        if self.preferences.highlight_syntax != "off":
            self._apply_live_features()
        
        self._apply_theme(self.preferences.theme)
    
    def _apply_theme(self, theme: str):
        """Apply color theme to the editor."""
        if theme == "dark":
            bg_color = '#1e1e1e'
            fg_color = '#d4d4d4'
            insert_color = '#ffffff'
            select_bg = '#264f78'
            select_fg = '#ffffff'
            line_num_bg = '#252526'
            line_num_fg = '#858585'
        else:  # light theme
            bg_color = '#ffffff'
            fg_color = '#484848'
            insert_color = '#000000'
            select_bg = '#0078d7'
            select_fg = '#ffffff'
            line_num_bg = '#f0f0f0'
            line_num_fg = '#666666'
        
        self.text_area.config(
            bg=bg_color,
            fg=fg_color,
            insertbackground=insert_color,
            selectbackground=select_bg,
            selectforeground=select_fg
        )
        self.line_numbers.config(bg=line_num_bg)
        # Store colors for line number redraw
        self.line_numbers.text_color = line_num_fg

    # =========================================================================
    # RECENT FILES MANAGEMENT
    # =========================================================================
    
    def _update_recent_files(self, filepath: str):
        """Update the recent files list."""
        if filepath in self.preferences.recent_files:
            self.preferences.recent_files.remove(filepath)
        self.preferences.recent_files.insert(0, filepath)
        self.preferences.recent_files = self.preferences.recent_files[:10]  # Keep max 10
        self._save_preferences()
        self._update_recent_files_menu()
    
    def _update_recent_files_menu(self):
        """Update the recent files submenu."""
        # Clear existing items
        self.recent_menu.delete(0, tk.END)
        
        if not self.preferences.recent_files:
            self.recent_menu.add_command(label="(No recent files)", state=tk.DISABLED)
        else:
            for i, filepath in enumerate(self.preferences.recent_files):
                if os.path.exists(filepath):
                    display_name = os.path.basename(filepath)
                    self.recent_menu.add_command(
                        label=f"{i+1}. {display_name}",
                        command=lambda f=filepath: self._open_recent_file(f),
                        underline=0
                    )
            self.recent_menu.add_separator()
            self.recent_menu.add_command(label="Clear Recent Files", command=self._clear_recent_files)
    
    def _open_recent_file(self, filepath: str):
        """Open a file from recent files list."""
        if not self._check_save():
            return
        
        if not os.path.exists(filepath):
            messagebox.showerror("File Not Found", f"The file '{filepath}' no longer exists.")
            self.preferences.recent_files.remove(filepath)
            self._save_preferences()
            self._update_recent_files_menu()
            return
        
        self.text_area.delete(1.0, tk.END)
        try:
            with open(filepath, "r", encoding='utf-8') as input_file:
                self.text_area.insert(1.0, input_file.read())
            self.current_file = filepath
            self.modified = False
            self.set_title(filepath)
            self._update_recent_files(filepath)
        except Exception as e:
            messagebox.showerror("Open File Error", f"Could not read file: {e}")
    
    def _clear_recent_files(self):
        """Clear the recent files list."""
        self.preferences.recent_files = []
        self._save_preferences()
        self._update_recent_files_menu()

    # =========================================================================
    # MENU CREATION METHODS
    # =========================================================================

    def _create_file_menu(self):
        """Creates the File menu structure and commands."""
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=file_menu, underline=0)
        
        file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N", underline=0)
        file_menu.add_command(label="New Window", command=self.new_window, accelerator="Ctrl+Shift+N", underline=4)
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O", underline=0)
        
        # Recent files submenu
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Files", menu=self.recent_menu, underline=0)
        self._update_recent_files_menu()
        
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S", underline=0)
        file_menu.add_command(label="Save As...", command=self.save_file_as, accelerator="Ctrl+Shift+S", underline=5)
        file_menu.add_separator()
        file_menu.add_command(label="Close", command=self.close_file, accelerator="Ctrl+W", underline=0)
        file_menu.add_command(label="Exit", command=self._on_closing, accelerator="Ctrl+Q", underline=1)

    def _create_edit_menu(self):
        """Creates the Edit menu structure and commands."""
        edit_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Edit", menu=edit_menu, underline=0)
        
        edit_menu.add_command(label="Undo", command=self.text_area.edit_undo, accelerator="Ctrl+Z", underline=0)
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut", command=lambda: self.text_area.event_generate("<<Cut>>"), accelerator="Ctrl+X", underline=2)
        edit_menu.add_command(label="Copy", command=lambda: self.text_area.event_generate("<<Copy>>"), accelerator="Ctrl+C", underline=0)
        edit_menu.add_command(label="Paste", command=lambda: self.text_area.event_generate("<<Paste>>"), accelerator="Ctrl+V", underline=0)
        edit_menu.add_command(label="Delete", command=lambda: self.text_area.event_generate("<Delete>"), accelerator="Del", underline=0)
        edit_menu.add_separator()
        edit_menu.add_command(label="Find...", command=self._find_dialog, accelerator="Ctrl+F", underline=0)
        edit_menu.add_command(label="Find Next", command=self._find_next, accelerator="F3", underline=5)
        edit_menu.add_command(label="Find Previous", command=self._find_prev, accelerator="Shift+F3", underline=5)
        edit_menu.add_command(label="Replace...", command=self._replace_dialog, accelerator="Ctrl+H", underline=0)
        edit_menu.add_command(label="Go To...", command=self._goto_line, accelerator="Ctrl+G", underline=0)
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All", command=self._select_all, accelerator="Ctrl+A", underline=7)
        edit_menu.add_command(label="Time/Date", command=self._insert_time_date, accelerator="F5", underline=0)
        edit_menu.add_separator()
        edit_menu.add_command(label="Evaluate Formula", command=self._evaluate_formula, accelerator="Ctrl+E", underline=0)
        edit_menu.add_command(label="List Variables", command=self._list_variables)
        edit_menu.add_command(label="Clear Variables", command=self._clear_variables, underline=0)

    def _create_format_menu(self):
        """Creates the Format menu structure and commands."""
        format_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Format", menu=format_menu, underline=1)
        
        self.word_wrap_var = tk.BooleanVar(value=True)
        format_menu.add_checkbutton(label="Word wrap", onvalue=True, offvalue=False, variable=self.word_wrap_var, command=self._toggle_word_wrap, underline=0)
        
        format_menu.add_command(label="Font...", command=self._font_dialog, underline=0)

    def _create_view_menu(self):
        """Creates the View menu structure and commands."""
        view_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="View", menu=view_menu, underline=0)

        zoom_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Zoom", menu=zoom_menu, underline=0)
        zoom_menu.add_command(label="Zoom In", command=self._zoom_in, accelerator="Ctrl+Plus", underline=5)
        zoom_menu.add_command(label="Zoom Out", command=self._zoom_out, accelerator="Ctrl+Minus", underline=5)
        zoom_menu.add_command(label="Restore Default Zoom", command=self._zoom_reset, accelerator="Ctrl+0", underline=0)
        
        self.status_bar_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(label="Status bar", onvalue=True, offvalue=False, variable=self.status_bar_var, command=self._toggle_status_bar, underline=0)
        
        self.line_numbers_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(label="Line numbers", onvalue=True, offvalue=False, variable=self.line_numbers_var, command=self._toggle_line_numbers, underline=0)
        
        # Theme submenu
        theme_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Theme", menu=theme_menu, underline=0)
        theme_menu.add_command(label="Light", command=lambda: self._change_theme("light"))
        theme_menu.add_command(label="Dark", command=lambda: self._change_theme("dark"))
        view_menu.add_separator()
        
        # Syntax highlighting submenu with radio buttons
        highlight_syntax_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Highlight syntax", menu=highlight_syntax_menu, underline=0)
        highlight_syntax_menu.add_radiobutton(
            label="Off", 
            variable=self.highlight_syntax_var, 
            value="off",
            command=self._toggle_highlight_syntax,
            underline=0
        )
        highlight_syntax_menu.add_radiobutton(
            label="Code", 
            variable=self.highlight_syntax_var, 
            value="code",
            command=self._toggle_highlight_syntax,
            underline=0
        )
        highlight_syntax_menu.add_radiobutton(
            label="Text", 
            variable=self.highlight_syntax_var, 
            value="text",
            command=self._toggle_highlight_syntax,
            underline=0
        )        
    def _create_help_menu(self):
        """Creates the Help menu structure and commands."""
        help_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Help", menu=help_menu, underline=0)
        
        help_menu.add_command(label="Formula Help", command=self._show_formula_help, underline=0)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about, underline=0)

    # =========================================================================
    # KEY BINDINGS SETUP
    # =========================================================================
    
    def _setup_key_bindings(self):
        """Sets up all keyboard shortcuts."""
        # File shortcuts
        self.master.bind('<Control-n>', self.new_file)
        self.master.bind('<Control-Shift-N>', self.new_window)
        self.master.bind('<Control-o>', self.open_file)
        self.master.bind('<Control-s>', self.save_file)
        self.master.bind('<Control-Shift-S>', self.save_file_as)
        self.master.bind('<Control-w>', lambda e: self.close_file())
        self.master.bind('<Control-q>', lambda e: self._on_closing())
        
        # Edit shortcuts
        self.master.bind('<Control-f>', lambda e: self._find_dialog())
        self.master.bind('<F3>', lambda e: self._find_next())
        self.master.bind('<Shift-F3>', lambda e: self._find_prev())
        self.master.bind('<Control-h>', lambda e: self._replace_dialog())
        self.master.bind('<Control-g>', lambda e: self._goto_line())
        self.master.bind('<Control-a>', self._select_all)
        self.master.bind('<F5>', self._insert_time_date)
        self.master.bind('<=>', lambda e: self._evaluate_formula())
        self.master.bind('<Control-l>', lambda e: self._list_variables())

        # Semantic shortcuts
        self.text_area.bind('<Control-BackSpace>', self._delete_word_left)
        self.text_area.bind('<Control-Delete>', self._delete_word_right)
        
        # Zoom shortcuts
        self.master.bind('<Control-plus>', lambda e: self._zoom_in())
        self.master.bind('<Control-equal>', lambda e: self._zoom_in())
        self.master.bind('<Control-minus>', lambda e: self._zoom_out())
        self.master.bind('<Control-0>', lambda e: self._zoom_reset())
        
        # Cursor tracking for status bar
        self.text_area.bind('<KeyRelease>', lambda e: (self._update_status_bar(e), self._apply_live_features(e)))
        self.text_area.bind('<ButtonRelease-1>', self._update_status_bar)

    # =========================================================================
    # FORMULA EVALUATION
    # =========================================================================

    # Helper function to pre-evaluate expression
    def pre_process_expression(self, expr: str) -> str:
        # 1. Replace ^ with **
        expr = expr.replace('^', '**')
    
        # 2. Add * between numbers and variables (e.g., 2x -> 2*x)
        # This looks for a digit followed by a letter
        expr = re.sub(r'(\d)(?![eE][+-]?\d)([a-zA-Z\(])', r'\1*\2', expr)
        # 3. Add * between closing bracket and number/variable (e.g., (1+2)x -> (1+2)*x)
        expr = re.sub(r'(\))([0-9a-zA-Z])', r'\1*\2', expr)
    
        return expr

    def _evaluate_formula(self):
        """Evaluates formulas ending with '=' and handles chaining and prefix preservation."""
        try:
            selected_text = self.text_area.get(tk.SEL_FIRST, tk.SEL_LAST)
            has_selection = True
            start_idx = self.text_area.index(tk.SEL_FIRST)
            end_idx = self.text_area.index(tk.SEL_LAST)
        except tk.TclError:
            has_selection = False
            selected_text = self.text_area.get("1.0", tk.END)
            start_idx = "1.0"
            end_idx = tk.END
        
        lines = selected_text.split('\n')
        modified = False
        new_lines = []

        for line in lines:
            stripped = line.rstrip()
            
            # Only process lines ending with '='
            if stripped.endswith('='):
                # Remove the trailing '='
                content = stripped[:-1].strip()
                
                var_name = None
                var_separator = None  # Track whether it's ':' or '='
                formula_to_eval = None
                prefix = ''
                
                # Check for variable assignment patterns FIRST (before splitting by '=')
                # Pattern 1: "variable_name: formula" or "variable name: formula"
                if ':' in content:
                    parts = content.split(':', 1)
                    potential_var = parts[0].strip()
                    # Check if it's a valid identifier (allowing spaces that we'll convert to underscores)
                    if potential_var.replace(' ', '').replace('_', '').isalnum() and not potential_var[0].isdigit():
                        var_name = potential_var.replace(' ', '_')
                        var_separator = ':'
                        remainder = parts[1].strip()
                        
                        # The remainder might have chained formulas: "5 + 3 = 8 + 2"
                        if '=' in remainder:
                            chain_parts = remainder.split('=')
                            formula_to_eval = chain_parts[-1].strip()
                            if len(chain_parts) > 1:
                                prefix = '='.join(chain_parts[:-1]).strip() + ' = '
                        else:
                            formula_to_eval = remainder
                
                # Pattern 2: "variable_name = formula" (only if no ':' found or not a valid variable with ':')
                if var_name is None:
                    # Split by '=' to get all parts
                    parts = content.split('=')
                    
                    # Check if the first part is a variable name (simple identifier, no operators)
                    if len(parts) >= 1:
                        first_part = parts[0].strip()
                        # It's a variable if it's a simple identifier with no math operators
                        if (first_part.replace('_', '').replace(' ', '').isalnum() and 
                            not first_part[0].isdigit() and
                            not any(op in first_part for op in ['+', '-', '*', '/', '(', ')', '%'])):
                            
                            var_name = first_part.replace(' ', '_')
                            var_separator = '='
                            
                            # Everything after the first '=' is what we evaluate
                            if len(parts) > 1:
                                remainder = '='.join(parts[1:]).strip()
                                # Check for chained formulas
                                if '=' in remainder:
                                    chain_parts = remainder.split('=')
                                    formula_to_eval = chain_parts[-1].strip()
                                    if len(chain_parts) > 1:
                                        prefix = '='.join(chain_parts[:-1]).strip() + ' = '
                                else:
                                    formula_to_eval = remainder
                        else:
                            # Not a variable assignment, treat as chained formula
                            formula_to_eval = parts[-1].strip()
                            if len(parts) > 1:
                                prefix = '='.join(parts[:-1]).strip() + ' = '
                
                # If we still don't have a formula, use the content
                if formula_to_eval is None:
                    formula_to_eval = content
                
                # Now evaluate the formula
                if formula_to_eval:
                    success, result, error = self.evaluator.evaluate(self.pre_process_expression(formula_to_eval))
                    
                    if success:
                        # Clean up float formatting
                        if isinstance(result, (float, int)):
                            if abs(result) >= 1e10 or (abs(result) < 1e-4 and result != 0):
                                result_str = f"{result:.4e}" # 4 decimal places in scientific notation
                            else:
                                result_str = f"{result:.10f}".rstrip('0').rstrip('.')
                        else:
                            result_str = str(result)
                        # Store in memory if we have a variable name
                        if var_name:
                            self.evaluator.variables[var_name] = result
                            # For variable assignments, use the appropriate separator
                            if prefix:
                                new_lines.append(f"{var_name}{var_separator} {prefix}{result_str}")
                            else:
                                new_lines.append(f"{var_name} {var_separator} {result_str}")
                        else:
                            # Preserve prefix and append result
                            if prefix:
                                new_lines.append(f"{prefix}{result_str}")
                            else:
                                new_lines.append(f"{formula_to_eval} = {result_str}")
                        
                        modified = True
                    else:
                        # Keep original line if evaluation fails
                        new_lines.append(line)
                else:
                    # Empty formula
                    new_lines.append(line)
            else:
                # Line doesn't end with '=', keep as is
                new_lines.append(line)
        
        if modified:
            self.text_area.edit_separator()
            if has_selection:
                self.text_area.delete(start_idx, end_idx)
                self.text_area.insert(start_idx, ''.join(new_lines))
            else:
                self.text_area.delete("1.0", tk.END)
                self.text_area.insert("1.0", '\n'.join(new_lines))
            self.text_area.edit_separator()

    def _list_variables(self):
        """Shows a dialog with all currently defined variables and their values."""
        variables = self.evaluator.variables
        
        if not variables:
            messagebox.showinfo("Variables", "No variables currently defined.")
            return

        # Create a formatted string of variables
        var_list = []
        for name, value in sorted(variables.items()):
            if isinstance(value, float):
                val_str = f"{value:.10f}".rstrip('0').rstrip('.')
            else:
                val_str = str(value)
            var_list.append(f"{name} = {val_str}")
        
        help_text = "Current Variables:\n" + "-" * 20 + "\n" + "\n".join(var_list)

        # Create a simple dialog to show them
        dialog = tk.Toplevel(self.master)
        dialog.title("Variable Inspector")
        set_window_icon(dialog)
        dialog.geometry("300x400")
        dialog.transient(self.master)
        
        text = tk.Text(dialog, wrap='word', padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert('1.0', help_text)
        text.config(state=tk.DISABLED)
        
        tk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)
    
    def _clear_variables(self):
        """Clear all stored formula variables."""
        self.evaluator.clear_variables()
        messagebox.showinfo("Clear Variables", "All formula variables have been cleared.")

    # =========================================================================
    # SYNTAX HIGHLIGHTING
    # =========================================================================

    def _tag_pattern(self, pattern, tag_name):
        """Internal helper to find and tag all regex matches."""
        start = "1.0"
        while True:
            count = tk.IntVar()
            # Use the built-in Tkinter search with Regex enabled and count variable
            pos = self.text_area.search(pattern, start, stopindex=tk.END, regexp=True, count=count)
            if not pos or count.get() == 0: 
                break
            
            end_pos = f"{pos} + {count.get()} chars"
            self.text_area.tag_add(tag_name, pos, end_pos)
            start = end_pos # Move the cursor forward to find the next one

    def _add_regex_tags(self, pattern, tag_name):
        """Helper to apply a tag to all regex matches with accurate length tracking."""
        start = "1.0"
        while True:
            count = tk.IntVar()
            pos = self.text_area.search(pattern, start, stopindex=tk.END, regexp=True, count=count)
            if not pos or count.get() == 0: 
                break
            
            end_pos = f"{pos} + {count.get()} chars"
            self.text_area.tag_add(tag_name, pos, end_pos)
            start = end_pos

    def _highlight_text_in_brackets(self):
        """Highlight all text inside parentheses, brackets, and braces."""
        content = self.text_area.get("1.0", tk.END)
        
        for i, char in enumerate(content):
            if char in "([{":
                # Find matching closing bracket
                open_bracket = char
                close_bracket = {'(': ')', '[': ']', '{': '}'}[char]
                depth = 1
                j = i + 1
                
                while j < len(content) and depth > 0:
                    if content[j] == open_bracket:
                        depth += 1
                    elif content[j] == close_bracket:
                        depth -= 1
                    j += 1
                
                # If we found a match, highlight the text inside
                if depth == 0:
                    start_idx = f"1.0 + {i + 1} chars"
                    end_idx = f"1.0 + {j - 1} chars"
                    self.text_area.tag_add("bracket_text", start_idx, end_idx)

    def _apply_live_features(self, event=None):
        """Handles bracket matching, syntax coloring, and error sounds."""
        # Get the current syntax highlighting mode
        mode = self.highlight_syntax_var.get()
        
        # If highlighting is off, don't do anything
        if mode == "off":
            return
        
        # 1. Configure Tags (Ensuring all categories are defined)
        if mode == "code":
            self.text_area.tag_configure("bracket_text", foreground="#7da8ff") # Light blue
            self.text_area.tag_configure("math_num", foreground="#445ad4")  # Indigo
            self.text_area.tag_configure("math_var", foreground="#e06c75")  # Red-ish
            self.text_area.tag_configure("math_op", foreground="#44ccd4")   # Cyan
            self.text_area.tag_configure("string", foreground="#21ad4d")  # Green
            self.text_area.tag_configure("bracket_match", foreground="#1400eb")
            self.text_area.tag_configure("bracket_err", background="#ef4444", foreground="white")
            self.text_area.tag_configure("function", foreground="#ffeb3b")  # Yellow
            self.text_area.tag_configure("punct", foreground="#484848")
        elif mode == "text":
            self.text_area.tag_configure("bracket_text", foreground="#000000") # Dark grey
            self.text_area.tag_configure("math_num", foreground="#898989")  # Grey-ish
            self.text_area.tag_configure("math_var", foreground="#484848")  # Normal
            self.text_area.tag_configure("math_op", foreground="#898989")   # Grey-ish
            self.text_area.tag_configure("string", foreground="#b3b3b3")  # Light grey
            self.text_area.tag_configure("bracket_match", foreground="#000000") # Dark grey
            self.text_area.tag_configure("bracket_err", background="#000000") # Dark grey
            self.text_area.tag_configure("function", foreground="#484848")  # Normal
            self.text_area.tag_configure("punct", foreground="#000000")

        # Reset all tags to prevent "bleeding" from old text
        for tag in ["math_num", "math_var", "math_op", "bracket_match", "bracket_err", "string", "bracket_text", "function", "punct"]:
            self.text_area.tag_remove(tag, "1.0", tk.END)

        # 2. Syntax Coloring (Using the fixed Helper Function)
        # Highlight text in brackets (order depends on type)
        if mode == "code":
            self._highlight_text_in_brackets()

        # Highlight numbers (integers and decimals)
        self._add_regex_tags(r'\b\d+(\.\d+)?\b', "math_num")
        self._add_regex_tags(r'\d+\.?\d*([eE][+-]?\d+)?', "math_num")

        # Highlight punctuation
        self._add_regex_tags(r'[\,\!\:\;\&\.]', "punct")
        
        # Highlight variables (letters/underscores followed by alphanumeric)
        self._add_regex_tags(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', "math_var")

        # Highlight operators
        self._add_regex_tags(r'[\+\-\*\/\=\%\^]', "math_op")

        # Highlight strings
        self._add_regex_tags(r'"[^"]*"', "string")  # Double quotes
        self._add_regex_tags(r"'[^']*'", "string")  # Single quotes

        # Highlight text before brackets
        self._add_regex_tags(r'[a-zA-Z_][a-zA-Z0-9_]*(?=\()', "function")

        if mode == "text":
            self._highlight_text_in_brackets()

        # 3. Bracket Matching Logic
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
                    self.master.bell() 

        for _, idx in stack:
            self.text_area.tag_add("bracket_err", idx, f"{idx} + 1 chars")

    # =========================================================================
    # COMMAND IMPLEMENTATION METHODS
    # =========================================================================

    def _delete_word_left(self, event=None):
        """Deletes the word to the left of the cursor."""
        # If there is a selection, just delete the selection
        if self.text_area.tag_ranges(tk.SEL):
            self.text_area.delete(tk.SEL_FIRST, tk.SEL_LAST)
        else:
            # Define the start and end of the word to the left
            # "insert-1c wordstart" moves to the beginning of the previous word
            self.text_area.delete("insert-1c wordstart", "insert")
        
        self._on_text_modified()
        return "break" # Prevents the default backspace behavior

    def _delete_word_right(self, event=None):
        """Deletes the word to the right of the cursor."""
        if self.text_area.tag_ranges(tk.SEL):
            self.text_area.delete(tk.SEL_FIRST, tk.SEL_LAST)
        else:
            # "insert wordend" finds the end of the current word
            self.text_area.delete("insert", "insert wordend")
            
        self._on_text_modified()
        return "break" # Prevents the default delete behavior

    def set_title(self, filename=None):
        """Sets the window title."""
        base_title = " - Enhanced Notepad"
        modified_marker = "*" if self.modified else ""
        if filename:
            self.master.title(f"{modified_marker}{os.path.basename(filename)}{base_title}")
        else:
            self.master.title(f"{modified_marker}Untitled{base_title}")

    def _on_text_modified(self, event=None):
        """Called when text is modified."""
        if self.text_area.edit_modified():
            if not self.modified:
                self.modified = True
                self.set_title(self.current_file)
            self.text_area.edit_modified(False)

    def _check_save(self):
        """Check if file needs saving before closing/opening new file."""
        if self.modified:
            response = messagebox.askyesnocancel("Save Changes", 
                "Do you want to save changes to this document?")
            if response:
                self.save_file()
                return True
            elif response is None:
                return False
        return True

    def _on_closing(self):
        """Handle window close event."""
        if self._check_save():
            self._save_preferences()
            self.master.quit()

    def new_window(self, event=None):
        """Creates a new instance of the application."""
        new_root = tk.Toplevel(self.master)
        set_window_icon(new_root) 
        NotepadApp(new_root)

    def new_file(self, event=None):
        """Clears the text area."""
        if not self._check_save():
            return
        self.current_file = None
        self.text_area.delete(1.0, tk.END)
        self.modified = False
        self.set_title()
    
    def open_file(self, event=None):
        """Opens a file."""
        if not self._check_save():
            return
        filepath = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not filepath:  
            return
        self.text_area.delete(1.0, tk.END)
        try:
            with open(filepath, "r", encoding='utf-8') as input_file:
                self.text_area.insert(1.0, input_file.read())
            self.current_file = filepath
            self.modified = False
            self.set_title(filepath)
            self._update_recent_files(filepath)
        except Exception as e:
            messagebox.showerror("Open File Error", f"Could not read file: {e}")

    def save_file(self, event=None):
        """Saves the current file."""
        if self.current_file:
            self._write_file(self.current_file)
        else:
            self.save_file_as()

    def save_file_as(self, event=None):
        """Saves the file with a new name."""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not filepath:  
            return
        self._write_file(filepath)
        self.current_file = filepath
        self.set_title(filepath)
        self._update_recent_files(filepath)
        
    def _write_file(self, filepath):
        """Helper to write content to a given path."""
        try:
            with open(filepath, "w", encoding='utf-8') as output_file:
                text = self.text_area.get(1.0, tk.END)
                if text.endswith('\n'):
                    text = text[:-1]
                output_file.write(text)
            self.modified = False
            self.set_title(self.current_file)
        except Exception as e:
            messagebox.showerror("Save File Error", f"Could not save file: {e}")

    def close_file(self, event=None):
        """Closes current file and returns to untitled."""
        if not self._check_save():
            return
        self.current_file = None
        self.text_area.delete(1.0, tk.END)
        self.modified = False
        self.set_title()

    def _select_all(self, event=None):
        """Selects all text in the editor."""
        self.text_area.tag_add(tk.SEL, "1.0", tk.END)
        self.text_area.mark_set(tk.INSERT, tk.END)
        return 'break'

    def _insert_time_date(self, event=None):
        """Inserts current time and date."""
        now = datetime.datetime.now().strftime("%H:%M %m/%d/%Y")
        self.text_area.insert(tk.INSERT, now)
        return 'break'

    def _find_dialog(self):
        """Opens the Find dialog."""
        FindDialog(self.master, self.text_area, self)

    def _find_next(self):
        """Find next occurrence using last search term."""
        if not self.last_find_term:
            messagebox.showinfo("Find Next", "Use Ctrl+F to open Find dialog first.")
            return
        
        start_pos = self.text_area.index(tk.INSERT)
        pos = self.text_area.search(self.last_find_term, start_pos, tk.END, 
                                    nocase=not self.last_find_case_sensitive)
        
        if pos:
            self.text_area.tag_remove(tk.SEL, "1.0", tk.END)
            end_pos = f"{pos}+{len(self.last_find_term)}c"
            self.text_area.tag_add(tk.SEL, pos, end_pos)
            self.text_area.mark_set(tk.INSERT, end_pos)
            self.text_area.see(pos)
        else:
            # Wrap around to beginning
            pos = self.text_area.search(self.last_find_term, "1.0", start_pos,
                                       nocase=not self.last_find_case_sensitive)
            if pos:
                self.text_area.tag_remove(tk.SEL, "1.0", tk.END)
                end_pos = f"{pos}+{len(self.last_find_term)}c"
                self.text_area.tag_add(tk.SEL, pos, end_pos)
                self.text_area.mark_set(tk.INSERT, end_pos)
                self.text_area.see(pos)
            else:
                messagebox.showinfo("Find Next", f"Cannot find \"{self.last_find_term}\"")

    def _find_prev(self):
        """Find previous occurrence using last search term."""
        if not self.last_find_term:
            messagebox.showinfo("Find Previous", "Use Ctrl+F to open Find dialog first.")
            return
        
        start_pos = self.text_area.index(tk.INSERT)
        pos = self.text_area.search(self.last_find_term, start_pos, "1.0", 
                                    backwards=True, nocase=not self.last_find_case_sensitive)
        
        if pos:
            self.text_area.tag_remove(tk.SEL, "1.0", tk.END)
            end_pos = f"{pos}+{len(self.last_find_term)}c"
            self.text_area.tag_add(tk.SEL, pos, end_pos)
            self.text_area.mark_set(tk.INSERT, pos)
            self.text_area.see(pos)
        else:
            # Wrap around to end
            pos = self.text_area.search(self.last_find_term, tk.END, start_pos,
                                       backwards=True, nocase=not self.last_find_case_sensitive)
            if pos:
                self.text_area.tag_remove(tk.SEL, "1.0", tk.END)
                end_pos = f"{pos}+{len(self.last_find_term)}c"
                self.text_area.tag_add(tk.SEL, pos, end_pos)
                self.text_area.mark_set(tk.INSERT, pos)
                self.text_area.see(pos)
            else:
                messagebox.showinfo("Find Previous", f"Cannot find \"{self.last_find_term}\"")

    def _replace_dialog(self):
        """Opens the Replace dialog."""
        ReplaceDialog(self.master, self.text_area)

    def _goto_line(self):
        """Opens Go To Line dialog."""
        line_num = simpledialog.askinteger("Go To Line", "Line number:", parent=self.master, minvalue=1)
        if line_num:
            self.text_area.mark_set(tk.INSERT, f"{line_num}.0")
            self.text_area.see(tk.INSERT)

    def _toggle_word_wrap(self):
        """Toggles word wrap on and off."""
        if self.word_wrap_var.get():
            self.text_area.config(wrap='word')
        else:
            self.text_area.config(wrap='none')
        self._save_preferences()

    def _font_dialog(self):
        """Opens font selection dialog."""
        dialog = tk.Toplevel(self.master)
        dialog.title("Font")
        set_window_icon(dialog)
        dialog.geometry("300x150")
        dialog.transient(self.master)
        
        tk.Label(dialog, text="Font size:").pack(pady=10)
        
        size_var = tk.IntVar(value=self.current_font_size)
        spinbox = tk.Spinbox(dialog, from_=8, to=72, textvariable=size_var, width=10)
        spinbox.pack(pady=5)
        
        def apply_font():
            self.current_font_size = size_var.get()
            self.text_area.config(font=('Consolas', self.current_font_size))
            self._save_preferences()
            dialog.destroy()
        
        tk.Button(dialog, text="OK", command=apply_font, width=10).pack(pady=10)

    def _toggle_status_bar(self):
        """Shows or hides the status bar."""
        if self.status_bar_var.get():
            self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
            self._update_status_bar()
        else:
            self.status_bar.pack_forget()
        self._save_preferences()

    def _toggle_line_numbers(self):
        """Shows or hides line numbers."""
        if self.line_numbers_var.get():
            self.line_numbers_frame.pack(side=tk.RIGHT, fill=tk.Y)
            self.line_numbers.pack(side=tk.RIGHT, fill=tk.Y)
            self.line_numbers.redraw()
        else:
            self.line_numbers_frame.pack_forget()
        self._save_preferences()

    def _toggle_highlight_syntax(self):
        """Toggles syntax highlighting on and off."""
        if self.highlight_syntax_var.get() != "off":  # Check the checkbox variable, not the preference
            self.text_area.bind('<KeyRelease>', lambda e: (
                self._update_status_bar(e), 
                self._apply_live_features(e)
            ))
            self._apply_live_features()
        else:
            for tag in ["math_num", "math_var", "math_op", "bracket_match", "bracket_err"]:
                self.text_area.tag_remove(tag, "1.0", tk.END)
            self.text_area.bind('<KeyRelease>', self._update_status_bar)
    
        self._save_preferences()

    def _update_status_bar(self, event=None):
        """Updates the status bar with current line and column."""
        if self.status_bar_var.get():
            cursor_pos = self.text_area.index(tk.INSERT)
            line, col = cursor_pos.split('.')
            self.status_bar.config(text=f"Ln {line}, Col {int(col) + 1}")

    def _zoom_in(self):
        """Increases font size."""
        if self.current_font_size < 72:
            self.current_font_size += 1
            self.text_area.config(font=('Consolas', self.current_font_size))
            self._save_preferences()

    def _zoom_out(self):
        """Decreases font size."""
        if self.current_font_size > 8:
            self.current_font_size -= 1
            self.text_area.config(font=('Consolas', self.current_font_size))
            self._save_preferences()

    def _zoom_reset(self):
        """Resets font size to default."""
        self.current_font_size = 11
        self.text_area.config(font=('Consolas', self.current_font_size))
        self._save_preferences()

    def _change_theme(self, theme: str):
        """Change the color theme."""
        self.preferences.theme = theme
        self._apply_theme(theme)
        self._save_preferences()

    def _show_formula_help(self):
        """Show formula help dialog."""
        help_text = """Formula Evaluation Help

How to use:
1. Type a mathematical expression followed by '='
2. Press Ctrl+E or use Edit > Evaluate Formula
3. The result will replace the '='

Available Operators:
  +  Addition
  -  Subtraction
  *  Multiplication
  /  Division
  // Floor Division
  %  Modulo
  ** Power

Available Functions:
  abs, round, min, max, sum, pow
  sqrt, sin, cos, tan
  log, log10, exp

Constants:
  pi, e

Examples:
  2 + 2 * 3 =
  sqrt(16) =
  sin(pi/2) =
  2**8 =
  
Variables:
  Results are automatically stored and can be reused
  Use Edit > Clear Variables to reset

Selection Mode:
  Select text to evaluate only that portion"""
        
        dialog = tk.Toplevel(self.master)
        dialog.title("Formula Help")
        set_window_icon(dialog)
        dialog.geometry("500x500")
        dialog.transient(self.master)
        
        text = tk.Text(dialog, wrap='word', padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert('1.0', help_text)
        text.config(state=tk.DISABLED)
        
        tk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)

    def _show_about(self):
        """Show about dialog."""
        about_text = """Enhanced Notepad
Version 2.0

A feature-rich text editor with:
- Formula evaluation
- Recent files
- Find & Replace
- Line numbers
- Dark mode
- And more!

Built with Python and Tkinter"""
        
        messagebox.showinfo("About Enhanced Notepad", about_text)


# Run the Application
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x600")
    app = NotepadApp(root)
    root.mainloop()
