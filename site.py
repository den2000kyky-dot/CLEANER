#!/usr/bin/env python3
"""
site.py

Простой инструмент для очистки компьютера от следов читерских клиентов
для Minecraft (Doomsday и похожие). Делает так:

1. Показывает окно со списком уже ЗАПУЩЕННЫХ процессов Minecraft
   (java.exe/javaw.exe с "minecraft"/"forge"/"fabric" в командной строке
   или заголовке окна). Ты выбираешь нужный из списка.
2. По кнопке «Очистить читы» ищет и удаляет папки/файлы, процессы,
   записи реестра, связанные с известными читерскими клиентами, по
   маскам имён (сам выбранный процесс Minecraft не трогает).
3. Чистит Prefetch (Windows пересоздаёт его сам, это безопасно).

Работает только на Windows. Для чистки реестра и Prefetch скрипт нужно
запускать от имени администратора — иначе соответствующие шаги просто
пропустятся с предупреждением.

Использование:
    python site.py
"""

import os
import re
import sys
import shutil
import ctypes
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# --- Маски имён читерских клиентов, которые ищем -----------------------
# Можно дополнять список при необходимости.
CHEAT_NAME_PATTERNS = [
    r"doomsday",
    r"wurst",
    r"impact",
    r"meteor[-_ ]?client",
    r"future[-_ ]?client",
    r"aristois",
    r"sigma[-_ ]?client",
    r"rise[-_ ]?client",
    r"salhack",
    r"pyro[-_ ]?client",
]
CHEAT_REGEX = re.compile("|".join(CHEAT_NAME_PATTERNS), re.IGNORECASE)

# Папки, в которых ищем файлы/подпапки, совпадающие с масками
SEARCH_ROOTS = [
    os.path.join(os.environ.get("APPDATA", ""), ""),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), ""),
    os.path.join(os.path.expanduser("~"), "Desktop"),
    os.path.join(os.path.expanduser("~"), "Downloads"),
    os.path.join(os.environ.get("APPDATA", ""), ".minecraft"),
]


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def find_running_minecraft():
    """
    Находит уже ЗАПУЩЕННЫЕ процессы Minecraft (java.exe / javaw.exe) и
    возвращает список словарей: {pid, name, title, cmdline}.

    Берём через PowerShell + Win32_Process, чтобы получить и PID, и
    командную строку (по ней видно, что это именно Minecraft — путь к
    .minecraft, к версии, к лаунчеру и т.п.), и заголовок окна.
    """
    ps_script = (
        "$procs = Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match '^java(w)?\\.exe$' }; "
        "$result = foreach ($p in $procs) { "
        "  $title = ''; "
        "  try { $gp = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue; "
        "        if ($gp) { $title = $gp.MainWindowTitle } } catch {}; "
        "  [PSCustomObject]@{ Pid = $p.ProcessId; Name = $p.Name; "
        "                      Title = $title; CommandLine = $p.CommandLine } "
        "}; "
        "$result | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=15,
        )
        raw = out.stdout.strip()
        if not raw:
            return []
        import json
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        procs = []
        for item in data:
            cmdline = item.get("CommandLine") or ""
            title = item.get("Title") or ""
            # Оставляем только то, что реально похоже на Minecraft:
            # в командной строке упоминается minecraft, .minecraft, launcher и т.п.,
            # либо заголовок окна содержит "Minecraft".
            haystack = (cmdline + " " + title).lower()
            if "minecraft" in haystack or "forge" in haystack or "fabric" in haystack:
                procs.append({
                    "pid": item.get("Pid"),
                    "name": item.get("Name"),
                    "title": title.strip(),
                    "cmdline": cmdline.strip(),
                })
        return procs
    except Exception:
        return []


def log(widget, text):
    widget.insert(tk.END, text + "\n")
    widget.see(tk.END)
    widget.update_idletasks()


