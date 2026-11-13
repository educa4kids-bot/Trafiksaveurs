# -*- coding: utf-8 -*-
"""Trafik Saveurs — مراقبة تواريخ صلاحية المنتجات وإصدار إشعارات ويندوز.

يقرأ البيانات المحفوظة (%APPDATA%\\TrafikSaveurs\\data.json أو ملفات webview
المحلية localStorage) ويبحث عن أي حقول تاريخ صلاحية (DLC / péremption / expiry /
date limite…)، ثم يعرض:
  • بالون إشعار في علبة النظام (Windows Toast via PowerShell) عند الاقتراب/الانتهاء.
  • نافذة تنبيه تفصيلية داخل البرنامج نفسه عند الإقلاع.
لا يتكرر إشعار نفس المنتج في نفس اليوم (سجل في notified.json).
"""
import os, re, json, datetime, threading, subprocess

APP = 'Trafik Saveurs'
DAYS_BEFORE = 7          # عدد الأيام قبل انتهاء الصلاحية لبدء التنبيه
INTERVAL_SEC = 6 * 3600  # إعادة الفحص كل 6 ساعات أثناء عمل البرنامج

# كلمات مفتاحية تدل على أن الحقل تاريخ صلاحية (عربية/فرنسية/إنجليزية)
KEY_RE = re.compile(
    r'(dlc|p[ée]rempt|peremption|expir|validit|shelf|تاريخ\s*الصلاحية|صلاحية|انتهاء|entente)',
    re.I)
DATE_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')

NAME_KEYS = ('name', 'nom', 'designation', 'désignation', 'produit', 'article',
             'libelle', 'libellé', 'product', 'item', 'اسم', 'المنتج', 'اسم_المنتج',
             'التسمية', 'المادة')


