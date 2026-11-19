"""Dark blue look for the window (ttk 'clam' theme with a navy palette)."""

PALETTE = {
    "bg": "#0b1a33",        # window
    "panel": "#10264a",     # frames, notebook tabs
    "field": "#0c1d3b",     # entry / text boxes
    "fg": "#d8e6ff",        # normal text
    "dim": "#8fa8d0",       # secondary text
    "accent": "#3a8dff",    # buttons, selection
    "accent_hi": "#5ca3ff",
    "border": "#1f3b6b",
}


def apply(root, style=None):
    """Style every ttk widget we use and the plain tk bits (combobox pop-up lists)."""
    from tkinter import ttk
    p = PALETTE
    style = style or ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001 - theme missing: keep the default, colours still apply
        pass
    try:
        root.configure(bg=p["bg"])
    except Exception:  # noqa: BLE001
        pass
    style.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                    bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"],
                    troughcolor=p["field"], focuscolor=p["accent"], font=("Segoe UI", 10))
    style.configure("TFrame", background=p["bg"])
    style.configure("TLabel", background=p["bg"], foreground=p["fg"])
    style.configure("Dim.TLabel", background=p["bg"], foreground=p["dim"])
    style.configure("TLabelframe", background=p["bg"], bordercolor=p["border"])
    style.configure("TLabelframe.Label", background=p["bg"], foreground=p["accent_hi"],
                    font=("Segoe UI", 10, "bold"))
    style.configure("TButton", background=p["panel"], foreground=p["fg"], padding=(10, 5),
                    bordercolor=p["border"])
    style.map("TButton", background=[("active", p["accent"]), ("pressed", p["accent_hi"])],
              foreground=[("active", "#ffffff")])
    style.configure("Accent.TButton", background=p["accent"], foreground="#ffffff",
                    font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("active", p["accent_hi"])])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=p["field"], foreground=p["fg"], background=p["panel"],
                        arrowcolor=p["fg"], insertcolor=p["fg"], bordercolor=p["border"])
    style.map("TCombobox", fieldbackground=[("readonly", p["field"])],
              foreground=[("readonly", p["fg"])], selectbackground=[("readonly", p["field"])],
              selectforeground=[("readonly", p["fg"])])
    style.configure("TCheckbutton", background=p["bg"], foreground=p["fg"])
    style.map("TCheckbutton", background=[("active", p["bg"])], foreground=[("active", "#ffffff")])
    style.configure("TNotebook", background=p["bg"], bordercolor=p["border"])
    style.configure("TNotebook.Tab", background=p["panel"], foreground=p["dim"], padding=(12, 5))
    style.map("TNotebook.Tab", background=[("selected", p["accent"])],
              foreground=[("selected", "#ffffff")])
    style.configure("Vertical.TScrollbar", background=p["panel"], troughcolor=p["field"],
                    arrowcolor=p["fg"], bordercolor=p["border"])
    # the drop-down list of a combobox is a plain tk Listbox
    for opt, val in (("*TCombobox*Listbox.background", p["field"]),
                     ("*TCombobox*Listbox.foreground", p["fg"]),
                     ("*TCombobox*Listbox.selectBackground", p["accent"]),
                     ("*TCombobox*Listbox.selectForeground", "#ffffff")):
        try:
            root.option_add(opt, val)
        except Exception:  # noqa: BLE001
            pass
    return p


def style_text(widget):
    """Colour a tk Text / ScrolledText to match."""
    p = PALETTE
    widget.configure(bg=p["field"], fg=p["fg"], insertbackground=p["fg"],
                     selectbackground=p["accent"], selectforeground="#ffffff",
                     relief="flat", borderwidth=0, padx=10, pady=8)
