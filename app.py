# -*- coding: utf-8 -*-
"""Trafik Saveurs — تطبيق سطح المكتب لويندوز (Python + pywebview).
يشغّل النظام عبر خادم محلي بمنفذ ثابت (لتبقى البيانات محفوظة) داخل نافذة WebView2.
إن لم يتوفر WebView2 (ويندوز قديم) يُفتح النظام تلقائياً في المتصفح الافتراضي.
"""
import os, sys, json, base64, threading, datetime, webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

try:  # مراقبة صلاحية المنتجات وإصدار إشعارات (متاحة أيضاً في نسخة المتصفح)
    import expiration
except Exception:
    expiration = None

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

    def do_GET(self):
        p = self.path.split('?')[0]
        if p.lower() == '/expiration.js':
            return self._send(EXPIRATION_JS.encode('utf-8'), 'text/javascript; charset=utf-8')
        if p.lower().endswith('.html'):
            try:
                f = self.translate_path(p)
                with open(f, 'rb') as fh:
                    data = fh.read()
                inject = b'<script src="/expiration.js"></script>'
                if b'/expiration.js' not in data:
                    low = data.lower()
                    for tag in (b'</body>', b'</html>'):
                        i = low.rfind(tag)
                        if i != -1:
                            data = data[:i] + inject + data[i:]
                            break
                    else:
                        data = data + inject
                return self._send(data, 'text/html; charset=utf-8')
            except Exception:
                pass
        return super().do_GET()

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


EXPIRATION_JS = r"""
/* Trafik Saveurs — تنبيهات صلاحية المنتجات داخل الصفحة (نسخة سطح المكتب) */
(function () {
  if (!window.pywebview) return;
  function fmt(iso) { var p = iso.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }
  function show(res) {
    try {
      if (!res || !res.ok) return;
      var n = (res.expired || []).length + (res.soon || []).length;
      if (!n) return;
      var html = '<div id="ts-exp-banner" dir="rtl" style="position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:2147483647;' +
        'background:#fff;border:2px solid #dc2626;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.25);' +
        'padding:14px 18px;max-width:520px;font-family:Cairo,Segoe UI,Tahoma,sans-serif;">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">' +
        '<b style="color:#dc2626;font-size:15px;">⚠️ تنبيه صلاحية المنتجات</b>' +
        '<button onclick="document.getElementById(\'ts-exp-banner\').remove()" ' +
        'style="background:none;border:none;font-size:18px;cursor:pointer;color:#666;">✕</button></div>';
      if (res.expired && res.expired.length) {
        html += '<div style="margin-top:8px;color:#dc2626;font-weight:600;">⛔ منتهية الصلاحية (' + res.expired.length + '):</div><ul style="margin:4px 0 0;padding-inline-start:20px;">';
        res.expired.slice(0, 6).forEach(function (p) { html += '<li>' + p.name + ' — ' + fmt(p.date) + '</li>'; });
        html += '</ul>';
      }
      if (res.soon && res.soon.length) {
        html += '<div style="margin-top:8px;color:#d97706;font-weight:600;">⏳ قرب الانتهاء (' + res.soon.length + '):</div><ul style="margin:4px 0 0;padding-inline-start:20px;">';
        res.soon.slice(0, 6).forEach(function (p) { html += '<li>' + p.name + ' — ' + fmt(p.date) + '</li>'; });
        html += '</ul>';
      }
      html += '</div>';
      var add = function () {
        if (document.getElementById('ts-exp-banner')) return;
        document.body.insertAdjacentHTML('beforeend', html);
        setTimeout(function () {
          var b = document.getElementById('ts-exp-banner');
          if (b) b.style.opacity = '0.95';
        }, 15000);
      };
      if (document.body) add(); else window.addEventListener('DOMContentLoaded', add);
    } catch (e) { /* لا يكسر الصفحة */ }
  }
  function run() {
    try {
      if (window.pywebview && pywebview.api && pywebview.api.check_expirations) {
        Promise.resolve(pywebview.api.check_expirations()).then(show).catch(function () {});
      }
    } catch (e) {}
  }
  window.addEventListener('pywebviewready', run);
  setTimeout(run, 2500);
  setInterval(run, 30 * 60 * 1000); // إعادة الفحص كل 30 دقيقة
})();
"""


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

    def check_expirations(self):
        """تُستدعى من الواجهة بعد تحميل البيانات: تفحص الصلاحيات وترجع الملخص."""
        if expiration is None:
            return {'ok': False}
        try:
            expired, soon = expiration.check_once(DATA_DIR, show_dialog=False)
            return {
                'ok': True,
                'expired': [{'name': n, 'date': d.isoformat()} for n, d in expired],
                'soon': [{'name': n, 'date': d.isoformat()} for n, d in soon],
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}


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
    # مراقبة صلاحية المنتجات: إشعار عند الإقلاع ثم كل 6 ساعات (نافذة + Toast)
    if expiration is not None:
        expiration.start_monitor(DATA_DIR)
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
