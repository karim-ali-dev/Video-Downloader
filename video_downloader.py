# -*- coding: utf-8 -*-
import math
import json
import os
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import yt_dlp

APP_NAME = 'Video Downloader'
VERSION = '4.0.0'
DEV_WHATSAPP = '01099724825'
MAX_PARALLEL = 3
INFO_POOL = 6

BASE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DEFAULT_FOLDER = str(Path.home() / 'Downloads')
HISTORY_FILE = BASE_DIR / 'download_history.json'

C_BG = '#121212'
C_CARD = '#1c1c1c'
C_FIELD = '#2a2a2a'
C_FG = '#ffffff'
C_MUT = '#d9d9d9'
C_ACC = '#d62828'
C_ACC_H = '#ef4444'
C_ACC_D = '#a61b1b'
C_TEAL = '#ffffff'
C_BAD = '#ef3038'
C_GOOD = '#ffffff'
C_BORDER = '#3f3f3f'
C_DIS = '#4b4b4b'

FMT_LABELS = {
    'MP4 فيديو': 'mp4',
    'MKV فيديو': 'mkv',
    'MP3 صوت': 'mp3',
}

BITRATE_FMTS = {'mp3'}
AUDIO_CODEC = {'mp3': 'mp3'}

HEIGHTS = {
    '4320p': '4320',
    '2160p': '2160',
    '1440p': '1440',
    '1080p': '1080',
    '720p': '720',
    '480p': '480',
    '360p': '360',
    '240p': '240',
    '144p': '144',
}

QUALITY_LABELS = ['الأفضل', '4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p']
AUDIO_BITRATES = {
    '320 kbps (الأفضل)': '320',
    '256 kbps': '256',
    '192 kbps': '192',
    '128 kbps': '128',
    '96 kbps': '96',
}
PLACEHOLDER = 'الصق الروابط هنا... رابط في كل سطر'


def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(c):
    return '#%02x%02x%02x' % c


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def get_ffmpeg_dir():
    candidates = []
    if getattr(sys, 'frozen', False):
        candidates.append(Path(getattr(sys, '_MEIPASS', BASE_DIR)) / 'tools' / 'ffmpeg')
    candidates.append(BASE_DIR / 'tools' / 'ffmpeg')
    for cand in candidates:
        if (cand / 'ffmpeg.exe').is_file() and (cand / 'ffprobe.exe').is_file():
            return str(cand)
    return None


def build_format_string(fmt, quality):
    if fmt == 'mp3':
        return 'bestaudio/best'
    if quality == 'الأفضل':
        if fmt == 'mp4':
            return ('best[ext=mp4]/bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]'
                    '/bestvideo+bestaudio/best')
        return 'best/bestvideo+bestaudio/best'
    h = HEIGHTS.get(quality, '1080')
    if fmt == 'mp4':
        return (f'best[ext=mp4][height<={h}]'
                f'/bestvideo[ext=mp4][vcodec^=avc1][height<={h}]+bestaudio[ext=m4a]'
                f'/bestvideo[height<={h}]+bestaudio[height<={h}]/best')
    return f'best[height<={h}]/bestvideo[height<={h}]+bestaudio[height<={h}]/best'


def fmt_duration(sec):
    if not sec:
        return ''
    sec = int(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m}:{s:02d}'


