import tkinter as tk
from tkinter import filedialog, messagebox, font, simpledialog
import datetime
import os
import ast
import operator
import math
from typing import Tuple, Optional

# Define the icon file path relative to the script
ICON_PATH = "notepad.ico"

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


class FindDialog:
    """Simple Find dialog window."""
    def __init__(self, parent, text_widget):
        self.parent = parent
        self.text_widget = text_widget
        self.last_search = ""
        self.last_pos = "1.0"
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Find")
        set_window_icon(self.dialog) 
        self.dialog.geometry("400x120")
        self.dialog.transient(parent)
        
        tk.Label(self.dialog, text="Find what:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.search_entry = tk.Entry(self.dialog, width=30)
        self.search_entry.grid(row=0, column=1, padx=5, pady=5)
        self.search_entry.focus()
        
        self.match_case_var = tk.BooleanVar()
        tk.Checkbutton(self.dialog, text="Match case", variable=self.match_case_var).grid(row=1, column=1, sticky=tk.W)
        
        tk.Button(self.dialog, text="Find Next", command=self.find_next, width=12).grid(row=0, column=2, padx=5, pady=5)
        tk.Button(self.dialog, text="Cancel", command=self.dialog.destroy, width=12).grid(row=1, column=2, padx=5, pady=5)
        
        self.search_entry.bind('<Return>', lambda e: self.find_next())
        
    def find_next(self):
        search_term = self.search_entry.get()
        if not search_term:
            return
            
        self.last_search = search_term
        
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
        self.default_font_size = 11
        self.current_font_size = self.default_font_size
        
        # Initialize formula evaluator
        self.evaluator = SafeExpressionEvaluator()
        
        # Text Area and Scrollbar Setup
        self.text_area = tk.Text(master, wrap='word', undo=True, font=('Consolas', self.current_font_size))
        self.scrollbar = tk.Scrollbar(master, command=self.text_area.yview)
        self.text_area.config(yscrollcommand=self.scrollbar.set)
        
        # Track modifications
        self.text_area.bind('<<Modified>>', self._on_text_modified)
        
        # Status bar
        self.status_bar = tk.Label(master, text="Ln 1, Col 1", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar.pack_forget()

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_area.pack(fill=tk.BOTH, expand=1)
        
        # Menu Bar Creation
        self.menu_bar = tk.Menu(master)
        master.config(menu=self.menu_bar)
        
        self._create_file_menu()
        self._create_edit_menu()
        self._create_format_menu()
        self._create_view_menu()

        # Keyboard Bindings
        self._setup_key_bindings()
        
        # Handle window close
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

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

    def _create_format_menu(self):
        """Creates the Format menu structure and commands."""
        format_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Format", menu=format_menu, underline=0)
        
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
        self.master.bind('<Control-e>', lambda e: self._evaluate_formula())
        
        # Zoom shortcuts
        self.master.bind('<Control-plus>', lambda e: self._zoom_in())
        self.master.bind('<Control-equal>', lambda e: self._zoom_in())
        self.master.bind('<Control-minus>', lambda e: self._zoom_out())
        self.master.bind('<Control-0>', lambda e: self._zoom_reset())
        
        # Cursor tracking for status bar
        self.text_area.bind('<KeyRelease>', self._update_status_bar)
        self.text_area.bind('<ButtonRelease-1>', self._update_status_bar)

    # =========================================================================
    # FORMULA EVALUATION
    # =========================================================================
    
    def _evaluate_formula(self):
        """Evaluates formulas in the text that end with '='"""
        content = self.text_area.get("1.0", tk.END)
        lines = content.split('\n')
        modified = False
        evaluated_count = 0
        error_count = 0
        
        new_lines = []
        for line in lines:
            stripped = line.rstrip()
            
            # Only process lines ending with '='
            if stripped.endswith('='):
                # Remove the trailing '='
                formula = stripped[:-1].strip()
                
                if formula:  # Make sure there's something before the '='
                    success, result, error = self.evaluator.evaluate(formula)
                    
                    if success:
                        # Format result nicely
                        if isinstance(result, float):
                            result_str = f"{result:.10f}".rstrip('0').rstrip('.')
                        else:
                            result_str = str(result)
                        
                        new_lines.append(f"{formula} = {result_str}")
                        modified = True
                        evaluated_count += 1
                    else:
                        # Keep the original line if evaluation fails
                        new_lines.append(line)
                        error_count += 1
                else:
                    # Just '=' with nothing before it
                    new_lines.append(line)
            else:
                # Line doesn't end with '=', keep as is
                new_lines.append(line)
        
        if modified:
            # Update the text area
            self.text_area.delete("1.0", tk.END)
            self.text_area.insert("1.0", '\n'.join(new_lines))
            
            # Show summary
            if error_count > 0:
                messagebox.showinfo("Evaluate Formulas", 
                    f"Evaluated {evaluated_count} formula(s).\n{error_count} error(s) encountered.")
            else:
                messagebox.showinfo("Evaluate Formulas", 
                    f"Successfully evaluated {evaluated_count} formula(s)!")
        else:
            messagebox.showinfo("Evaluate Formulas", 
                "No formulas found ending with '=' to evaluate.")

    # =========================================================================
    # COMMAND IMPLEMENTATION METHODS
    # =========================================================================

    def set_title(self, filename=None):
        """Sets the window title."""
        base_title = " - Simple Notepad"
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
        FindDialog(self.master, self.text_area)

    def _find_next(self):
        """Find next occurrence (simplified version)."""
        messagebox.showinfo("Find Next", "Use Ctrl+F to open Find dialog first.")

    def _find_prev(self):
        """Find previous occurrence."""
        messagebox.showinfo("Find Previous", "Use Ctrl+F to open Find dialog first.")

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
            dialog.destroy()
        
        tk.Button(dialog, text="OK", command=apply_font, width=10).pack(pady=10)

    def _toggle_status_bar(self):
        """Shows or hides the status bar."""
        if self.status_bar_var.get():
            self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
            self._update_status_bar()
        else:
            self.status_bar.pack_forget()

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

    def _zoom_out(self):
        """Decreases font size."""
        if self.current_font_size > 8:
            self.current_font_size -= 1
            self.text_area.config(font=('Consolas', self.current_font_size))

    def _zoom_reset(self):
        """Resets font size to default."""
        self.current_font_size = self.default_font_size
        self.text_area.config(font=('Consolas', self.current_font_size))


# Run the Application
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x600")
    app = NotepadApp(root)
    root.mainloop()