def kill_matching_processes(widget):
    log(widget, "[*] Поиск и завершение подозрительных процессов...")
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10)
        for line in out.stdout.splitlines():
            if CHEAT_REGEX.search(line):
                parts = line.split()
                if len(parts) >= 2:
                    pid = parts[1]
                    name = parts[0]
                    try:
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
                        log(widget, f"    остановлен процесс: {name} (PID {pid})")
                    except Exception as e:
                        log(widget, f"    не удалось остановить {name}: {e}")
    except Exception as e:
        log(widget, f"    ошибка при получении списка процессов: {e}")


def clean_filesystem(widget):
    log(widget, "[*] Поиск файлов и папок читерских клиентов...")
    removed = 0
    for root in SEARCH_ROOTS:
        if not root or not os.path.isdir(root):
            continue
        try:
            for entry in os.listdir(root):
                if CHEAT_REGEX.search(entry):
                    full = os.path.join(root, entry)
                    try:
                        if os.path.isdir(full):
                            shutil.rmtree(full, ignore_errors=True)
                        else:
                            os.remove(full)
                        log(widget, f"    удалено: {full}")
                        removed += 1
                    except Exception as e:
                        log(widget, f"    не удалось удалить {full}: {e}")
        except Exception as e:
            log(widget, f"    не удалось прочитать {root}: {e}")

    # Отдельно проверяем .minecraft/mods и .minecraft/versions на подозрительные файлы
    mc_dir = os.path.join(os.environ.get("APPDATA", ""), ".minecraft")
    for sub in ("mods", "versions"):
        d = os.path.join(mc_dir, sub)
        if os.path.isdir(d):
            for entry in os.listdir(d):
                if CHEAT_REGEX.search(entry):
                    full = os.path.join(d, entry)
                    try:
                        if os.path.isdir(full):
                            shutil.rmtree(full, ignore_errors=True)
                        else:
                            os.remove(full)
                        log(widget, f"    удалено: {full}")
                        removed += 1
                    except Exception as e:
                        log(widget, f"    не удалось удалить {full}: {e}")

    log(widget, f"[*] Файловая очистка завершена, удалено объектов: {removed}")