def human_size(n):
    if not n:
        return ''
    for unit in ('بايت', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            if unit != 'بايت':
                return f'{n:.1f} {unit}'
            return f'{int(n)} بايت'
        n /= 1024
    return ''


def short_title(s, limit=70):
    s = (s or '').strip()
    return s if len(s) <= limit else s[:limit] + '…'


class _PauseAbort(Exception):
    pass


class _StopAbort(Exception):
    pass


class Anim:
    def __init__(self, root):
        self.root = root
        self.jobs = {}

    def color(self, widget, target, duration=200, attr='bg'):
        key = (id(widget), attr)
        st = self.jobs.pop(key, None)
        if st and st.get('job'):
            self.root.after_cancel(st['job'])
        try:
            current = widget.cget(attr)
        except tk.TclError:
            current = None
        if current == target:
            return None
        if not current or current.startswith('system'):
            current = C_CARD
        try:
            start = hex_to_rgb(current)
            end = hex_to_rgb(target)
        except ValueError:
            return None
        state = {'start': start, 'end': end, 't': 0.0, 'dur': max(1, duration)}

        def step():
            state['t'] = min(1.0, state['t'] + 16 / state['dur'])
            eased = 1 - (1 - state['t']) ** 3
            col = rgb_to_hex(lerp(state['start'], state['end'], eased))
            try:
                widget.configure(**{attr: col})
            except tk.TclError:
                return None
            if state['t'] < 1.0:
                state['job'] = self.root.after(16, step)
                return None
            self.jobs.pop(key, None)
            return None

        state['job'] = self.root.after(16, step)
        self.jobs[key] = state
        return None

    def stop(self, widget, attr='bg'):
        key = (id(widget), attr)
        st = self.jobs.pop(key, None)
        if st and st.get('job'):
            self.root.after_cancel(st['job'])
            return None
        return None


class DownloadItem:
    def __init__(self, app, url):
        self.app = app
        self.url = url
        self.title = 'جارٍ جلب المعلومات...'
        self.uploader = ''
        self.duration = None
        self.size = 0
        self.ready = False
        self.info_error = False
        self.paused = False
        self.stopped = False
        self.done = False
        self.failed = False
        self.started = False
        self._progress_target = 0.0
        self.pause_evt = threading.Event()
        self.stop_evt = threading.Event()
        self._thumb_photo = None
        self.thread = None
        self._build()

    def _build(self):
        frame = tk.Frame(self.app.list_container, bg=C_CARD, highlightbackground=C_BORDER, highlightthickness=1)
        frame.pack(fill='x', padx=0, pady=(0, 8))
        self.frame = frame

        top = tk.Frame(frame, bg=C_CARD)
        top.pack(fill='x', padx=10, pady=(8, 2))
        self.thumb_lbl = tk.Label(top, text='🎬', bg='#161616', fg=C_MUT, font=('Segoe UI', 20),
                                  width=13, height=4)
        self.thumb_lbl.pack(side='right', padx=(0, 10))
        txt = tk.Frame(top, bg=C_CARD)
        txt.pack(side='right', fill='x', expand=True)
        self.title_lbl = tk.Label(txt, text=self.title, bg=C_CARD, fg=C_FG, font=('Segoe UI', 10, 'bold'),
                                  justify='right', anchor='e', wraplength=360)
        self.title_lbl.pack(fill='x')
        self.meta_lbl = tk.Label(txt, text='', bg=C_CARD, fg=C_MUT, font=('Segoe UI', 8), justify='right', anchor='e')
        self.meta_lbl.pack(fill='x')
        self.size_lbl = tk.Label(txt, text='الحجم: جارٍ الحساب...', bg=C_CARD, fg=C_TEAL,
                                 font=('Segoe UI', 8, 'bold'), justify='right', anchor='e')
        self.size_lbl.pack(fill='x')

        mid = tk.Frame(frame, bg=C_CARD)
        mid.pack(fill='x', padx=10, pady=(2, 2))
        self.bar = ttk.Progressbar(mid, style='Horizontal.TProgressbar', mode='determinate')
        self.bar.pack(fill='x', side='right', expand=True, padx=(10, 0))
        self.status_lbl = tk.Label(mid, text='بانتظار البداية', bg=C_CARD, fg=C_MUT, font=('Segoe UI', 8))
        self.status_lbl.pack(side='right')

        btns = tk.Frame(frame, bg=C_CARD)
        btns.pack(fill='x', padx=10, pady=(2, 8))
        self.pause_btn = tk.Button(btns, text='⏸️ إيقاف مؤقت', command=self.toggle_pause, bg=C_FIELD, fg=C_FG,
                                   activebackground=C_ACC, activeforeground='white', relief='flat',
                                   font=('Segoe UI', 8, 'bold'), cursor='hand2', padx=10, pady=4)
        self.pause_btn.pack(side='right')
        self.stop_btn = tk.Button(btns, text='🛑 إيقاف', command=self.stop, bg=C_FIELD, fg=C_FG,
                                  activebackground=C_ACC, activeforeground='white', relief='flat',
                                  font=('Segoe UI', 8, 'bold'), cursor='hand2', padx=10, pady=4)
        self.stop_btn.pack(side='right', padx=(6, 0))
        self.remove_btn = tk.Button(btns, text='✖ حذف', command=self.remove, bg=C_FIELD, fg=C_MUT,
                                    activebackground=C_ACC, activeforeground='white', relief='flat',
                                    font=('Segoe UI', 8), cursor='hand2', padx=10, pady=4)
        self.remove_btn.pack(side='right', padx=(6, 0))
        self.app.animate_btn(self.pause_btn, C_FIELD, C_ACC)
        self.app.animate_btn(self.stop_btn, C_FIELD, C_ACC)
        self.app.animate_btn(self.remove_btn, C_FIELD, C_ACC)
        self.app.tooltip(self.pause_btn, 'إيقاف / استئناف هذا الفيديو')
        self.app.tooltip(self.stop_btn, 'إيقاف هذا الفيديو نهائيًا')
        self.app.tooltip(self.remove_btn, 'حذف العنصر من القائمة')

    def remove(self):
        self.stop()
        self.app.post(self._destroy)

    def _destroy(self):
        self.app.remove_item(self, destroy=True)
        self.app.refresh_scroll()
        self.app.update_total()
        self.app.maybe_finish()

    def toggle_pause(self):
        if self.paused:
            self.pause_evt.clear()
            self.paused = False
        else:
            self.pause_evt.set()
            self.paused = True
        self.app.post(self._set_pause_ui)

    def _set_pause_ui(self):
        if self.paused:
            self.pause_btn.configure(text='▶️ استئناف')
            self.set_status('متوقف مؤقتًا', C_MUT)
        else:
            self.pause_btn.configure(text='⏸️ إيقاف مؤقت')
            if self.started and not self.done and not self.failed and not self.stopped:
                self.set_status('جارٍ التحميل...', C_GOOD)

    def stop(self):
        self.stop_evt.set()
        self.stopped = True
        self.app.post(self._set_stop_ui)

    def _set_stop_ui(self):
        self.stop_btn.configure(state='disabled', text='متوقف')
        self.pause_btn.configure(state='disabled')
        self.set_status('تم الإيقاف', C_BAD)
        self.app.update_total()
        self.app.maybe_finish()

    def start_info(self):
        threading.Thread(target=self._fetch_info, daemon=True).start()

    def _fetch_info(self):
        with self.app.info_sem:
            try:
                with yt_dlp.YoutubeDL(self.app.info_opts()) as ydl:
                    info = ydl.extract_info(self.url, download=False)
            except Exception as e:
                self.app.post(self.set_error, short_title(str(e), 130))
                return
        if isinstance(info, dict) and info.get('entries'):
            self.app.post(self.app.expand_playlist, info['entries'], self)
            return
        self.app.post(self.apply_info,
                      info.get('title') or 'بدون عنوان',
                      info.get('duration'),
                      info.get('uploader') or '',
                      self.app.compute_size(info))
        thumb = info.get('thumbnail')
        if thumb:
            threading.Thread(target=self._load_thumb, args=(thumb,), daemon=True).start()

    def apply_info(self, title, duration, uploader, size):
        self.title = title
        self.duration = duration
        self.uploader = uploader
        self.size = size
        self.ready = True
        self.title_lbl.configure(text=short_title(title))
        meta = []
        if duration:
            meta.append('⏱ ' + fmt_duration(duration))
        if uploader:
            meta.append('👤 ' + short_title(uploader, 30))
        self.meta_lbl.configure(text='   •   '.join(meta))
        self.size_lbl.configure(text='الحجم: ' + (human_size(size) if size else 'غير محدد'))
        self.set_status('جاهز للتحميل', C_GOOD)
        self.app.update_total()
        self.app.refresh_scroll()
        if self.app.downloading and not self.started:
            self.start_download()

    def set_error(self, msg):
        self.info_error = True
        self.ready = True
        self.title_lbl.configure(text='تعذر قراءة الرابط')
        self.size_lbl.configure(text='')
        self.meta_lbl.configure(text='')
        self.set_status('خطأ: ' + msg, C_BAD)
        self.app.update_total()

    def _load_thumb(self, url):
        try:
            import urllib.request
            from io import BytesIO
            from PIL import Image
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=15).read()
            img = Image.open(BytesIO(data)).convert('RGB')
            img.thumbnail((150, 90))
            self.app.post(self._set_thumb, img)
        except Exception:
            pass

    def _set_thumb(self, img):
        try:
            from PIL import ImageTk
            self._thumb_photo = ImageTk.PhotoImage(img)
            self.thumb_lbl.configure(image=self._thumb_photo, text='', width=150, height=90)
            self.thumb_lbl.image = self._thumb_photo
        except Exception:
            pass

    def set_status(self, text, color=C_MUT):
        try:
            self.status_lbl.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def set_progress(self, pct):
        self._progress_target = pct
        self.app.post(self._smooth_progress)

    def _smooth_progress(self):
        try:
            cur = self.bar['value']
        except tk.TclError:
            return
        t = self._progress_target
        if abs(t - cur) > 0.5:
            self.bar.configure(value=cur + (t - cur) * 0.25)
            if not self.done:
                self.app.root.after(40, self._smooth_progress)
        else:
            self.bar.configure(value=t)

    def start_download(self):
        if self.started:
            return
        self.started = True
        self.thread = threading.Thread(target=self._download_worker, daemon=True)
        self.thread.start()

    def _download_worker(self):
        with self.app.parallel_sem:
            opts = self.app.download_opts()
            opts['progress_hooks'] = [self.hook]
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    while True:
                        if self.stop_evt.is_set():
                            break
                        if self.pause_evt.is_set():
                            self.app.post(self.set_status, 'متوقف مؤقتًا...', C_MUT)
                            while self.pause_evt.is_set():
                                if self.stop_evt.is_set():
                                    return
                                time.sleep(0.2)
                            if self.stop_evt.is_set():
                                return
                            continue
                        self.app.post(self.set_status, 'جارٍ التحميل...', C_GOOD)
                        try:
                            ydl.download([self.url])
                        except _PauseAbort:
                            continue
                        except _StopAbort:
                            break
                        except Exception as e:
                            if self.stop_evt.is_set():
                                break
                            if self.pause_evt.is_set():
                                continue
                            self.failed = True
                            self.started = False
                            self.app.post(self.set_status, 'فشل: ' + short_title(str(e), 100), C_BAD)
                            self.app.post(self.app.update_total)
                            self.app.post(self.app.maybe_finish)
                            return
                        else:
                            if self.stop_evt.is_set() or self.pause_evt.is_set():
                                continue
                            self.done = True
                            self.app.post(self._finish_ok)
                            return
            except Exception:
                self.failed = True
                self.started = False
                self.app.post(self.set_status, 'خطأ عام في التحميل', C_BAD)
                self.app.post(self.app.maybe_finish)
                return

    def _finish_ok(self):
        self.set_status('✓ اكتمل التحميل', C_GOOD)
        try:
            self.bar.configure(value=100)
        except tk.TclError:
            pass
        self.pause_btn.configure(state='disabled')
        self.stop_btn.configure(state='disabled', text='مكتمل')
        fmt = FMT_LABELS[self.app.fmt_var.get()]
        self.app.add_history(self.url, fmt, 'مكتمل')
        self.app.update_total()
        self.app.maybe_finish()

    def hook(self, d):
        if self.stop_evt.is_set():
            raise _StopAbort()
        if self.pause_evt.is_set():
            raise _PauseAbort()
        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            pct = downloaded / total * 100 if total else 0
            speed = d.get('speed')
            eta = d.get('eta')
            text = f'{pct:.0f}%'
            if speed:
                text += f'  |  {human_size(speed)}/ث'
            if eta:
                text += f'  |  متبقي {int(eta)} ث'
            self.app.post(self.set_progress, pct)
            self.app.post(self.set_status, text, C_FG)
            return None
        elif status == 'finished':
            self.app.post(self.set_status, 'معالجة الملف (دمج / تحويل)...', C_MUT)
            return None
        return None


