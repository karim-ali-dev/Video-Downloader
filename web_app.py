# -*- coding: utf-8 -*-
"""
Video Downloader - Web Edition (mobile-friendly, NO dependencies, stdlib only)
Run:  python web_app.py   then open http://127.0.0.1:8000 from any device
On the same Wi-Fi, open http://<this-PC-IP>:8000 from your phone browser.
"""
import json
import mimetypes
import os
import shutil
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = BASE_DIR / '.web_tmp'
TMP_DIR.mkdir(exist_ok=True)
SOCKET_TIMEOUT = 3600

PAGE = '''<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Downloader - ويب</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "Segoe UI", Tahoma, Arial, sans-serif; background: #121212; color: #fff;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 16px; }
  .card { background: #1c1c1c; border: 1px solid #3f3f3f; border-radius: 14px; max-width: 480px;
          width: 100%; padding: 24px; }
  h1 { font-size: 22px; text-align: center; margin-bottom: 4px; }
  .sub { text-align: center; color: #d9d9d9; font-size: 13px; margin-bottom: 20px; }
  textarea { width: 100%; min-height: 90px; background: #2a2a2a; color: #fff; border: 1px solid #3f3f3f;
             border-radius: 10px; padding: 12px; font-size: 14px; resize: vertical; }
  select { width: 100%; background: #2a2a2a; color: #fff; border: 1px solid #3f3f3f; border-radius: 10px;
           padding: 10px; font-size: 14px; margin-top: 10px; }
  button { width: 100%; background: #d62828; color: #fff; border: none; border-radius: 10px; padding: 14px;
           font-size: 16px; font-weight: bold; margin-top: 14px; cursor: pointer; }
  button:disabled { opacity: .6; cursor: wait; }
  .status { margin-top: 14px; text-align: center; font-size: 14px; color: #d9d9d9; min-height: 20px; white-space: pre-line; }
  .ok { color: #7ee787; }
  .err { color: #ff6b6b; }
  .row { margin-top: 10px; }
  .row label { font-size: 12px; color: #d9d9d9; }
</style>
</head>
<body>
<div class="card">
  <h1>⬇️ Video Downloader</h1>
  <div class="sub">مجاني بالكامل</div>
  <textarea id="urls" placeholder="الصق الروابط هنا... رابط في كل سطر"></textarea>
  <div class="row"><label>الصيغة</label>
    <select id="fmt">
      <option value="mp4">MP4 فيديو</option>
      <option value="mkv">MKV فيديو</option>
      <option value="mp3">MP3 صوت</option>
    </select>
  </div>
  <button id="btn" onclick="go()">🚀 تحميل</button>
  <div class="status" id="status"></div>
</div>
<script>
var poll = null;
function go() {
  var urls = document.getElementById('urls').value.trim().split(/\\n+/).filter(Boolean);
  var fmt = document.getElementById('fmt').value;
  if (!urls.length) { show('الصق رابط على الأقل', 'err'); return; }
  document.getElementById('btn').disabled = true;
  show('جارٍ المعالجة...');
  fetch('/download', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({urls: urls, fmt: fmt})
  }).then(function(r){ return r.json(); })
    .then(function(d){
      if (d.id) {
        poll = setInterval(function(){ check(d.id); }, 1500);
      } else {
        show(d.error || 'حدث خطأ', 'err');
        document.getElementById('btn').disabled = false;
      }
    }).catch(function(){ show('خطأ في الاتصال', 'err'); document.getElementById('btn').disabled = false; });
}
function check(id) {
  fetch('/status/' + id).then(function(r){ return r.json(); })
    .then(function(d){
      if (d.done) {
        clearInterval(poll);
        show(d.msg || 'الفيديو جاهز — جاري فتحه...', 'ok');
        window.location.href = '/file/' + id;
      } else if (d.error) {
        clearInterval(poll);
        show(d.error, 'err');
        document.getElementById('btn').disabled = false;
      } else {
        show(d.msg || 'جارٍ التحميل...');
      }
    }).catch(function(){});
}
function show(msg, cls) {
  var el = document.getElementById('status');
  el.className = 'status ' + (cls || '');
  el.textContent = msg;
}
</script>
</body>
</html>'''


def get_ffmpeg_dir():
    cands = []
    if getattr(sys, 'frozen', False):
        cands.append(Path(getattr(sys, '_MEIPASS', BASE_DIR)) / 'tools' / 'ffmpeg')
    cands.append(BASE_DIR / 'tools' / 'ffmpeg')
    local = os.environ.get('LOCALAPPDATA')
    if local:
        cands.append(Path(local))
    for cand in cands:
        if (cand / 'ffmpeg.exe').is_file() and (cand / 'ffprobe.exe').is_file():
            return str(cand)
    return None


