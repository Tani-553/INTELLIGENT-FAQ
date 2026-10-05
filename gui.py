"""
gui.py
------
Simple Tkinter interface. It contains NO inference logic:
it only calls reasoning_trace.answer_question() and the knowledge_base / inference_engine
functions, then displays what they return.
"""

import tkinter as tk
from tkinter import messagebox

import inference_engine as engine
import knowledge_base as kb
import reasoning_trace

# Demo login only - NOT real security (see README).
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Colours
BG = "#F7F7F7"
USER_BG = "#E6E0F3"        # soft lavender
REASON_BG = "#E3F1E3"      # soft light green
ADMIN_BG = "#FDE6D5"       # soft peach
BTN_BG = "#C9CED6"         # muted grey-blue
BTN_ACTIVE = "#B5BBC5"
TEXT_BG = "#FFFFFF"

TITLE_FONT = ("Segoe UI", 15, "bold")
LABEL_FONT = ("Segoe UI", 10, "bold")
TEXT_FONT = ("Segoe UI", 10)
MONO_FONT = ("Consolas", 10)


def make_button(parent, text, command, width=12):
    return tk.Button(parent, text=text, command=command, width=width, bg=BTN_BG,
                     activebackground=BTN_ACTIVE, relief="flat", font=TEXT_FONT, cursor="hand2")


def make_text_box(parent, height, font=TEXT_FONT, state="disabled"):
    """A text box with a scrollbar. Returns the Text widget."""
    frame = tk.Frame(parent)
    scrollbar = tk.Scrollbar(frame)
    box = tk.Text(frame, height=height, wrap="word", font=font, bg=TEXT_BG, relief="solid",
                  borderwidth=1, yscrollcommand=scrollbar.set, state=state)
    scrollbar.config(command=box.yview)
    scrollbar.pack(side="right", fill="y")
    box.pack(side="left", fill="both", expand=True)
    return frame, box