# -*- coding: utf-8 -*-
class _Logger:
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.anim = Anim(root)
        self.items = []
        self.total_size = 0
        self.downloading = 0
        self.completed = 0
        self.parallel_sem = threading.BoundedSemaphore(MAX_PARALLEL)
        self.info_sem = threading.BoundedSemaphore(INFO_POOL)
        self._clip_watch_job = None
        self._last_clip = ''
        self._titles = {}

        self.root.title(APP_NAME)
        self.root.configure(bg=C_BG)
        self.root.geometry('960x760')
        self.root.minsize(720, 560)

        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('Horizontal.TProgressbar', troughcolor='#2a2a2a', background=C_ACC,
                        borderwidth=0, thickness=10)
        style.configure('Treeview', background=C_CARD, fieldbackground=C_CARD, foreground=C_FG,
                        borderwidth=0, rowheight=28, font=('Segoe UI', 9))
        style.configure('Treeview.Heading', background=C_FIELD, foreground=C_FG,
                        relief='flat', font=('Segoe UI', 9, 'bold'))
        style.map('Treeview', background=[('selected', C_ACC)])

        self._build_ui()

        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        self.load_history()
        self.refresh_scroll()
        self.set_status('جاهز', C_GOOD)
        self.root.after(400, self._poll_clipboard)

    def _looks_like_url(self, text):
        t = text.strip().lower()
        if not t or '\n' in t:
            return False
        return ('http://' in t) or ('https://' in t) or ('.' in t and ' ' not in t)

    def _poll_clipboard(self):
        try:
            text = self.root.clipboard_get()
            if (text and self._last_clip != text and self._looks_like_url(text)
                    and self.url_text.get('1.0', 'end').strip() == PLACEHOLDER):
                self._last_clip = text
                self._do_paste()
        except tk.TclError:
            pass
        self.root.after(400, self._poll_clipboard)

    def _build_ui(self):
        root_bg = tk.Frame(self.root, bg=C_BG)
        root_bg.pack(fill='both', expand=True)
        canvas = tk.Canvas(root_bg, bg=C_BG, highlightthickness=0, bd=0)
        vbar = ttk.Scrollbar(root_bg, orient='vertical', command=canvas.yview)
        self.content_root = tk.Frame(canvas, bg=C_BG)
        self.content_root.bind('<Configure>', self._sync_canvas_width)
        window_id = canvas.create_window((0, 0), window=self.content_root, anchor='nw')
        self._window_id = window_id
        self._syncing_width = False
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side='right', fill='both', expand=True)
        vbar.pack(side='right', fill='y')
        self.canvas = canvas
        self.canvas.bind('<Configure>', self._canvas_resized)
        self.content_root.bind('<Configure>', self._on_content_configure)
        self.root.bind_all('<MouseWheel>', self._on_mousewheel)
        self.root.bind_all('<Control-Return>', lambda e: self.start_all())
        self.root.bind_all('<Control-KP_Enter>', lambda e: self.start_all())
        self._canvas_resized_id = None
        self._build_ui_2()

    def _canvas_resized(self, e):
        if self._canvas_resized_id:
            return
        self._canvas_resized_id = self.root.after_idle(self._apply_canvas_width)

    def _apply_canvas_width(self):
        self._canvas_resized_id = None
        try:
            self.canvas.itemconfigure(self._window_id, width=self.canvas.winfo_width())
        except tk.TclError:
            pass
        self.root.after_idle(self.refresh_scroll)

    def _on_content_configure(self, e):
        self.root.after_idle(self.refresh_scroll)

    def _sync_canvas_width(self, e):
        if self._syncing_width:
            return
        self._syncing_width = True
        try:
            width = self.canvas.winfo_width()
            if width > 0 and self.content_root.winfo_reqwidth() != width:
                self.content_root.configure(width=width)
        finally:
            self._syncing_width = False

    def _on_mousewheel(self, e):
        if self.canvas.winfo_height() and self.content_root.winfo_reqheight() > self.canvas.winfo_height():
            d = e.delta
            if d:
                steps = int(-1 * d / 120 * 3)
                if not steps:
                    steps = -1 if d < 0 else 1
                self.canvas.yview_scroll(steps, 'units')
        return 'break'

    def refresh_scroll(self):
        now = time.monotonic()
        if getattr(self, '_last_refresh', 0) and now - self._last_refresh < 0.12:
            return
        self._last_refresh = now
        self.root.after_idle(self._do_refresh)

    def _do_refresh(self):
        try:
            region = self.canvas.bbox('all')
            if region != getattr(self, '_last_region', None):
                self._last_region = region
                self.canvas.configure(scrollregion=region)
        except tk.TclError:
            pass

    def _heading(self, text):
        lbl = tk.Label(self.content_root, text=text, bg=C_BG, fg=C_ACC, font=('Segoe UI', 16, 'bold'),
                       anchor='e')
        lbl.pack(fill='x', padx=20, pady=(16, 8))
        return lbl

    def _card(self):
        card = tk.Frame(self.content_root, bg=C_CARD, highlightbackground=C_BORDER, highlightthickness=1)
        card.pack(fill='x', padx=20, pady=(0, 12))
        return card

    def _field_lbl(self, parent, text, row, col):
        lbl = tk.Label(parent, text=text, bg=C_CARD, fg=C_FG, font=('Segoe UI', 10, 'bold'))
        lbl.grid(row=row, column=col, sticky='w', padx=(12, 4), pady=(10, 2))
        return lbl

    def _combobox(self, parent, values, var, cmd, width=14, row=0, col=0):
        cb = ttk.Combobox(parent, values=values, textvariable=var, state='readonly',
                          width=width, font=('Segoe UI', 10), justify='center')
        cb.grid(row=row, column=col, sticky='w', padx=12, pady=(0, 10))
        cb.bind('<<ComboboxSelected>>', cmd)
        cb.bind('<MouseWheel>', lambda e: 'break')
        return cb

    def animate_btn(self, btn, normal, hover):
        btn.bind('<Enter>', lambda e: self.anim.color(btn, hover, 150))
        btn.bind('<Leave>', lambda e: self.anim.color(btn, normal, 200))
        return btn

    def tooltip(self, widget, text):
        tip = None

        def show(e):
            nonlocal tip
            if tip:
                return
            x = self.root.winfo_pointerx() + 12
            y = self.root.winfo_pointery() + 12
            tip = tk.Toplevel(self.root)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f'+{x}+{y}')
            lbl = tk.Label(tip, text=text, bg='#000000', fg=C_FG, font=('Segoe UI', 9), padx=8, pady=4,
                           justify='right')
            lbl.pack()

        def hide(e):
            nonlocal tip
            if tip:
                tip.destroy()
                tip = None

        widget.bind('<Enter>', show)
        widget.bind('<Leave>', hide)
        return widget

    def _build_ui_2(self):
        self._heading('⬇️ Video Downloader')
        sub = tk.Label(self.content_root, text='مجاني بالكامل — الصق الروابط وضغط تحميل (Ctrl+V لصق • Ctrl+Enter تحميل)',
                       bg=C_BG, fg=C_MUT, font=('Segoe UI', 9), anchor='e')
        sub.pack(fill='x', padx=20, pady=(0, 10))

        url_card = self._card()
        url_lbl = tk.Label(url_card, text='🔗 روابط الفيديو (رابط في كل سطر)', bg=C_CARD, fg=C_FG,
                           font=('Segoe UI', 10, 'bold'), anchor='w')
        url_lbl.pack(fill='x', padx=12, pady=(10, 2))
        entry_frame = tk.Frame(url_card, bg=C_CARD)
        entry_frame.pack(fill='x', padx=12, pady=(0, 4))
        self.url_text = tk.Text(entry_frame, height=5, bg=C_FIELD, fg=C_MUT, insertbackground=C_FG,
                                relief='flat', font=('Segoe UI', 10), undo=True, wrap='word',
                                selectbackground=C_ACC, selectforeground='white')
        self.url_text.pack(side='right', fill='x', expand=True)
        self.url_text.insert('1.0', PLACEHOLDER)
        self.url_text.bind('<FocusIn>', self.on_url_focus_in)
        self.url_text.bind('<FocusOut>', self.on_url_focus_out)
        self.url_text.bind('<Button-3>', self._url_context_menu)
        self.url_text.bind('<Control-v>', self._handle_paste)
        self.url_text.bind('<Control-V>', self._handle_paste)
        self.url_text.bind('<Control-c>', self._handle_copy)
        self.url_text.bind('<Control-C>', self._handle_copy)
        self.url_text.bind('<Control-x>', self._handle_cut)
        self.url_text.bind('<Control-X>', self._handle_cut)
        self.url_text.bind('<Control-a>', self._select_all)
        self.url_text.bind('<Control-z>', self._handle_undo)
        self.url_text.bind('<Control-y>', self._handle_redo)
        self.url_text.bind('<Control-Z>', self._handle_redo)
        url_btn_row = tk.Frame(url_card, bg=C_CARD)
        url_btn_row.pack(fill='x', padx=12, pady=(2, 10))
        paste_btn = tk.Button(url_btn_row, text='📋 لصق', command=self._do_paste, bg=C_ACC, fg='white',
                              activebackground=C_ACC_H, activeforeground='white', relief='flat',
                              font=('Segoe UI', 9, 'bold'), cursor='hand2', padx=14, pady=5)
        paste_btn.pack(side='right')
        clear_btn = tk.Button(url_btn_row, text='🧹 مسح', command=self.clear_links, bg=C_FIELD, fg=C_FG,
                              activebackground=C_ACC, activeforeground='white', relief='flat',
                              font=('Segoe UI', 9, 'bold'), cursor='hand2', padx=14, pady=5)
        clear_btn.pack(side='right', padx=(6, 0))
        self.url_hint = tk.Label(url_btn_row, text='', bg=C_CARD, fg=C_MUT, font=('Segoe UI', 8),
                                 anchor='w')
        self.url_hint.pack(side='right', fill='x', expand=True, padx=(10, 0))
        self.animate_btn(clear_btn, C_FIELD, C_ACC)
        self.animate_btn(paste_btn, C_ACC, C_ACC_H)

        opt_card = self._card()
        g = tk.Frame(opt_card, bg=C_CARD)
        g.pack(fill='x', padx=12, pady=10)
        self.fmt_var = tk.StringVar(value='MP4 فيديو')
        self.q_var = tk.StringVar(value='الأفضل')
        self.bitrate_var = tk.StringVar(value='128 kbps')
        self.audio_bitrate = tk.StringVar(value='128')
        self._field_lbl(g, 'الصيغة', 0, 0)
        self.fmt_cb = self._combobox(g, list(FMT_LABELS.keys()), self.fmt_var, self.on_fmt_change, 12, 0, 1)
        self.q_lbl = self._field_lbl(g, 'الجودة', 0, 2)
        self.q_cb = self._combobox(g, QUALITY_LABELS, self.q_var, lambda e: None, 10, 0, 3)
        self.bit_lbl = self._field_lbl(g, 'معدل البت', 0, 4)
        self.bit_cb = self._combobox(g, list(AUDIO_BITRATES.keys()), self.bitrate_var,
                                     self.on_bitrate_change, 16, 0, 5)
        self.on_fmt_change()

        act_card = self._card()
        self.total_size_lbl = tk.Label(act_card, text='📦 إجمالي الحجم: 0', bg=C_CARD, fg=C_TEAL,
                                       font=('Segoe UI', 11, 'bold'), anchor='w')
        self.total_size_lbl.pack(fill='x', padx=12, pady=(10, 2))
        self.count_lbl = tk.Label(act_card, text='عدد الفيديوهات: 0', bg=C_CARD, fg=C_MUT,
                                  font=('Segoe UI', 9), anchor='w')
        self.count_lbl.pack(fill='x', padx=12, pady=(0, 2))
        folder_row = tk.Frame(act_card, bg=C_CARD)
        folder_row.pack(fill='x', padx=12, pady=(2, 4))
        self.folder_lbl = tk.Label(folder_row, text='📁 مجلد الحفظ: ' + DEFAULT_FOLDER, bg=C_CARD,
                                   fg=C_MUT, font=('Segoe UI', 8), anchor='w')
        self.folder_lbl.pack(side='right', fill='x', expand=True, padx=(10, 0))
        open_btn = tk.Button(folder_row, text='📂 فتح المجلد', command=self.open_folder, bg=C_FIELD,
                             fg=C_FG, activebackground=C_ACC, activeforeground='white', relief='flat',
                             font=('Segoe UI', 8, 'bold'), cursor='hand2', padx=10, pady=4)
        open_btn.pack(side='right')
        pick_btn = tk.Button(folder_row, text='🗂️ تغيير المجلد', command=self.pick_folder, bg=C_FIELD,
                             fg=C_FG, activebackground=C_ACC, activeforeground='white', relief='flat',
                             font=('Segoe UI', 8, 'bold'), cursor='hand2', padx=10, pady=4)
        pick_btn.pack(side='right', padx=(6, 0))
        self.animate_btn(open_btn, C_FIELD, C_ACC)
        self.animate_btn(pick_btn, C_FIELD, C_ACC)
        self.tooltip(pick_btn, 'اختر مكان حفظ الملفات')
        self.tooltip(open_btn, 'فتح مجلد الحفظ الحالي')
        row = tk.Frame(act_card, bg=C_CARD)
        row.pack(fill='x', padx=12, pady=(4, 10))
        self.dl_btn = tk.Button(row, text='🚀 بدء التحميل', command=self.start_all, bg=C_ACC, fg='white',
                                activebackground=C_ACC_H, activeforeground='white', relief='flat',
                                font=('Segoe UI', 12, 'bold'), cursor='hand2', padx=20, pady=8)
        self.dl_btn.pack(side='right')
        self.pause_all_btn = tk.Button(row, text='⏸️ إيقاف الكل', command=self.pause_all, bg=C_FIELD,
                                       fg=C_FG, activebackground=C_ACC, activeforeground='white',
                                       relief='flat', font=('Segoe UI', 9, 'bold'), cursor='hand2',
                                       padx=12, pady=8)
        self.pause_all_btn.pack(side='right', padx=(8, 0))
        self.resume_all_btn = tk.Button(row, text='▶️ استئناف الكل', command=self.resume_all, bg=C_FIELD,
                                        fg=C_FG, activebackground=C_ACC, activeforeground='white',
                                        relief='flat', font=('Segoe UI', 9, 'bold'), cursor='hand2',
                                        padx=12, pady=8)
        self.resume_all_btn.pack(side='right', padx=(8, 0))
        self.animate_btn(self.pause_all_btn, C_FIELD, C_ACC)
        self.animate_btn(self.resume_all_btn, C_FIELD, C_ACC)
        self.animate_btn(self.dl_btn, C_ACC, C_ACC_H)
        self.tooltip(self.dl_btn, 'تحميل جميع الفيديوهات بالتوازي')
        self.tooltip(self.pause_all_btn, 'إيقاف مؤقت لكل التحميلات الجارية')
        self.tooltip(self.resume_all_btn, 'استئناف كل التحميلات المتوقفة')

        list_card = self._card()
        list_header = tk.Frame(list_card, bg=C_CARD)
        list_header.pack(fill='x', padx=12, pady=(10, 2))
        self.list_lbl = tk.Label(list_header, text='📄 الفيديوهات المضافة', bg=C_CARD, fg=C_FG,
                                 font=('Segoe UI', 10, 'bold'), anchor='w')
        self.list_lbl.pack(side='right')

        self.list_container = tk.Frame(self.content_root, bg=C_BG)
        self.list_container.pack(fill='x', padx=0, pady=(0, 8))

        status_card = self._card()
        self.status_lbl_main = tk.Label(status_card, text='', bg=C_CARD, fg=C_GOOD,
                                        font=('Segoe UI', 9, 'bold'), anchor='w')
        self.status_lbl_main.pack(fill='x', padx=12, pady=10)

        footer_card = self._card()
        footer_inner = tk.Frame(footer_card, bg=C_CARD)
        footer_inner.pack(fill='x', padx=12, pady=8)
        self.footer_lbl = tk.Label(footer_inner, text='', bg=C_CARD, fg=C_MUT, font=('Segoe UI', 8),
                                   justify='center', wraplength=640)
        self.footer_lbl.pack(fill='x')
        dev_row = tk.Frame(footer_inner, bg=C_CARD)
        dev_row.pack(fill='x', pady=(6, 0))
        wa_btn = tk.Button(dev_row, text='💬 واتساب المطور', command=self.contact_developer, bg=C_ACC,
                           fg='white', activebackground=C_ACC_H, activeforeground='white', relief='flat',
                           font=('Segoe UI', 9, 'bold'), cursor='hand2', padx=14, pady=5)
        wa_btn.pack(side='right')
        copy_btn = tk.Button(dev_row, text='📋 نسخ الرقم', command=self.copy_number, bg=C_FIELD, fg=C_FG,
                             activebackground=C_ACC, activeforeground='white', relief='flat',
                             font=('Segoe UI', 9, 'bold'), cursor='hand2', padx=14, pady=5)
        copy_btn.pack(side='right', padx=(6, 0))
        self.animate_btn(wa_btn, C_ACC, C_ACC_H)
        self.animate_btn(copy_btn, C_FIELD, C_ACC)
        self.tooltip(wa_btn, 'افتح محادثة واتساب مع المطور')
        self.tooltip(copy_btn, 'انسخ رقم المطور للحفظ')
        self.set_footer()

    def on_bitrate_change(self, e=None):
        self.audio_bitrate.set(AUDIO_BITRATES.get(self.bitrate_var.get(), '128'))
        self.update_total()

    def _select_all(self, e=None):
        if self.url_text.get('1.0', 'end').strip() == PLACEHOLDER:
            return 'break'
        self.url_text.tag_add('sel', '1.0', 'end-1c')
        return 'break'

    def _handle_copy(self, e=None):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.url_text.selection_get())
        except tk.TclError:
            pass
        return 'break'

    def _handle_cut(self, e=None):
        self.url_text.event_generate('<<Cut>>')
        return 'break'

    def _handle_undo(self, e=None):
        self.url_text.event_generate('<<Undo>>')
        return 'break'

    def _handle_redo(self, e=None):
        self.url_text.event_generate('<<Redo>>')
        return 'break'

    def _handle_paste(self, e=None):
        try:
            self._do_paste()
        except tk.TclError:
            pass
        return 'break'

    def _url_context_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0, bg=C_CARD, fg=C_FG, activebackground=C_ACC,
                       activeforeground='white', font=('Segoe UI', 9))
        menu.add_command(label='لصق', command=self._do_paste)
        menu.add_command(label='نسخ', command=self._handle_copy)
        menu.add_command(label='تحديد الكل', command=self._select_all)
        menu.add_command(label='مسح', command=self.clear_links)
        menu.tk_popup(e.x_root, e.y_root)
        return None

    def on_url_focus_in(self, e=None):
        if self.url_text.get('1.0', 'end').strip() == PLACEHOLDER:
            self.url_text.delete('1.0', 'end')
            self.url_text.configure(fg=C_FG)
        return None

    def on_url_focus_out(self, e=None):
        if not self.url_text.get('1.0', 'end').strip():
            self.url_text.insert('1.0', PLACEHOLDER)
            self.url_text.configure(fg=C_MUT)
        return None

    def clear_links(self):
        self.url_text.delete('1.0', 'end')
        self.url_text.insert('1.0', PLACEHOLDER)
        self.url_text.configure(fg=C_MUT)
        self._update_url_hint()
        self.root.after(100, lambda: self.root.focus_set())

    def current_links(self):
        txt = self.url_text.get('1.0', 'end')
        links = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        return links

    def _update_url_hint(self):
        links = self.current_links()
        real = [l for l in links if l != PLACEHOLDER]
        if not real:
            self.url_hint.configure(text='')
            return
        self.url_hint.configure(text=f'تم رصد {len(real)} رابط — اضغط Enter للبدء أو انتظر الجلب')

    def _do_paste(self):
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            raw = ''
        if not raw:
            return
        self.on_url_focus_in()
        try:
            self.url_text.insert('insert', raw)
        except tk.TclError:
            try:
                self.url_text.insert('1.0', raw)
            except tk.TclError:
                return
        self._update_url_hint()
        self.post(self._auto_add_items)

    def _auto_add_items(self):
        real = [l for l in self.current_links() if l != PLACEHOLDER]
        self._add_urls(real)

    def _add_urls(self, urls):
        existing = {it.url for it in self.items}
        added = 0
        for u in urls:
            if not u or u in existing:
                continue
            item = DownloadItem(self, u)
            self.items.append(item)
            existing.add(u)
            added += 1
            item.start_info()
        if added:
            self.log_line(f'تمت إضافة {added} رابط')
        self.refresh_scroll()
        self.update_total()

    def clear_items(self):
        for it in list(self.items):
            it.stop()
        self.items.clear()
        for w in self.list_container.winfo_children():
            w.destroy()
        self.total_size = 0
        self.completed = 0
        self.downloading = 0
        self.update_total()
        self.refresh_scroll()
        self.set_status('تم مسح القائمة', C_GOOD)

    def remove_item(self, item, destroy=True):
        if item in self.items:
            self.items.remove(item)
        if destroy:
            try:
                item.frame.destroy()
            except tk.TclError:
                pass

    def on_fmt_change(self, e=None):
        fmt = FMT_LABELS[self.fmt_var.get()]
        if fmt == 'mp3':
            self.q_lbl.configure(fg=C_DIS)
            self.q_cb.configure(state='disabled')
            self.bit_lbl.configure(fg=C_FG)
            self.bit_cb.configure(state='readonly')
        else:
            self.q_lbl.configure(fg=C_FG)
            self.q_cb.configure(state='readonly')
            self.bit_lbl.configure(fg=C_DIS)
            self.bit_cb.configure(state='disabled')
        self.update_total()

    def info_opts(self):
        return {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'extract_flat': 'in_playlist',
            'logger': _Logger(),
            'ffmpeg_location': get_ffmpeg_dir(),
        }

    def download_opts(self):
        fmt = FMT_LABELS[self.fmt_var.get()]
        out = str(Path(DEFAULT_FOLDER) / '%(title)s.%(ext)s')
        opts = {
            'outtmpl': out,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'logger': _Logger(),
            'ffmpeg_location': get_ffmpeg_dir(),
            'noprogress': True,
            'restrictfilenames': True,
            'retries': 10,
            'fragment_retries': 10,
            'concurrent_fragment_downloads': 4,
            'socket_timeout': 30,
        }
        if fmt in AUDIO_CODEC:
            opts['format'] = build_format_string(fmt, self.q_var.get())
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': AUDIO_CODEC[fmt],
                'preferredquality': self.audio_bitrate.get() if fmt in BITRATE_FMTS else '0',
            }]
        else:
            opts['format'] = build_format_string(fmt, self.q_var.get())
            opts['merge_output_format'] = fmt
            opts['postprocessors'] = [{'key': 'FFmpegVideoConvertor', 'preferedformat': fmt}]
        return opts

    def compute_size(self, info):
        fmt = FMT_LABELS[self.fmt_var.get()]
        q = self.q_var.get()

        def fsize(f):
            return f.get('filesize') or f.get('filesize_approx') or 0

        fmts = info.get('formats') or []
        videos = [f for f in fmts if f.get('vcodec') and f.get('vcodec') != 'none']
        audios = [f for f in fmts
                  if (not f.get('vcodec') or f.get('vcodec') == 'none')
                  and f.get('acodec') and f.get('acodec') != 'none']
        if fmt in AUDIO_CODEC:
            best_a = max(audios, key=fsize, default={})
            return fsize(best_a)
        if q == 'الأفضل':
            best_v = max(videos, key=lambda f: f.get('height') or 0, default={})
        else:
            h = int(HEIGHTS.get(q, '1080'))
            cand = [f for f in videos if (f.get('height') or 0) <= h]
            best_v = (max(cand, key=lambda f: f.get('height') or 0, default={})
                      or max(videos, key=lambda f: f.get('height') or 0, default={}))
        best_a = max(audios, key=fsize, default={})
        return fsize(best_v) + fsize(best_a)

    def start_all(self):
        urls = [l for l in self.current_links() if l != PLACEHOLDER]
        if urls:
            self._add_urls(urls)
        ready = [it for it in self.items if it.ready and not it.started and not it.done]
        if not ready:
            pending = [it for it in self.items if not it.ready and not it.info_error]
            if pending:
                self.set_status(f'في انتظار معلومات {len(pending)} فيديو...', C_MUT)
                self.root.after(300, self.start_all)
                return
            if self.completed:
                self.set_status('تم تحميل كل الفيديوهات ✓', C_GOOD)
            else:
                self.set_status('لا يوجد فيديو جاهز', C_MUT)
            return
        self.downloading = 0
        for it in ready:
            it.started = True
            it.pause_evt.clear()
            it.stop_evt.clear()
            it.thread = threading.Thread(target=it._download_worker, daemon=True)
            it.thread.start()
            self.downloading += 1
        self.set_status(f'بدأ تحميل {len(ready)} فيديو بالتوازي (الحد الأقصى {MAX_PARALLEL})', C_GOOD)
        self.log_line(f'بدء التحميل: {len(ready)} عنصر')
        self.maybe_finish()

    def pause_all(self):
        for it in self.items:
            if it.started and not it.done and not it.stopped and not it.paused:
                it.pause_evt.set()
                it.paused = True
        self.set_status('إيقاف مؤقت للجميع', C_MUT)
        self.root.after(100, self._update_pause_buttons)

    def resume_all(self):
        for it in self.items:
            if it.started and it.paused and not it.done and not it.stopped:
                it.pause_evt.clear()
                it.paused = False
        self.set_status('استئناف الجميع', C_GOOD)
        self.root.after(100, self._update_pause_buttons)

    def stop_all(self):
        for it in self.items:
            if it.started and not it.done and not it.stopped:
                it.stop()
        self.set_status('إيقاف الكل', C_BAD)

    def _update_pause_buttons(self):
        for it in self.items:
            it._set_pause_ui()

    def update_total(self):
        self.total_size = 0
        for it in self.items:
            if it.size and not it.stopped and not it.failed and not it.done:
                self.total_size += it.size
        if hasattr(self, 'total_size_lbl'):
            self.total_size_lbl.configure(text='📦 إجمالي الحجم: ' + human_size(self.total_size))
            self.count_lbl.configure(text=f'عدد الفيديوهات: {len(self.items)}')
        self._update_url_hint()

    def maybe_finish(self):
        active = [it for it in self.items if it.started and not it.done and not it.stopped and not it.failed]
        if not active and self.downloading > 0:
            self.downloading = 0
            done = len([it for it in self.items if it.done])
            failed = len([it for it in self.items if it.failed])
            self.set_status(f'انتهى التحميل — ناجح: {done}، فشل: {failed}', C_GOOD)
            self.completed += done
            self.update_total()
            self.refresh_scroll()

    def post(self, fn, *args):
        def wrap():
            try:
                fn(*args)
            except Exception:
                pass
        self.root.after(0, wrap)

    def set_status(self, text, color=C_GOOD):
        try:
            self.status_lbl_main.configure(text=text, fg=color)
        except tk.TclError:
            pass

    def log_line(self, text):
        ts = datetime.now().strftime('%H:%M:%S')
        print(f'[{ts}] {text}', file=sys.stderr)
        self.set_status(text, C_GOOD)

    def set_footer(self):
        self.footer_lbl.configure(
            text=f'📱 تواصل مع المطور: {DEV_WHATSAPP}'
                 f'\nالبرنامج مجاني بالكامل — كل اللي محتاجه إنك تلصق الرابط وتضغط تحميل 😊')

    def contact_developer(self, e=None):
        webbrowser.open(f'https://wa.me/2{DEV_WHATSAPP}')
        return None

    def copy_number(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append('+20' + DEV_WHATSAPP.lstrip('0'))
            self.set_status('تم نسخ رقم المطور ✓', C_GOOD)
        except tk.TclError:
            pass
        return None

    def add_history(self, url, fmt, result):
        try:
            history = []
            if HISTORY_FILE.exists():
                history = json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
            history.append({'time': datetime.now().isoformat(), 'url': url, 'format': fmt, 'result': result})
            history = history[-200:]
            HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    def load_history(self):
        try:
            if HISTORY_FILE.exists():
                self._history = json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
            else:
                self._history = []
        except Exception:
            self._history = []

    def pick_folder(self):
        folder = filedialog.askdirectory(title='اختر مجلد الحفظ')
        if folder:
            global DEFAULT_FOLDER
            DEFAULT_FOLDER = folder
            self.folder_lbl.configure(text='📁 مجلد الحفظ: ' + DEFAULT_FOLDER)
            self.set_status(f'سيتم الحفظ في: {folder}', C_GOOD)
        return None

    def open_folder(self):
        os.startfile(DEFAULT_FOLDER)
        return None

    def expand_playlist(self, entries, parent):
        if not entries:
            return
        self.remove_item(parent, destroy=True)
        urls = []
        for entry in entries:
            if not entry or not entry.get('id'):
                continue
            web_url = entry.get('webpage_url') or entry.get('url')
            if not web_url or not str(web_url).startswith('http'):
                continue
            urls.append(str(web_url))
        self._add_urls(urls)
        self.set_status(f'تم توسيع قائمة تشغيل إلى {len(urls)} فيديو', C_GOOD)

    def on_close(self):
        self.stop_all()
        try:
            self.root.clipboard_clear()
        except tk.TclError:
            pass
        self.root.destroy()

def run_cli():
    print(f'{APP_NAME} v{VERSION}')
    print('UI mode is the default. Passing a URL downloads it directly.')
    return 0


def get_icon_path():
    base = Path(getattr(sys, '_MEIPASS', BASE_DIR))
    for name in ('app_icon.ico', 'app_icon.png'):
        p = base / name
        if p.is_file():
            return str(p)
    return None


def main():
    if '--cli' in sys.argv:
        return run_cli()
    root = tk.Tk()
    icon = get_icon_path()
    if icon:
        try:
            root.iconbitmap(default=icon)
            root.iconphoto(True, tk.PhotoImage(file=icon))
        except Exception:
            pass
    App(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
