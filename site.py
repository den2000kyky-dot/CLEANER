
import os
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import winreg
import shutil

NAMES = [
    "doomsday", "wurst", "meteor", "impact",
    "aristois", "future", "liquidbounce",
    "rusherhack", "inertia", "bleach",
    "sigma", "novoline", "rise"
]

def scan():
    results.delete(*results.get_children())
    locations = [
        Path(os.environ.get("APPDATA", "")) / ".minecraft",
        Path(os.environ.get("APPDATA", "")),
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path.home() / "Downloads",
        Path.home() / "Desktop"
    ]

    found = set()

    for root in locations:
        if not root.exists():
            continue
        try:
            for current, dirs, files in os.walk(root):
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in ("node_modules", ".git")
                ]

                for name in dirs + files:
                    low = name.lower()
                    if any(word in low for word in NAMES):
                        found.add(str(Path(current) / name))
        except (PermissionError, OSError):
            continue

    for path in sorted(found):
        results.insert("", "end", values=(path,))

    status.config(text=f"Найдено совпадений: {len(found)}")

def remove_selected():
    selected = results.selection()
    if not selected:
        messagebox.showinfo("Информация", "Выбери найденные элементы.")
        return

    if not messagebox.askyesno(
        "Подтверждение",
        "Удалить выбранные файлы и папки?"
    ):
        return

    deleted = 0

    for item in selected:
        path = Path(results.item(item, "values")[0])

        try:
            if not path.exists():
                continue

            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

            results.delete(item)
            deleted += 1
        except (PermissionError, OSError) as e:
            messagebox.showwarning("Ошибка", f"{path}\n{e}")

    status.config(text=f"Удалено объектов: {deleted}")

root = tk.Tk()
root.title("Minecraft Cleanup")
root.geometry("850x520")
root.configure(bg="#111318")

style = ttk.Style()
style.theme_use("clam")
style.configure(
    "Treeview",
    background="#191d25",
    foreground="white",
    fieldbackground="#191d25",
    rowheight=27
)
style.configure(
    "Treeview.Heading",
    background="#292f3b",
    foreground="white"
)

tk.Label(
    root, text="MINECRAFT CLEANUP",
    font=("Segoe UI", 23, "bold"),
    bg="#111318", fg="#ffffff"
).pack(pady=(20, 5))

tk.Label(
    root, text="Поиск остатков удалённых Minecraft-клиентов",
    bg="#111318", fg="#929aaa"
).pack(pady=5)

frame = tk.Frame(root, bg="#111318")
frame.pack(fill="both", expand=True, padx=20, pady=15)

results = ttk.Treeview(
    frame, columns=("path",), show="headings",
    selectmode="extended"
)
results.heading("path", text="Найденный путь")
results.column("path", width=780)
results.pack(fill="both", expand=True)

status = tk.Label(
    root, text="Готов к сканированию",
    bg="#111318", fg="#aeb7c8"
)
status.pack()

buttons = tk.Frame(root, bg="#111318")
buttons.pack(pady=15)

tk.Button(
    buttons, text="СКАНИРОВАТЬ",
    command=scan, bg="#3478f6",
    fg="white", relief="flat",
    padx=25, pady=12
).pack(side="left", padx=8)

tk.Button(
    buttons, text="УДАЛИТЬ ВЫБРАННОЕ",
    command=remove_selected, bg="#c34242",
    fg="white", relief="flat",
    padx=25, pady=12
).pack(side="left", padx=8)

root.mainloop()