class Job:
    def __init__(self, task_id, urls, fmt):
        self.task_id = task_id
        self.urls = urls
        self.fmt = fmt
        self.dir = TMP_DIR / task_id
        self.dir.mkdir(exist_ok=True)
        self.done = False
        self.error = None
        self.msg = 'في قائمة الانتظار...'
        threading.Thread(target=self.run, daemon=True).start()

    def build_opts(self):
        opts = {
            'outtmpl': str(self.dir / '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'ffmpeg_location': get_ffmpeg_dir(),
            'noprogress': True,
            'restrictfilenames': True,
            'retries': 5,
            'socket_timeout': 30,
            'progress_hooks': [self.hook],
        }
        fmt = self.fmt
        if fmt == 'mp3':
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3',
                                       'preferredquality': '192'}]
        else:
            if fmt == 'mp4':
                opts['format'] = ('best[ext=mp4]'
                                  '/bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]'
                                  '/bestvideo+bestaudio/best')
            else:
                opts['format'] = 'best/bestvideo+bestaudio/best'
            opts['merge_output_format'] = fmt
            opts['postprocessors'] = [{'key': 'FFmpegVideoConvertor', 'preferedformat': fmt}]
        return opts

    def hook(self, d):
        s = d.get('status')
        if s == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            done = d.get('downloaded_bytes') or 0
            pct = done / total * 100 if total else 0
            sp = d.get('speed')
            text = f'التحميل: {pct:.0f}%'
            if sp:
                text += f'  ({human_size(sp)}/ث)'
            self.msg = text
        elif s == 'finished':
            self.msg = 'معالجة الملف (دمج/تحويل)...'

    def run(self):
        try:
            with yt_dlp.YoutubeDL(self.build_opts()) as ydl:
                ydl.download(self.urls)
            self.done = True
            self.msg = 'اكتمل'
        except Exception as e:
            self.error = str(e)[:200]
            self.msg = self.error
        self._cleanup_later()

    def _cleanup_later(self):
        def _del():
            time.sleep(600)
            shutil.rmtree(str(self.dir), ignore_errors=True)
        threading.Thread(target=_del, daemon=True).start()


def human_size(n):
    if not n:
        return ''
    for unit in ('بايت', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return ''


JOBS = {}


class Handler(BaseHTTPRequestHandler):
    server_version = 'VideoDownloader/4.0'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s\n' % (fmt % args))

    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            self._send(200, PAGE, 'text/html')
            return
        if path.startswith('/status/'):
            tid = path[len('/status/'):]
            job = JOBS.get(tid)
            if not job:
                self._json({'error': 'المهمة غير موجودة'})
                return
            self._json({'done': job.done, 'msg': job.msg, 'error': job.error})
            return
        if path.startswith('/file/'):
            tid = path[len('/file/'):]
            job = JOBS.get(tid)
            if not job or not job.done:
                self._json({'error': 'الملف غير جاهز بعد'})
                return
            files = [f for f in job.dir.iterdir()
                     if f.is_file() and not f.name.endswith(('.part', '.ytdl'))]
            if not files:
                self._json({'error': 'لا يوجد ملف'})
                return
            target = max(files, key=lambda f: f.stat().st_size)
            if target.suffix not in ('.mp4', '.mkv', '.mp3', '.webm', '.m4a', '.mov'):
                self._json({'error': 'صيغة غير مدعومة'})
                return
            self.send_response(200)
            ctype = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Disposition',
                             f"attachment; filename*=UTF-8''{target.name}")
            self.send_header('Content-Length', str(target.stat().st_size))
            self.end_headers()
            with open(str(target), 'rb') as f:
                shutil.copyfileobj(f, self.wfile)
            return
        self._send(404, 'Not found', 'text/plain')

    def do_POST(self):
        path = urlparse(self.path).path
        if path != '/download':
            self._send(404, 'Not found', 'text/plain')
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length)
            data = json.loads(raw.decode('utf-8'))
        except Exception:
            self._json({'error': 'طلب غير صالح'}, 400)
            return
        urls = [u.strip() for u in (data.get('urls') or []) if u.strip()]
        fmt = (data.get('fmt') or 'mp4').strip().lower()
        if not urls:
            self._json({'error': 'لا يوجد روابط'}, 400)
            return
        tid = uuid.uuid4().hex[:12]
        JOBS[tid] = Job(tid, urls, fmt)
        self._json({'id': tid})


def main():
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '8000'))
    server = ThreadingHTTPServer((host, port), Handler)
    server.socket.settimeout(SOCKET_TIMEOUT)
    local_ip = '127.0.0.1'
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    print('=' * 50)
    print('  Video Downloader — النسخة الويب')
    print('=' * 50)
    print(f'  من الجهاز ده:  http://127.0.0.1:{port}')
    print(f'  من الموبايل (نفس الواي فاي):  http://{local_ip}:{port}')
    print('  وقف: Ctrl+C')
    print('=' * 50)
    if os.environ.get('WINDOWS_OPEN'):
        webbrowser.open(f'http://127.0.0.1:{port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
