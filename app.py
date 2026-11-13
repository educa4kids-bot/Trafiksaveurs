# -*- coding: utf-8 -*-
"""Trafik Saveurs — تطبيق سطح المكتب لويندوز (Python + pywebview).
يشغّل النظام عبر خادم محلي بمنفذ ثابت (لتبقى البيانات محفوظة) داخل نافذة WebView2.
إن لم يتوفر WebView2 (ويندوز قديم) يُفتح النظام تلقائياً في المتصفح الافتراضي.
"""
import os, sys, json, base64, threading, datetime, webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

APP = 'Trafik Saveurs'
PORT = 8765
HOST = '127.0.0.1'
DATA_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'TrafikSaveurs')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
WIN = None


def res(*p):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *p)


def msgbox(text, icon=0x40):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, APP, icon)
    except Exception:
        print(text)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=res('web'), **k)

    def log_message(self, *a):  # لا مخرجات (نسخة windowed بلا console)
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


class Api:
    """دوال تُستدعى من الواجهة (JavaScript)."""

    def save_file(self, name, b64):
        import webview
        try:
            mode = webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG
            path = WIN.create_file_dialog(mode, save_filename=name)
            if not path:
                return False
            if isinstance(path, (list, tuple)):
                path = path[0]
            with open(path, 'wb') as f:
                f.write(base64.b64decode(b64))
            return True
        except Exception as e:
            return str(e)

    def autosave(self, js):
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            tmp = os.path.join(DATA_DIR, 'data.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(js)
            os.replace(tmp, os.path.join(DATA_DIR, 'data.json'))
            day = os.path.join(BACKUP_DIR, 'backup_%s.json' % datetime.date.today().isoformat())
            with open(day, 'w', encoding='utf-8') as f:
                f.write(js)
            for old in sorted(os.listdir(BACKUP_DIR))[:-30]:  # آخر 30 يوماً
                os.remove(os.path.join(BACKUP_DIR, old))
            return True
        except Exception as e:
            return str(e)

    def load_data(self):
        try:
            with open(os.path.join(DATA_DIR, 'data.json'), encoding='utf-8') as f:
                return f.read()
        except Exception:
            return ''

    def open_data_folder(self):
        try:
            os.startfile(DATA_DIR)
        except Exception:
            pass


def run_browser_fallback(server):
    """بديل للويندوز القديم: فتح النظام في المتصفح مع نافذة صغيرة لإيقاف الخادم."""
    webbrowser.open('http://%s:%d/index.html' % (HOST, PORT))
    try:
        import tkinter as tk
        r = tk.Tk()
        r.title(APP)
        r.geometry('360x120')
        tk.Label(r, text='النظام يعمل في المتصفح\nأغلق هذه النافذة لإيقاف البرنامج', font=('Segoe UI', 11)).pack(expand=True)
        r.mainloop()
    except Exception:
        threading.Event().wait()


def main():
    global WIN
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        msgbox('البرنامج يعمل بالفعل (أو المنفذ %d مستخدم).\nLe programme est déjà ouvert.' % PORT, 0x30)
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        import webview
        WIN = webview.create_window(APP, 'http://%s:%d/index.html?desktop=1' % (HOST, PORT),
                                    width=1280, height=800, min_size=(900, 600), js_api=Api())
        webview.start(gui='edgechromium', private_mode=False, storage_path=os.path.join(DATA_DIR, 'webview'))
    except Exception:
        run_browser_fallback(server)
    server.shutdown()


if __name__ == '__main__':
    main()
