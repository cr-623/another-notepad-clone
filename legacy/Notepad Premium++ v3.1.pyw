import tkinter as tk
from tkinter import filedialog, messagebox, font, simpledialog, ttk
import datetime
import os
import ast
import operator
import math
import json
import re
from typing import Tuple, Optional, Dict
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


@dataclass
class TabData:
    """Data structure to hold information about each tab."""
    text_widget: tk.Text
    scrollbar: tk.Scrollbar
    line_numbers: LineNumbers
    line_numbers_frame: tk.Frame
    current_file: Optional[str] = None
    modified: bool = False
    evaluator: SafeExpressionEvaluator = None
    
    def __post_init__(self):
        if self.evaluator is None:
            self.evaluator = SafeExpressionEvaluator()


class NotepadApp:
    def __init__(self, master):
        self.master = master
        set_window_icon(master)
        
        master.title("Untitled - Enhanced Notepad")
        
        # Load preferences
        self.preferences = self._load_preferences()
        self.current_font_size = self.preferences.font_size
        self.highlight_syntax_var = tk.StringVar(value=self.preferences.highlight_syntax)
        
        # Find/Replace state
        self.last_find_term = ""
        self.last_find_case_sensitive = False
        
        # Tab management
        self.tabs: Dict[str, TabData] = {}
        self.tab_counter = 0
        
        # Drag and drop state
        self.drag_data = {"source": None, "x": 0, "y": 0}
        
        # Create main frame
        main_frame = tk.Frame(master)
        main_frame.pack(fill=tk.BOTH, expand=1)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=1)
        
        # Bind tab events
        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)
        self.notebook.bind('<Button-2>', self._on_middle_click)  # Middle-click to close
        self.notebook.bind('<ButtonPress-1>', self._on_tab_press)  # Start drag
        self.notebook.bind('<B1-Motion>', self._on_tab_drag)  # Dragging
        self.notebook.bind('<ButtonRelease-1>', self._on_tab_release)  # End drag
        
        # Status bar
        self.status_bar = tk.Label(master, text="Ln 1, Col 1", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        
        # Menu Bar Creation
        self.menu_bar = tk.Menu(master)
        master.config(menu=self.menu_bar)
        
        self._create_file_menu()
        self._create_edit_menu()
        self._create_format_menu()
        self._create_view_menu()
        self._create_help_menu()
        
        # Context Menu Creation
        self._create_context_menu()

        # Keyboard Bindings
        self._setup_key_bindings()
        
        # Create first tab
        self._new_tab()
        
        # Apply saved preferences
        self._apply_preferences()
        
        # Handle window close
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

    # =========================================================================
    # TAB MANAGEMENT
    # =========================================================================
    
    def _new_tab(self, filename=None, content=""):
        """Create a new tab."""
        self.tab_counter += 1
        tab_id = f"tab_{self.tab_counter}"
        
        # Create frame for this tab
        tab_frame = tk.Frame(self.notebook)
        
        # Line numbers frame
        line_numbers_frame = tk.Frame(tab_frame)
        
        # Text Area and Scrollbar Setup
        text_frame = tk.Frame(tab_frame)
        text_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=1)
        
        text_area = tk.Text(text_frame, wrap='word', undo=True, font=('Consolas', self.current_font_size))
        scrollbar = tk.Scrollbar(text_frame, command=text_area.yview)
        text_area.config(yscrollcommand=scrollbar.set)
        
        # Line numbers
        line_numbers = LineNumbers(line_numbers_frame, text_area)
        
        # Track modifications
        text_area.bind('<<Modified>>', lambda e: self._on_text_modified(tab_id))
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_area.pack(fill=tk.BOTH, expand=1)
        
        # Insert content if provided
        if content:
            text_area.insert(1.0, content)
        
        # Create tab data
        tab_data = TabData(
            text_widget=text_area,
            scrollbar=scrollbar,
            line_numbers=line_numbers,
            line_numbers_frame=line_numbers_frame,
            current_file=filename
        )
        
        self.tabs[tab_id] = tab_data
        
        # Add tab to notebook
        tab_title = os.path.basename(filename) if filename else f"Untitled {self.tab_counter}"
        self.notebook.add(tab_frame, text=tab_title)
        
        # Select the new tab
        self.notebook.select(tab_frame)
        
        # Set up bindings for this text widget
        self._setup_text_widget_bindings(text_area, tab_id)
        
        # Apply current theme to new tab
        self._apply_theme_to_tab(tab_data, self.preferences.theme)
        
        # Apply word wrap setting
        wrap_mode = 'word' if self.word_wrap_var.get() else 'none'
        text_area.config(wrap=wrap_mode)
        
        # Apply line numbers setting
        if self.line_numbers_var.get():
            line_numbers_frame.pack(side=tk.LEFT, fill=tk.Y)
            line_numbers.pack(side=tk.LEFT, fill=tk.Y)
            line_numbers.redraw()
        
        # Apply syntax highlighting if enabled
        if self.highlight_syntax_var.get() != "off":
            self._apply_live_features_to_tab(tab_data)
        
        # Update title
        self._update_window_title()
        
        # Focus the text area
        text_area.focus_set()
        
        return tab_id
    
    def _close_tab(self, tab_id=None):
        """Close a tab."""
        if tab_id is None:
            tab_id = self._get_current_tab_id()
        
        if tab_id is None:
            return
        
        tab_data = self.tabs[tab_id]
        
        # Check if file needs saving
        if tab_data.modified:
            filename = os.path.basename(tab_data.current_file) if tab_data.current_file else "Untitled"
            response = messagebox.askyesnocancel("Save Changes", 
                f"Do you want to save changes to '{filename}'?")
            if response:
                self._save_file(tab_id)
            elif response is None:
                return False
        
        # Find and remove the tab
        for i, frame in enumerate(self.notebook.tabs()):
            if self._get_tab_id_from_index(i) == tab_id:
                self.notebook.forget(i)
                break
        
        # Remove from tabs dict
        del self.tabs[tab_id]
        
        # If no tabs left, close the window instead of creating a new tab
        if len(self.tabs) == 0:
            self._save_preferences()
            self.master.quit()
            return True
        
        self._update_window_title()
        return True
    
    def _get_current_tab_id(self):
        """Get the ID of the currently selected tab."""
        try:
            current_index = self.notebook.index(self.notebook.select())
            return self._get_tab_id_from_index(current_index)
        except:
            return None
    
    def _get_tab_id_from_index(self, index):
        """Get tab ID from notebook index."""
        for i, (tab_id, tab_data) in enumerate(self.tabs.items()):
            if i == index:
                return tab_id
        return None
    
    def _get_current_tab(self) -> Optional[TabData]:
        """Get the current tab data."""
        tab_id = self._get_current_tab_id()
        if tab_id:
            return self.tabs[tab_id]
        return None
    
    def _on_tab_changed(self, event=None):
        """Called when the active tab changes."""
        self._update_window_title()
        self._update_status_bar()
        
        # Apply current preferences to the new tab
        tab_data = self._get_current_tab()
        if tab_data:
            if self.preferences.line_numbers:
                tab_data.line_numbers_frame.pack(side=tk.LEFT, fill=tk.Y)
                tab_data.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
                tab_data.line_numbers.redraw()
            # Focus the text area when switching tabs
            tab_data.text_widget.focus_set()
    
    def _update_tab_title(self, tab_id, modified=None):
        """Update the title of a specific tab."""
        if tab_id not in self.tabs:
            return
        
        tab_data = self.tabs[tab_id]
        
        if modified is not None:
            tab_data.modified = modified
        
        # Find the tab index
        for i, (tid, tdata) in enumerate(self.tabs.items()):
            if tid == tab_id:
                modified_marker = "*" if tab_data.modified else ""
                if tab_data.current_file:
                    title = f"{modified_marker}{os.path.basename(tab_data.current_file)}"
                else:
                    tab_num = tab_id.split('_')[1]
                    title = f"{modified_marker}Untitled {tab_num}"
                
                self.notebook.tab(i, text=title)
                break
        
        self._update_window_title()
    
    def _update_window_title(self):
        """Update the main window title."""
        tab_data = self._get_current_tab()
        if tab_data:
            base_title = " - Enhanced Notepad"
            modified_marker = "*" if tab_data.modified else ""
            if tab_data.current_file:
                self.master.title(f"{modified_marker}{os.path.basename(tab_data.current_file)}{base_title}")
            else:
                tab_id = self._get_current_tab_id()
                tab_num = tab_id.split('_')[1] if tab_id else "1"
                self.master.title(f"{modified_marker}Untitled {tab_num}{base_title}")

    # =========================================================================
    # TAB DRAG AND DROP
    # =========================================================================
    
    def _on_middle_click(self, event):
        """Handle middle-click to close tab."""
        try:
            # Get the tab at the click position
            clicked_tab = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if clicked_tab != "":
                tab_id = self._get_tab_id_from_index(int(clicked_tab))
                if tab_id:
                    self._close_tab(tab_id)
        except:
            pass
    
    def _on_tab_press(self, event):
        """Handle mouse press on tab to start dragging."""
        try:
            clicked_tab = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            if clicked_tab != "":
                self.drag_data["source"] = int(clicked_tab)
                self.drag_data["x"] = event.x
                self.drag_data["y"] = event.y
        except:
            pass
    
    def _on_tab_drag(self, event):
        """Handle tab dragging."""
        if self.drag_data["source"] is None:
            return
        
        # Visual feedback could be added here
        pass
    
    def _on_tab_release(self, event):
        """Handle tab release to reorder tabs."""
        if self.drag_data["source"] is None:
            return
        
        try:
            # Get the tab at the release position
            target_tab = self.notebook.tk.call(self.notebook._w, "identify", "tab", event.x, event.y)
            
            if target_tab != "" and target_tab != self.drag_data["source"]:
                target_index = int(target_tab)
                source_index = self.drag_data["source"]
                
                # Get all tab IDs in current order
                tab_list = list(self.tabs.keys())
                
                # Reorder the tabs dictionary
                moved_tab_id = tab_list[source_index]
                tab_list.pop(source_index)
                
                # Adjust target index if needed
                if source_index < target_index:
                    target_index -= 1
                
                tab_list.insert(target_index, moved_tab_id)
                
                # Rebuild the notebook with new order
                new_tabs = {}
                for tab_id in tab_list:
                    new_tabs[tab_id] = self.tabs[tab_id]
                
                self.tabs = new_tabs
                
                # Reorder in the notebook widget
                self.notebook.insert(target_index, self.notebook.tabs()[source_index])
                
        except Exception as e:
            print(f"Tab reorder error: {e}")
        finally:
            self.drag_data["source"] = None

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
            # Apply to all tabs
            for tab_data in self.tabs.values():
                self._apply_live_features_to_tab(tab_data)
        
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
        
        # Apply to all tabs
        for tab_data in self.tabs.values():
            self._apply_theme_to_tab(tab_data, theme)
    
    def _apply_theme_to_tab(self, tab_data, theme: str):
        """Apply color theme to a specific tab."""
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
        
        tab_data.text_widget.config(
            bg=bg_color,
            fg=fg_color,
            insertbackground=insert_color,
            selectbackground=select_bg,
            selectforeground=select_fg
        )
        tab_data.line_numbers.config(bg=line_num_bg)
        tab_data.line_numbers.text_color = line_num_fg

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
        if not os.path.exists(filepath):
            messagebox.showerror("File Not Found", f"The file '{filepath}' no longer exists.")
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
        
        file_menu.add_command(label="New Tab", command=lambda: self._new_tab(), accelerator="Ctrl+T", underline=0)
        file_menu.add_command(label="New Window", command=self.new_window, accelerator="Ctrl+Shift+N", underline=4)
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O", underline=0)
        
        # Recent files submenu
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Files", menu=self.recent_menu, underline=0)
        self._update_recent_files_menu()
        
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=lambda: self._save_file(), accelerator="Ctrl+S", underline=0)
        file_menu.add_command(label="Save As...", command=lambda: self._save_file_as(), accelerator="Ctrl+Shift+S", underline=5)
        file_menu.add_command(label="Save All", command=self._save_all, underline=5)
        file_menu.add_separator()
        file_menu.add_command(label="Close Tab", command=lambda: self._close_tab(), accelerator="Ctrl+W", underline=0)
        file_menu.add_command(label="Close All Tabs", command=self._close_all_tabs, underline=6)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_closing, accelerator="Ctrl+Q", underline=1)

    def _create_edit_menu(self):
        """Creates the Edit menu structure and commands."""
        edit_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Edit", menu=edit_menu, underline=0)
        
        edit_menu.add_command(label="Undo", command=self._undo, accelerator="Ctrl+Z", underline=0)
        edit_menu.add_command(label="Redo", command=self._redo, accelerator="Ctrl+Y", underline=0)
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut", command=self._cut, accelerator="Ctrl+X", underline=2)
        edit_menu.add_command(label="Copy", command=self._copy, accelerator="Ctrl+C", underline=0)
        edit_menu.add_command(label="Paste", command=self._paste, accelerator="Ctrl+V", underline=0)
        edit_menu.add_command(label="Delete", command=self._delete, accelerator="Del", underline=0)
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
    # CONTEXT MENU
    # =========================================================================
    
    def _create_context_menu(self):
        """Creates the right-click context menu."""
        self.context_menu = tk.Menu(self.master, tearoff=0)
        
        self.context_menu.add_command(label="Undo", command=self._undo, accelerator="Ctrl+Z")
        self.context_menu.add_command(label="Redo", command=self._redo, accelerator="Ctrl+Y")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Cut", command=self._cut, accelerator="Ctrl+X")
        self.context_menu.add_command(label="Copy", command=self._copy, accelerator="Ctrl+C")
        self.context_menu.add_command(label="Paste", command=self._paste, accelerator="Ctrl+V")
        self.context_menu.add_command(label="Delete", command=self._delete_selection, accelerator="Del")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select All", command=self._select_all, accelerator="Ctrl+A")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Find...", command=self._find_dialog, accelerator="Ctrl+F")
        self.context_menu.add_command(label="Replace...", command=self._replace_dialog, accelerator="Ctrl+H")
        self.context_menu.add_command(label="Go To Line...", command=self._goto_line, accelerator="Ctrl+G")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Evaluate Formula", command=self._evaluate_formula, accelerator="Ctrl+E")
        self.context_menu.add_command(label="Insert Time/Date", command=self._insert_time_date, accelerator="F5")
    
    def _show_context_menu(self, event):
        """Display the context menu at the cursor position."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return
            
        try:
            # Update menu items based on selection
            has_selection = bool(tab_data.text_widget.tag_ranges(tk.SEL))
            
            # Enable/disable commands based on context
            if has_selection:
                self.context_menu.entryconfig("Cut", state=tk.NORMAL)
                self.context_menu.entryconfig("Copy", state=tk.NORMAL)
                self.context_menu.entryconfig("Delete", state=tk.NORMAL)
            else:
                self.context_menu.entryconfig("Cut", state=tk.DISABLED)
                self.context_menu.entryconfig("Copy", state=tk.DISABLED)
                self.context_menu.entryconfig("Delete", state=tk.DISABLED)
            
            # Check if clipboard has content for paste
            try:
                self.master.clipboard_get()
                self.context_menu.entryconfig("Paste", state=tk.NORMAL)
            except:
                self.context_menu.entryconfig("Paste", state=tk.DISABLED)
            
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
    
    def _delete_selection(self):
        """Delete the current selection."""
        tab_data = self._get_current_tab()
        if tab_data:
            try:
                tab_data.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                pass

    # =========================================================================
    # KEY BINDINGS SETUP
    # =========================================================================
    
    def _setup_key_bindings(self):
        """Sets up all keyboard shortcuts."""
        # File shortcuts - Changed Ctrl+N to Ctrl+T
        self.master.bind('<Control-t>', lambda e: self._new_tab())
        self.master.bind('<Control-Shift-N>', lambda e: self.new_window())
        self.master.bind('<Control-o>', lambda e: self.open_file())
        self.master.bind('<Control-s>', lambda e: self._save_file())
        self.master.bind('<Control-Shift-S>', lambda e: self._save_file_as())
        self.master.bind('<Control-w>', lambda e: self._close_tab())
        self.master.bind('<Control-q>', lambda e: self._on_closing())
        
        # Tab navigation
        self.master.bind('<Control-Tab>', self._next_tab)
        self.master.bind('<Control-Shift-Tab>', self._prev_tab)
        
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
        self.master.bind('<Control-y>', lambda e: self._redo())
        
        # Zoom shortcuts
        self.master.bind('<Control-plus>', lambda e: self._zoom_in())
        self.master.bind('<Control-equal>', lambda e: self._zoom_in())
        self.master.bind('<Control-minus>', lambda e: self._zoom_out())
        self.master.bind('<Control-0>', lambda e: self._zoom_reset())
    
    def _setup_text_widget_bindings(self, text_widget, tab_id):
        """Set up bindings for a specific text widget."""
        # Semantic shortcuts
        text_widget.bind('<Control-BackSpace>', self._delete_word_left)
        text_widget.bind('<Control-Delete>', self._delete_word_right)
        
        # Right-click context menu
        text_widget.bind('<Button-3>', self._show_context_menu)
        
        # Cursor tracking for status bar
        text_widget.bind('<KeyRelease>', lambda e: (self._update_status_bar(e), self._apply_live_features(e)))
        text_widget.bind('<ButtonRelease-1>', self._update_status_bar)
    
    def _next_tab(self, event=None):
        """Switch to next tab."""
        try:
            current = self.notebook.index(self.notebook.select())
            total = len(self.notebook.tabs())
            next_tab = (current + 1) % total
            self.notebook.select(next_tab)
        except:
            pass
        return "break"
    
    def _prev_tab(self, event=None):
        """Switch to previous tab."""
        try:
            current = self.notebook.index(self.notebook.select())
            total = len(self.notebook.tabs())
            prev_tab = (current - 1) % total
            self.notebook.select(prev_tab)
        except:
            pass
        return "break"

    # =========================================================================
    # FORMULA EVALUATION
    # =========================================================================

    def pre_process_expression(self, expr: str) -> str:
        """Pre-process expression for evaluation."""
        expr = expr.replace('^', '**')
        expr = re.sub(r'(\d)(?![eE][+-]?\d)([a-zA-Z\(])', r'\1*\2', expr)
        expr = re.sub(r'(\))([0-9a-zA-Z])', r'\1*\2', expr)
        return expr

    def _evaluate_formula(self):
        """Evaluates formulas ending with '='."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return
        
        text_area = tab_data.text_widget
        evaluator = tab_data.evaluator
        
        try:
            selected_text = text_area.get(tk.SEL_FIRST, tk.SEL_LAST)
            has_selection = True
            start_idx = text_area.index(tk.SEL_FIRST)
            end_idx = text_area.index(tk.SEL_LAST)
        except tk.TclError:
            has_selection = False
            selected_text = text_area.get("1.0", tk.END)
            start_idx = "1.0"
            end_idx = tk.END
        
        lines = selected_text.split('\n')
        modified = False
        new_lines = []

        for line in lines:
            stripped = line.rstrip()
            
            if stripped.endswith('='):
                content = stripped[:-1].strip()
                
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
                
                if formula_to_eval:
                    success, result, error = evaluator.evaluate(self.pre_process_expression(formula_to_eval))
                    
                    if success:
                        if isinstance(result, (float, int)):
                            if abs(result) >= 1e10 or (abs(result) < 1e-4 and result != 0):
                                result_str = f"{result:.4e}"
                            else:
                                result_str = f"{result:.10f}".rstrip('0').rstrip('.')
                        else:
                            result_str = str(result)
                        
                        if var_name:
                            evaluator.variables[var_name] = result
                            if prefix:
                                new_lines.append(f"{var_name}{var_separator} {prefix}{result_str}")
                            else:
                                new_lines.append(f"{var_name} {var_separator} {result_str}")
                        else:
                            if prefix:
                                new_lines.append(f"{prefix}{result_str}")
                            else:
                                new_lines.append(f"{formula_to_eval} = {result_str}")
                        
                        modified = True
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        if modified:
            text_area.edit_separator()
            if has_selection:
                text_area.delete(start_idx, end_idx)
                text_area.insert(start_idx, '\n'.join(new_lines))
            else:
                text_area.delete("1.0", tk.END)
                text_area.insert("1.0", '\n'.join(new_lines))
            text_area.edit_separator()

    def _list_variables(self):
        """Shows a dialog with all currently defined variables."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return
            
        variables = tab_data.evaluator.variables
        
        if not variables:
            messagebox.showinfo("Variables", "No variables currently defined.")
            return

        var_list = []
        for name, value in sorted(variables.items()):
            if isinstance(value, float):
                val_str = f"{value:.10f}".rstrip('0').rstrip('.')
            else:
                val_str = str(value)
            var_list.append(f"{name} = {val_str}")
        
        help_text = "Current Variables:\n" + "-" * 20 + "\n" + "\n".join(var_list)

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
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.evaluator.clear_variables()
            messagebox.showinfo("Clear Variables", "All formula variables have been cleared.")

    # =========================================================================
    # SYNTAX HIGHLIGHTING
    # =========================================================================

    def _add_regex_tags(self, text_area, pattern, tag_name):
        """Helper to apply a tag to all regex matches."""
        start = "1.0"
        while True:
            count = tk.IntVar()
            pos = text_area.search(pattern, start, stopindex=tk.END, regexp=True, count=count)
            if not pos or count.get() == 0: 
                break
            
            end_pos = f"{pos} + {count.get()} chars"
            text_area.tag_add(tag_name, pos, end_pos)
            start = end_pos

    def _highlight_text_in_brackets(self, text_area):
        """Highlight all text inside parentheses, brackets, and braces."""
        content = text_area.get("1.0", tk.END)
        
        for i, char in enumerate(content):
            if char in "([{":
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
                
                if depth == 0:
                    start_idx = f"1.0 + {i + 1} chars"
                    end_idx = f"1.0 + {j - 1} chars"
                    text_area.tag_add("bracket_text", start_idx, end_idx)

    def _apply_live_features_to_tab(self, tab_data):
        """Handles bracket matching and syntax coloring for a specific tab."""
        if not tab_data:
            return
            
        text_area = tab_data.text_widget
        mode = self.highlight_syntax_var.get()
        
        if mode == "off":
            return
        
        if mode == "code":
            text_area.tag_configure("bracket_text", foreground="#7da8ff")
            text_area.tag_configure("math_num", foreground="#445ad4")
            text_area.tag_configure("math_var", foreground="#e06c75")
            text_area.tag_configure("math_op", foreground="#44ccd4")
            text_area.tag_configure("string", foreground="#21ad4d")
            text_area.tag_configure("bracket_match", foreground="#1400eb")
            text_area.tag_configure("bracket_err", background="#ef4444", foreground="white")
            text_area.tag_configure("function", foreground="#ffeb3b")
            text_area.tag_configure("punct", foreground="#484848")
        elif mode == "text":
            text_area.tag_configure("bracket_text", foreground="#000000")
            text_area.tag_configure("math_num", foreground="#898989")
            text_area.tag_configure("math_var", foreground="#484848")
            text_area.tag_configure("math_op", foreground="#898989")
            text_area.tag_configure("string", foreground="#b3b3b3")
            text_area.tag_configure("bracket_match", foreground="#000000")
            text_area.tag_configure("bracket_err", background="#000000")
            text_area.tag_configure("function", foreground="#484848")
            text_area.tag_configure("punct", foreground="#000000")

        for tag in ["math_num", "math_var", "math_op", "bracket_match", "bracket_err", "string", "bracket_text", "function", "punct"]:
            text_area.tag_remove(tag, "1.0", tk.END)

        if mode == "code":
            self._highlight_text_in_brackets(text_area)

        self._add_regex_tags(text_area, r'\b\d+(\.\d+)?\b', "math_num")
        self._add_regex_tags(text_area, r'\d+\.?\d*([eE][+-]?\d+)?', "math_num")
        self._add_regex_tags(text_area, r'[\,\!\:\;\&\.]', "punct")
        self._add_regex_tags(text_area, r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', "math_var")
        self._add_regex_tags(text_area, r'[\+\-\*\/\=\%\^]', "math_op")
        self._add_regex_tags(text_area, r'"[^"]*"', "string")
        self._add_regex_tags(text_area, r"'[^']*'", "string")
        self._add_regex_tags(text_area, r'[a-zA-Z_][a-zA-Z0-9_]*(?=\()', "function")

        if mode == "text":
            self._highlight_text_in_brackets(text_area)

        content = text_area.get("1.0", tk.END)
        stack = []
        pairs = {')': '(', ']': '[', '}': '{'}
        for i, char in enumerate(content):
            idx = f"1.0 + {i} chars"
            if char in "([{":
                stack.append((char, idx))
            elif char in ")]}":
                if stack and stack[-1][0] == pairs[char]:
                    _, open_idx = stack.pop()
                    text_area.tag_add("bracket_match", open_idx, f"{open_idx} + 1 chars")
                    text_area.tag_add("bracket_match", idx, f"{idx} + 1 chars")
                else:
                    text_area.tag_add("bracket_err", idx, f"{idx} + 1 chars")
                    self.master.bell()

        for _, idx in stack:
            text_area.tag_add("bracket_err", idx, f"{idx} + 1 chars")

    def _apply_live_features(self, event=None):
        """Handles bracket matching and syntax coloring for current tab."""
        tab_data = self._get_current_tab()
        if tab_data:
            self._apply_live_features_to_tab(tab_data)

    # =========================================================================
    # COMMAND IMPLEMENTATION METHODS
    # =========================================================================

    def _delete_word_left(self, event=None):
        """Deletes the word to the left of the cursor."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return "break"
            
        text_area = tab_data.text_widget
        if text_area.tag_ranges(tk.SEL):
            text_area.delete(tk.SEL_FIRST, tk.SEL_LAST)
        else:
            text_area.delete("insert-1c wordstart", "insert")
        return "break"

    def _delete_word_right(self, event=None):
        """Deletes the word to the right of the cursor."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return "break"
            
        text_area = tab_data.text_widget
        if text_area.tag_ranges(tk.SEL):
            text_area.delete(tk.SEL_FIRST, tk.SEL_LAST)
        else:
            text_area.delete("insert", "insert wordend")
        return "break"

    def _on_text_modified(self, tab_id):
        """Called when text is modified."""
        if tab_id not in self.tabs:
            return
            
        tab_data = self.tabs[tab_id]
        if tab_data.text_widget.edit_modified():
            if not tab_data.modified:
                self._update_tab_title(tab_id, modified=True)
            tab_data.text_widget.edit_modified(False)

    def _on_closing(self):
        """Handle window close event."""
        # Check all tabs for unsaved changes
        for tab_id in list(self.tabs.keys()):
            if not self._close_tab(tab_id):
                return
        
        self._save_preferences()
        self.master.quit()

    def new_window(self, event=None):
        """Creates a new window."""
        new_root = tk.Tk()
        set_window_icon(new_root)
        new_root.geometry("800x600")
        NotepadApp(new_root)

    def open_file(self, event=None):
        """Opens a file in a new tab."""
        filepath = filedialog.askopenfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not filepath:
            return
            
        try:
            with open(filepath, "r", encoding='utf-8') as input_file:
                content = input_file.read()
            self._new_tab(filename=filepath, content=content)
            self._update_recent_files(filepath)
        except Exception as e:
            messagebox.showerror("Open File Error", f"Could not read file: {e}")

    def _save_file(self, tab_id=None):
        """Saves the current file."""
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
        """Saves the file with a new name."""
        if tab_id is None:
            tab_id = self._get_current_tab_id()
        
        if tab_id is None:
            return
            
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not filepath:
            return
            
        self._write_file(tab_id, filepath)
        tab_data = self.tabs[tab_id]
        tab_data.current_file = filepath
        self._update_tab_title(tab_id)
        self._update_recent_files(filepath)
        
    def _write_file(self, tab_id, filepath):
        """Helper to write content to a given path."""
        tab_data = self.tabs[tab_id]
        try:
            with open(filepath, "w", encoding='utf-8') as output_file:
                text = tab_data.text_widget.get(1.0, tk.END)
                if text.endswith('\n'):
                    text = text[:-1]
                output_file.write(text)
            self._update_tab_title(tab_id, modified=False)
        except Exception as e:
            messagebox.showerror("Save File Error", f"Could not save file: {e}")
    
    def _save_all(self):
        """Save all open tabs."""
        for tab_id in self.tabs.keys():
            self._save_file(tab_id)
    
    def _close_all_tabs(self):
        """Close all tabs."""
        for tab_id in list(self.tabs.keys()):
            if not self._close_tab(tab_id):
                return

    def _undo(self):
        """Undo last action."""
        tab_data = self._get_current_tab()
        if tab_data:
            try:
                tab_data.text_widget.edit_undo()
            except:
                pass
    
    def _redo(self):
        """Redo last action."""
        tab_data = self._get_current_tab()
        if tab_data:
            try:
                tab_data.text_widget.edit_redo()
            except:
                pass
    
    def _cut(self):
        """Cut selected text."""
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.event_generate("<<Cut>>")
    
    def _copy(self):
        """Copy selected text."""
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.event_generate("<<Copy>>")
    
    def _paste(self):
        """Paste from clipboard."""
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.event_generate("<<Paste>>")
    
    def _delete(self):
        """Delete selected text."""
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.event_generate("<Delete>")

    def _select_all(self, event=None):
        """Selects all text in the editor."""
        tab_data = self._get_current_tab()
        if tab_data:
            tab_data.text_widget.tag_add(tk.SEL, "1.0", tk.END)
            tab_data.text_widget.mark_set(tk.INSERT, tk.END)
        return 'break'

    def _insert_time_date(self, event=None):
        """Inserts current time and date."""
        tab_data = self._get_current_tab()
        if tab_data:
            now = datetime.datetime.now().strftime("%H:%M %m/%d/%Y")
            tab_data.text_widget.insert(tk.INSERT, now)
        return 'break'

    def _find_dialog(self):
        """Opens the Find dialog."""
        tab_data = self._get_current_tab()
        if tab_data:
            FindDialog(self.master, tab_data.text_widget, self)

    def _find_next(self):
        """Find next occurrence using last search term."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return
            
        if not self.last_find_term:
            messagebox.showinfo("Find Next", "Use Ctrl+F to open Find dialog first.")
            return
        
        text_area = tab_data.text_widget
        start_pos = text_area.index(tk.INSERT)
        pos = text_area.search(self.last_find_term, start_pos, tk.END, 
                                    nocase=not self.last_find_case_sensitive)
        
        if pos:
            text_area.tag_remove(tk.SEL, "1.0", tk.END)
            end_pos = f"{pos}+{len(self.last_find_term)}c"
            text_area.tag_add(tk.SEL, pos, end_pos)
            text_area.mark_set(tk.INSERT, end_pos)
            text_area.see(pos)
        else:
            pos = text_area.search(self.last_find_term, "1.0", start_pos,
                                       nocase=not self.last_find_case_sensitive)
            if pos:
                text_area.tag_remove(tk.SEL, "1.0", tk.END)
                end_pos = f"{pos}+{len(self.last_find_term)}c"
                text_area.tag_add(tk.SEL, pos, end_pos)
                text_area.mark_set(tk.INSERT, end_pos)
                text_area.see(pos)
            else:
                messagebox.showinfo("Find Next", f"Cannot find \"{self.last_find_term}\"")

    def _find_prev(self):
        """Find previous occurrence using last search term."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return
            
        if not self.last_find_term:
            messagebox.showinfo("Find Previous", "Use Ctrl+F to open Find dialog first.")
            return
        
        text_area = tab_data.text_widget
        start_pos = text_area.index(tk.INSERT)
        pos = text_area.search(self.last_find_term, start_pos, "1.0", 
                                    backwards=True, nocase=not self.last_find_case_sensitive)
        
        if pos:
            text_area.tag_remove(tk.SEL, "1.0", tk.END)
            end_pos = f"{pos}+{len(self.last_find_term)}c"
            text_area.tag_add(tk.SEL, pos, end_pos)
            text_area.mark_set(tk.INSERT, pos)
            text_area.see(pos)
        else:
            pos = text_area.search(self.last_find_term, tk.END, start_pos,
                                       backwards=True, nocase=not self.last_find_case_sensitive)
            if pos:
                text_area.tag_remove(tk.SEL, "1.0", tk.END)
                end_pos = f"{pos}+{len(self.last_find_term)}c"
                text_area.tag_add(tk.SEL, pos, end_pos)
                text_area.mark_set(tk.INSERT, pos)
                text_area.see(pos)
            else:
                messagebox.showinfo("Find Previous", f"Cannot find \"{self.last_find_term}\"")

    def _replace_dialog(self):
        """Opens the Replace dialog."""
        tab_data = self._get_current_tab()
        if tab_data:
            ReplaceDialog(self.master, tab_data.text_widget)

    def _goto_line(self):
        """Opens Go To Line dialog."""
        tab_data = self._get_current_tab()
        if not tab_data:
            return
            
        line_num = simpledialog.askinteger("Go To Line", "Line number:", parent=self.master, minvalue=1)
        if line_num:
            tab_data.text_widget.mark_set(tk.INSERT, f"{line_num}.0")
            tab_data.text_widget.see(tk.INSERT)

    def _toggle_word_wrap(self):
        """Toggles word wrap on and off."""
        wrap_mode = 'word' if self.word_wrap_var.get() else 'none'
        for tab_data in self.tabs.values():
            tab_data.text_widget.config(wrap=wrap_mode)
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
            for tab_data in self.tabs.values():
                tab_data.text_widget.config(font=('Consolas', self.current_font_size))
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
        for tab_data in self.tabs.values():
            if self.line_numbers_var.get():
                tab_data.line_numbers_frame.pack(side=tk.LEFT, fill=tk.Y)
                tab_data.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
                tab_data.line_numbers.redraw()
            else:
                tab_data.line_numbers_frame.pack_forget()
        self._save_preferences()

    def _toggle_highlight_syntax(self):
        """Toggles syntax highlighting on and off."""
        if self.highlight_syntax_var.get() != "off":
            # Apply highlighting to all tabs
            for tab_data in self.tabs.values():
                self._apply_live_features_to_tab(tab_data)
        else:
            # Remove highlighting from all tabs
            for tab_data in self.tabs.values():
                for tag in ["math_num", "math_var", "math_op", "bracket_match", "bracket_err", "string", "bracket_text", "function", "punct"]:
                    tab_data.text_widget.tag_remove(tag, "1.0", tk.END)
        self._save_preferences()

    def _update_status_bar(self, event=None):
        """Updates the status bar with current line and column."""
        if self.status_bar_var.get():
            tab_data = self._get_current_tab()
            if tab_data:
                cursor_pos = tab_data.text_widget.index(tk.INSERT)
                line, col = cursor_pos.split('.')
                self.status_bar.config(text=f"Ln {line}, Col {int(col) + 1}")

    def _zoom_in(self):
        """Increases font size."""
        if self.current_font_size < 72:
            self.current_font_size += 1
            for tab_data in self.tabs.values():
                tab_data.text_widget.config(font=('Consolas', self.current_font_size))
            self._save_preferences()

    def _zoom_out(self):
        """Decreases font size."""
        if self.current_font_size > 8:
            self.current_font_size -= 1
            for tab_data in self.tabs.values():
                tab_data.text_widget.config(font=('Consolas', self.current_font_size))
            self._save_preferences()

    def _zoom_reset(self):
        """Resets font size to default."""
        self.current_font_size = 11
        for tab_data in self.tabs.values():
            tab_data.text_widget.config(font=('Consolas', self.current_font_size))
        self._save_preferences()

    def _change_theme(self, theme: str):
        """Change the color theme."""
        self.preferences.theme = theme
        self._apply_theme(theme)
        self._save_preferences()
        # Reapply syntax highlighting with new theme colors
        if self.highlight_syntax_var.get() != "off":
            for tab_data in self.tabs.values():
                self._apply_live_features_to_tab(tab_data)

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
  Results are automatically stored per tab
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
Version 3.1

A feature-rich text editor with:
- Tabbed interface
- Middle-click to close tabs
- Drag to reorder tabs
- Formula evaluation
- Recent files
- Find & Replace
- Line numbers
- Dark mode
- Right-click context menu
- Tab navigation (Ctrl+Tab)
- And more!

Built with Python and Tkinter"""
        
        messagebox.showinfo("About Enhanced Notepad", about_text)


# Run the Application
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x600")
    app = NotepadApp(root)
    root.mainloop()