def clean_registry(widget):
    if not is_admin():
        log(widget, "[!] Нет прав администратора — пропускаю очистку реестра.")
        log(widget, "    Перезапусти скрипт от имени администратора, чтобы почистить и его.")
        return

    try:
        import winreg
    except ImportError:
        log(widget, "[!] Модуль winreg недоступен (не Windows?) — пропускаю реестр.")
        return

    log(widget, "[*] Поиск записей в реестре...")
    roots_to_scan = [
        (winreg.HKEY_CURRENT_USER, r"Software"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    removed = 0
    for hive, base in roots_to_scan:
        try:
            with winreg.OpenKey(hive, base) as key:
                i = 0
                subkeys_to_delete = []
                while True:
                    try:
                        subname = winreg.EnumKey(key, i)
                        if CHEAT_REGEX.search(subname):
                            subkeys_to_delete.append(subname)
                        i += 1
                    except OSError:
                        break
                for subname in subkeys_to_delete:
                    try:
                        winreg.DeleteKey(key, subname)
                        log(widget, f"    удалён ключ: {base}\\{subname}")
                        removed += 1
                    except Exception as e:
                        log(widget, f"    не удалось удалить ключ {subname}: {e}")

                # Значения (например, в Run) тоже проверяем
                j = 0
                values_to_delete = []
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, j)
                        if CHEAT_REGEX.search(str(name)) or CHEAT_REGEX.search(str(value)):
                            values_to_delete.append(name)
                        j += 1
                    except OSError:
                        break
                for name in values_to_delete:
                    try:
                        winreg.DeleteValue(key, name)
                        log(widget, f"    удалено значение: {base}\\{name}")
                        removed += 1
                    except Exception as e:
                        log(widget, f"    не удалось удалить значение {name}: {e}")
        except FileNotFoundError:
            continue
        except PermissionError:
            log(widget, f"    нет доступа к {base}")
            continue

    log(widget, f"[*] Очистка реестра завершена, удалено записей: {removed}")


def clean_prefetch(widget):
    prefetch_dir = r"C:\Windows\Prefetch"
    if not is_admin():
        log(widget, "[!] Нет прав администратора — пропускаю очистку Prefetch.")
        return
    if not os.path.isdir(prefetch_dir):
        log(widget, "[!] Папка Prefetch не найдена.")
        return

    log(widget, "[*] Очистка Prefetch...")
    removed = 0
    for entry in os.listdir(prefetch_dir):
        full = os.path.join(prefetch_dir, entry)
        try:
            if os.path.isfile(full):
                os.remove(full)
                removed += 1
        except Exception:
            pass
    log(widget, f"[*] Prefetch очищен, удалено файлов: {removed}")
    log(widget, "    (Windows пересоздаст эти файлы сама в процессе обычной работы — это нормально.)")


def run_cleanup(widget, mc_proc):
    log(widget, "=" * 50)
    if mc_proc:
        log(widget, f"Выбран процесс Minecraft: PID {mc_proc['pid']} ({mc_proc['name']})")
        if mc_proc.get("title"):
            log(widget, f"    окно: {mc_proc['title']}")
    else:
        log(widget, "Процесс Minecraft не выбран — очистка всё равно продолжится.")
    if not is_admin():
        log(widget, "[!] Скрипт запущен БЕЗ прав администратора.")
        log(widget, "    Очистка файлов и процессов пройдёт, но реестр и Prefetch")
        log(widget, "    будут пропущены. Для полной очистки перезапусти от имени администратора.")
    log(widget, "")

    kill_matching_processes(widget)
    clean_filesystem(widget)
    clean_registry(widget)
    clean_prefetch(widget)

    log(widget, "")
    log(widget, "Готово. Можешь закрывать окно.")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Очистка читов — выбор Minecraft")
        self.geometry("640x520")
        self.resizable(False, False)

        tk.Label(self, text="Запущенные процессы Minecraft (выбери нужный):",
                 font=("Segoe UI", 11)).pack(pady=(15, 5))

        top_frame = tk.Frame(self)
        top_frame.pack(pady=5)

        self.combo = ttk.Combobox(top_frame, width=68, state="readonly")
        self.combo.pack(side=tk.LEFT, padx=(0, 5))

        tk.Button(top_frame, text="Обновить", command=self.refresh_list).pack(side=tk.LEFT)

        self.mc_list = []
        self.refresh_list()

        self.clean_btn = tk.Button(self, text="Очистить читы", bg="#c0392b", fg="white",
                                    font=("Segoe UI", 11, "bold"), command=self.on_clean)
        self.clean_btn.pack(pady=10)

        self.log_widget = scrolledtext.ScrolledText(self, width=78, height=20, font=("Consolas", 9))
        self.log_widget.pack(padx=10, pady=10)

        if not is_admin():
            log(self.log_widget, "[i] Совет: запусти скрипт от имени администратора,")
            log(self.log_widget, "    чтобы очистка реестра и Prefetch тоже сработала.")

    def refresh_list(self):
        self.mc_list = find_running_minecraft()
        if self.mc_list:
            values = []
            for p in self.mc_list:
                label = f"PID {p['pid']} — {p['name']}"
                if p.get("title"):
                    label += f" — {p['title']}"
                values.append(label)
            self.combo["values"] = values
            self.combo.current(0)
        else:
            self.combo["values"] = ["Minecraft не запущен — запусти игру и нажми «Обновить»"]
            self.combo.current(0)

    def on_clean(self):
        if not self.mc_list:
            messagebox.showwarning(
                "Minecraft не найден",
                "Запущенный Minecraft не обнаружен. Запусти игру и нажми «Обновить»,\n"
                "либо продолжи — очистка всё равно сработает."
            )
            mc_proc = None
        else:
            idx = self.combo.current()
            mc_proc = self.mc_list[idx]

        self.clean_btn.config(state="disabled")
        run_cleanup(self.log_widget, mc_proc)
        self.clean_btn.config(state="normal")


if __name__ == "__main__":
    if os.name != "nt":
        print("Этот скрипт предназначен только для Windows.")
        sys.exit(1)
    app = App()
    app.mainloop()
