#!/usr/bin/env python3
"""
clean_cheats.py

Простой инструмент для очистки компьютера от следов читерских клиентов
для Minecraft (Doomsday и похожие). Делает три вещи:

1. Показывает окно с выбором установленной Java (просто для подтверждения
   "начать очистку" — реальный запуск игры этот скрипт не трогает).
2. Ищет и удаляет папки/файлы, процессы, записи реестра, связанные с
   известными читерскими клиентами, по маскам имён.
3. Чистит Prefetch (Windows пересоздаёт его сам, это безопасно).

Работает только на Windows. Для чистки реестра и Prefetch скрипт нужно
запускать от имени администратора — иначе соответствующие шаги просто
пропустятся с предупреждением.

Использование:
    python clean_cheats.py
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


def find_java_installations():
    """Находит установленные Java: по PATH, стандартным папкам и реестру."""
    found = set()

    # 1. JAVA_HOME / PATH
    java_home = os.environ.get("JAVA_HOME")
    if java_home and os.path.isdir(java_home):
        found.add(java_home)

    # where java (через PATH)
    try:
        out = subprocess.run(["where", "java"], capture_output=True, text=True, timeout=5)
        for line in out.stdout.splitlines():
            line = line.strip()
            if line.lower().endswith("java.exe"):
                found.add(os.path.dirname(os.path.dirname(line)))
    except Exception:
        pass

    # 2. Стандартные папки установки
    standard_dirs = [
        r"C:\Program Files\Java",
        r"C:\Program Files (x86)\Java",
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Microsoft\jdk-*",
    ]
    for base in standard_dirs:
        base_dir = base.replace("*", "")
        parent = os.path.dirname(base_dir) if "*" in base else base
        if os.path.isdir(parent):
            try:
                for name in os.listdir(parent):
                    full = os.path.join(parent, name)
                    if os.path.isdir(full) and "jdk" in name.lower() or "jre" in name.lower() or "java" in name.lower():
                        found.add(full)
            except Exception:
                pass

    # 3. Реестр (JavaSoft)
    try:
        import winreg
        reg_paths = [
            r"SOFTWARE\JavaSoft\Java Runtime Environment",
            r"SOFTWARE\JavaSoft\JDK",
            r"SOFTWARE\Eclipse Adoptium\JRE",
            r"SOFTWARE\Eclipse Adoptium\JDK",
        ]
        for rp in reg_paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rp) as key:
                    i = 0
                    while True:
                        try:
                            version = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, version) as vkey:
                                try:
                                    java_home_val, _ = winreg.QueryValueEx(vkey, "JavaHome")
                                    found.add(java_home_val)
                                except FileNotFoundError:
                                    pass
                            i += 1
                        except OSError:
                            break
            except FileNotFoundError:
                pass
    except ImportError:
        pass

    results = []
    for path in found:
        exe = os.path.join(path, "bin", "java.exe")
        if os.path.isfile(exe):
            results.append((path, exe))
    return sorted(set(results))


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


def run_cleanup(widget, java_path):
    log(widget, "=" * 50)
    log(widget, f"Выбранная Java: {java_path}")
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
        self.title("Очистка читов — выбор Java")
        self.geometry("640x480")
        self.resizable(False, False)

        tk.Label(self, text="Выбери установленную Java для запуска Minecraft:",
                 font=("Segoe UI", 11)).pack(pady=(15, 5))

        self.java_list = find_java_installations()
        self.combo = ttk.Combobox(self, width=80, state="readonly")
        if self.java_list:
            self.combo["values"] = [f"{path}" for path, _ in self.java_list]
            self.combo.current(0)
        else:
            self.combo["values"] = ["Java не найдена автоматически"]
            self.combo.current(0)
        self.combo.pack(pady=5)

        self.clean_btn = tk.Button(self, text="Очистить читы", bg="#c0392b", fg="white",
                                    font=("Segoe UI", 11, "bold"), command=self.on_clean)
        self.clean_btn.pack(pady=10)

        self.log_widget = scrolledtext.ScrolledText(self, width=78, height=20, font=("Consolas", 9))
        self.log_widget.pack(padx=10, pady=10)

        if not is_admin():
            log(self.log_widget, "[i] Совет: запусти скрипт от имени администратора,")
            log(self.log_widget, "    чтобы очистка реестра и Prefetch тоже сработала.")

    def on_clean(self):
        if not self.java_list:
            messagebox.showwarning("Java не найдена", "Автоматически Java не найдена, но очистка всё равно продолжится.")
            java_path = "не определено"
        else:
            idx = self.combo.current()
            java_path = self.java_list[idx][0]

        self.clean_btn.config(state="disabled")
        run_cleanup(self.log_widget, java_path)
        self.clean_btn.config(state="normal")


if __name__ == "__main__":
    if os.name != "nt":
        print("Этот скрипт предназначен только для Windows.")
        sys.exit(1)
    app = App()
    app.mainloop()