def set_text(box, text):
    """Replace the contents of a read-only Text widget."""
    box.config(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", text)
    box.config(state="disabled")


# ================================================================== main (user) window

def run_app():
    root = tk.Tk()
    root.title("CityCare Hospital - Intelligent FAQ Answering System")
    root.geometry("760x680")
    root.configure(bg=BG)

    # Load the knowledge base into the inference engine at start-up.
    try:
        engine.load_knowledge_base()
    except kb.KnowledgeBaseError as err:
        messagebox.showwarning(
            "Knowledge base problem",
            "{}\n\nThe system will start with an empty knowledge base. "
            "Use Admin > Reload after fixing the file.".format(err))

    tk.Label(root, text="CityCare Hospital", font=TITLE_FONT, bg=BG).pack(pady=(12, 0))
    tk.Label(root, text="Intelligent FAQ Answering System (First-Order Logic)", font=TEXT_FONT,
             bg=BG, fg="#555555").pack(pady=(0, 8))

    # ---- question section
    user_frame = tk.Frame(root, bg=USER_BG, padx=12, pady=10)
    user_frame.pack(fill="x", padx=14, pady=4)
    tk.Label(user_frame, text="Ask your question:", font=LABEL_FONT, bg=USER_BG).pack(anchor="w")
    question_box = tk.Text(user_frame, height=3, wrap="word", font=TEXT_FONT, relief="solid", borderwidth=1)
    question_box.pack(fill="x", pady=4)
    question_box.focus_set()

    # ---- answer section
    answer_frame = tk.Frame(root, bg=BG, padx=12)
    answer_frame.pack(fill="x", padx=14, pady=(6, 0))
    tk.Label(answer_frame, text="Answer", font=LABEL_FONT, bg=BG).pack(anchor="w")
    answer_holder, answer_box = make_text_box(answer_frame, height=6)
    answer_holder.pack(fill="x", pady=4)

    # ---- reasoning section
    reason_frame = tk.Frame(root, bg=REASON_BG, padx=12, pady=8)
    reason_frame.pack(fill="both", expand=True, padx=14, pady=8)
    tk.Label(reason_frame, text="Reasoning Trace", font=LABEL_FONT, bg=REASON_BG).pack(anchor="w")
    reason_holder, reason_box = make_text_box(reason_frame, height=10, font=MONO_FONT)
    reason_holder.pack(fill="both", expand=True, pady=4)

    def ask_question(event=None):
        question = question_box.get("1.0", "end").strip()
        result = reasoning_trace.answer_question(question)
        set_text(answer_box, result["answer"])
        set_text(reason_box, result["trace"])
        return "break"          # stops Enter from adding a new line in the question box

    def clear_all():
        question_box.delete("1.0", "end")
        set_text(answer_box, "")
        set_text(reason_box, "")
        question_box.focus_set()

    question_box.bind("<Return>", ask_question)       # Enter = ask,  Shift+Enter = new line
    question_box.bind("<Shift-Return>", lambda e: None)

    button_row = tk.Frame(user_frame, bg=USER_BG)
    button_row.pack(fill="x")
    make_button(button_row, "Ask Question", ask_question, width=14).pack(side="left", padx=(0, 6))
    make_button(button_row, "Clear", clear_all, width=8).pack(side="left")
    make_button(button_row, "Admin", lambda: open_login_window(root), width=7).pack(side="right")

    root.mainloop()


# ================================================================== admin login

def open_login_window(parent):
    window = tk.Toplevel(parent)
    window.title("Admin Login")
    window.geometry("300x190")
    window.configure(bg=ADMIN_BG)
    window.resizable(False, False)
    window.transient(parent)
    window.grab_set()

    tk.Label(window, text="Administrator Login", font=LABEL_FONT, bg=ADMIN_BG).pack(pady=(14, 8))
    form = tk.Frame(window, bg=ADMIN_BG)
    form.pack()
    tk.Label(form, text="Username:", bg=ADMIN_BG, font=TEXT_FONT).grid(row=0, column=0, sticky="e", pady=3)
    username_entry = tk.Entry(form, width=20)
    username_entry.grid(row=0, column=1, pady=3, padx=4)
    tk.Label(form, text="Password:", bg=ADMIN_BG, font=TEXT_FONT).grid(row=1, column=0, sticky="e", pady=3)
    password_entry = tk.Entry(form, width=20, show="*")
    password_entry.grid(row=1, column=1, pady=3, padx=4)
    username_entry.focus_set()

    def login(event=None):
        if username_entry.get().strip() == ADMIN_USERNAME and password_entry.get() == ADMIN_PASSWORD:
            window.destroy()
            open_admin_window(parent)
        else:
            messagebox.showerror("Login failed", "Incorrect username or password.", parent=window)
            password_entry.delete(0, "end")

    make_button(window, "Login", login, width=10).pack(pady=12)
    window.bind("<Return>", login)


# ================================================================== admin window

def open_admin_window(parent):
    window = tk.Toplevel(parent)
    window.title("Administrator / Knowledge Engineer")
    window.geometry("720x700")
    window.configure(bg=ADMIN_BG)

    state = {"facts": []}     # the facts currently shown (same as knowledge_base.json)

    tk.Label(window, text="Administrator / Knowledge Engineer", font=TITLE_FONT, bg=ADMIN_BG).pack(pady=(10, 4))
    status_label = tk.Label(window, text="", bg=ADMIN_BG, fg="#444444", font=TEXT_FONT)

    # ---- facts list
    tk.Label(window, text="Facts:", font=LABEL_FONT, bg=ADMIN_BG).pack(anchor="w", padx=14)
    list_frame = tk.Frame(window)
    list_frame.pack(fill="both", expand=True, padx=14, pady=4)
    scrollbar = tk.Scrollbar(list_frame)
    fact_list = tk.Listbox(list_frame, font=MONO_FONT, yscrollcommand=scrollbar.set,
                           activestyle="none", exportselection=False, relief="solid", borderwidth=1)
    scrollbar.config(command=fact_list.yview)
    scrollbar.pack(side="right", fill="y")
    fact_list.pack(side="left", fill="both", expand=True)

    def show_status(message):
        status_label.config(text=message)

    def refresh_list():
        fact_list.delete(0, "end")
        for fact in state["facts"]:
            fact_list.insert("end", kb.fact_to_text(fact))

    def selected_index():
        chosen = fact_list.curselection()
        return chosen[0] if chosen else None

    def save_and_reload(new_facts):
        """Write to knowledge_base.json, then reload the inference engine from the file."""
        kb.save_facts(new_facts)
        state["facts"] = new_facts
        engine.load_knowledge_base()
        refresh_list()

    # ---- add / edit form
    def open_fact_form(title, button_text, initial, on_submit):
        form = tk.Toplevel(window)
        form.title(title)
        form.geometry("340x230")
        form.configure(bg=ADMIN_BG)
        form.transient(window)
        form.grab_set()

        entries = []
        for number, label in enumerate(["Predicate:", "Argument 1:", "Argument 2:"]):
            tk.Label(form, text=label, bg=ADMIN_BG, font=TEXT_FONT).grid(row=number, column=0, sticky="e", padx=8, pady=6)
            entry = tk.Entry(form, width=30)
            entry.grid(row=number, column=1, pady=6)
            if number < len(initial):
                entry.insert(0, initial[number])
            entries.append(entry)
        tk.Label(form, text="(leave Argument 2 empty for one-argument facts, e.g. department)",
                 bg=ADMIN_BG, fg="#666666", font=("Segoe UI", 8)).grid(row=3, column=0, columnspan=2)
        entries[0].focus_set()

        def submit():
            problem = on_submit(entries[0].get(), [entries[1].get(), entries[2].get()])
            if problem:
                messagebox.showerror("Invalid fact", problem, parent=form)
            else:
                form.destroy()

        make_button(form, button_text, submit, width=10).grid(row=4, column=0, columnspan=2, pady=14)

    def add_fact_clicked():
        def on_submit(predicate, args):
            try:
                save_and_reload(kb.add_fact(state["facts"], predicate, args, engine.derived_predicates()))
            except (kb.FactError, kb.KnowledgeBaseError) as err:
                return str(err)
            show_status("Fact added, saved to knowledge_base.json and inference engine reloaded.")
        open_fact_form("Add Fact", "Add", [], on_submit)

    def edit_fact_clicked():
        index = selected_index()
        if index is None:
            messagebox.showinfo("Edit Fact", "Please select a fact in the list first.", parent=window)
            return
        old = state["facts"][index]

        def on_submit(predicate, args):
            try:
                save_and_reload(kb.update_fact(state["facts"], index, predicate, args, engine.derived_predicates()))
            except (kb.FactError, kb.KnowledgeBaseError) as err:
                return str(err)
            show_status("Fact updated and saved.")
        open_fact_form("Edit Fact", "Save", [old["predicate"]] + old["args"], on_submit)

    def delete_fact_clicked():
        index = selected_index()
        if index is None:
            messagebox.showinfo("Delete Fact", "Please select a fact in the list first.", parent=window)
            return
        text = kb.fact_to_text(state["facts"][index])
        if not messagebox.askyesno("Delete Fact", "Delete this fact?\n\n" + text, parent=window):
            return
        try:
            save_and_reload(kb.delete_fact(state["facts"], index))
            show_status("Deleted: " + text)
        except (kb.FactError, kb.KnowledgeBaseError) as err:
            messagebox.showerror("Delete failed", str(err), parent=window)

    # ---- knowledge base buttons
    def save_clicked():
        try:
            save_and_reload(list(state["facts"]))
            show_status("Knowledge base saved ({} facts).".format(len(state["facts"])))
        except kb.KnowledgeBaseError as err:
            messagebox.showerror("Save failed", str(err), parent=window)

    def reload_clicked():
        try:
            state["facts"] = kb.load_facts()
            count = engine.load_knowledge_base()
            refresh_list()
            show_status("Reloaded {} facts from knowledge_base.json.".format(count))
        except kb.KnowledgeBaseError as err:
            messagebox.showerror("Reload failed", str(err), parent=window)

    def backup_clicked():
        try:
            path = kb.backup_kb()
            show_status("Backup created.")
            messagebox.showinfo("Backup", "Backup created:\n" + path, parent=window)
        except kb.KnowledgeBaseError as err:
            messagebox.showerror("Backup failed", str(err), parent=window)

    fact_buttons = tk.Frame(window, bg=ADMIN_BG)
    fact_buttons.pack(pady=4)
    for text, command in [("Add Fact", add_fact_clicked), ("Edit Fact", edit_fact_clicked),
                          ("Delete Fact", delete_fact_clicked)]:
        make_button(fact_buttons, text, command).pack(side="left", padx=5)

    tk.Label(window, text="Knowledge Base:", font=LABEL_FONT, bg=ADMIN_BG).pack(anchor="w", padx=14, pady=(8, 0))
    kb_buttons = tk.Frame(window, bg=ADMIN_BG)
    kb_buttons.pack(pady=4)
    for text, command in [("Save", save_clicked), ("Reload", reload_clicked), ("Backup", backup_clicked)]:
        make_button(kb_buttons, text, command).pack(side="left", padx=5)

    # ---- test inference
    tk.Label(window, text="Test Inference - Logical Query:", font=LABEL_FONT, bg=ADMIN_BG).pack(anchor="w", padx=14, pady=(8, 0))
    query_entry = tk.Entry(window, font=MONO_FONT)
    query_entry.insert(0, "specializes(Doctor, cardiology)")
    query_entry.pack(fill="x", padx=14, pady=4)

    result_holder, result_box = make_text_box(window, height=6, font=MONO_FONT)

    def test_query(event=None):
        try:
            predicate, args = engine.parse_logical_query(query_entry.get())
            answers = engine.query(predicate, args)
        except engine.InferenceError as err:
            set_text(result_box, str(err))
            return
        if not answers:
            set_text(result_box, "No result: nothing can be derived for {}".format(engine.format_query(predicate, args)))
        elif answers == [{}]:
            set_text(result_box, "True: {} can be derived.".format(engine.format_query(predicate, args)))
        else:
            set_text(result_box, "\n".join(", ".join("{} = {}".format(k, v) for k, v in row.items())
                                           for row in answers))

    query_entry.bind("<Return>", test_query)
    make_button(window, "Test Query", test_query).pack(pady=4)
    tk.Label(window, text="Result:", font=LABEL_FONT, bg=ADMIN_BG).pack(anchor="w", padx=14)
    result_holder.pack(fill="x", padx=14, pady=4)
    status_label.pack(pady=(2, 8))

    # ---- start: show the facts currently in the file
    try:
        state["facts"] = kb.load_facts()
        refresh_list()
        show_status("{} facts loaded.".format(len(state["facts"])))
    except kb.KnowledgeBaseError as err:
        show_status("Could not load facts - see message.")
        messagebox.showerror("Knowledge base problem", str(err), parent=window)