def _parse_date(v):
    if not isinstance(v, str):
        return None
    m = DATE_RE.match(v.strip())
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r'^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$', v.strip())  # dd/mm/yyyy
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _iter_records(obj):
    """مرور عشوائي على JSON لإيجاد الكائنات التي تحتوي تاريخ صلاحية."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_records(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_records(v)


def scan_products(data_dir):
    """يرجع قائمة (اسم المنتج, تاريخ الصلاحية) من كل مصادر البيانات."""
    results = []
    raws = []
    dj = os.path.join(data_dir, 'data.json')
    if os.path.isfile(dj):
        try:
            with open(dj, encoding='utf-8') as f:
                raws.append(f.read())
        except Exception:
            pass
    # localStorage الخاص بـ WebView2/Chromium (ملفات LevelDB نصية جزئياً)
    leveldb_dir = None
    for root, dirs, files in os.walk(os.path.join(data_dir, 'webview')):
        if os.path.basename(root) == 'Local Storage' and 'leveldb' in dirs:
            leveldb_dir = os.path.join(root, 'leveldb')
    texts = list(raws)
    if leveldb_dir:
        for fn in os.listdir(leveldb_dir):
            if fn.endswith(('.log', '.ldb')):
                try:
                    with open(os.path.join(leveldb_dir, fn), 'rb') as f:
                        texts.append(f.read().decode('utf-8', 'ignore'))
                except Exception:
                    pass
    for txt in texts:
        objs = []
        try:
            objs.append(json.loads(txt))
        except Exception:
            pass
        # استخلاص كائنات JSON مضمّنة داخل نصوص localStorage
        for m in re.finditer(r'[\{\[]"[^\x00-\x1f]{20,}?[\}\]]', txt):
            try:
                objs.append(json.loads(m.group(0)))
            except Exception:
                pass
        for o in objs:
            for rec in _iter_records(o):
                exp = None
                for k, v in rec.items():
                    if KEY_RE.search(str(k)):
                        d = _parse_date(v)
                        if d:
                            exp = d
                            break
                if not exp:
                    continue
                name = None
                for nk in NAME_KEYS:
                    for k in rec.keys():
                        if str(k).strip().lower() == nk and isinstance(rec[k], str) and rec[k].strip():
                            name = rec[k].strip()
                            break
                    if name:
                        break
                if not name:
                    name = 'منتج'
                results.append((name, exp))
    # إزالة التكرار (نفس الاسم والتاريخ)
    uniq = {}
    for n, d in results:
        uniq[(n, d.isoformat())] = d
    return [(n, d) for (n, _), d in uniq.items()]


def _toast(title, message):
    """إشعار ويندوز عبر PowerShell (Toast) مع رجوع إلى msgbox."""
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
        " ContentType=WindowsRuntime] | Out-Null;"
        "$u=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(2);"
        "$t=$u.GetElementsByTagName('text');"
        "$t.Item(0).AppendChild($u.CreateTextNode('%s')) | Out-Null;"
        "$t.Item(1).AppendChild($u.CreateTextNode('%s')) | Out-Null;"
        "$a=[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%s');"
        "$a.Show([Windows.UI.Notifications.ToastNotification]::new($u));"
    ) % (title.replace("'", "''"), message.replace("'", "''"), APP)
    try:
        si = None
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                       timeout=15, startupinfo=si,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _msgbox(text, icon=0x30):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, APP, icon)
    except Exception:
        print(text)


def check_once(data_dir, show_dialog=True):
    """فحص واحد: يرجع (expired, soon) ويعرض الإشعارات اللازمة (مرة/يوم لكل منتج)."""
    today = datetime.date.today()
    try:
        products = scan_products(data_dir)
    except Exception:
        return [], []
    expired = [(n, d) for n, d in products if d < today]
    soon = [(n, d) for n, d in products if 0 <= (d - today).days <= DAYS_BEFORE]
    if not expired and not soon:
        return expired, soon

    nfile = os.path.join(data_dir, 'notified.json')
    notified = {}
    try:
        with open(nfile, encoding='utf-8') as f:
            notified = json.load(f)
    except Exception:
        pass
    stamp = today.isoformat()

    def fresh(n, d):
        return notified.get(n + '|' + d.isoformat(), '') != stamp

    new_exp = [(n, d) for n, d in expired if fresh(n, d)]
    new_soon = [(n, d) for n, d in soon if fresh(n, d)]
    if not new_exp and not new_soon:
        return expired, soon

    lines = []
    if new_exp:
        lines.append('⛔ منتجات منتهية الصلاحية (%d):' % len(new_exp))
        lines += ['   • %s — انتهت في %s' % (n, d.strftime('%d/%m/%Y')) for n, d in new_exp[:10]]
        if len(new_exp) > 10:
            lines.append('   … و%d أخرى' % (len(new_exp) - 10))
    if new_soon:
        lines.append('⚠️ منتجات قرب انتهاء صلاحيتها (%d):' % len(new_soon))
        lines += ['   • %s — تنتهي في %s' % (n, d.strftime('%d/%m/%Y')) for n, d in new_soon[:10]]
        if len(new_soon) > 10:
            lines.append('   … و%d أخرى' % (len(new_soon) - 10))
    body = '\n'.join(lines)

    short = ''
    if new_exp:
        short += 'منتهية: %s' % ', '.join(n for n, _ in new_exp[:3])
    if new_soon:
        short += (' | ' if short else '') + 'قريبة الانتهاء: %s' % ', '.join(n for n, _ in new_soon[:3])
    _toast(APP + ' — تنبيه الصلاحية', short[:250])
    if show_dialog:
        _msgbox(body)

    for n, d in new_exp + new_soon:
        notified[n + '|' + d.isoformat()] = stamp
    # تنظيف سجل قديم
    notified = {k: v for k, v in notified.items()
                if (today - datetime.date.fromisoformat(v)).days <= 3} if notified else notified
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(nfile, 'w', encoding='utf-8') as f:
            json.dump(notified, f, ensure_ascii=False)
    except Exception:
        pass
    return expired, soon


def start_monitor(data_dir):
    """خيط خلفي: فحص عند الإقلاع ثم كل INTERVAL_SEC."""
    def loop():
        check_once(data_dir, show_dialog=True)
        while True:
            threading.Event().wait(INTERVAL_SEC)
            check_once(data_dir, show_dialog=False)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t
