# -*- coding: utf-8 -*-
# Video Downloader - Android CLI runner (for Termux)
import os
import sys
import yt_dlp

FOLDER = os.path.join(os.path.expanduser('~'), 'storage', 'downloads')
os.makedirs(FOLDER, exist_ok=True)

FMT = 'mp4'
QUALITY = 'best'


def get_format():
    f = FMT
    if f == 'mp4':
        return 'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
    return 'bestvideo+bestaudio/best'


def human(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f}{u}'
        n /= 1024
    return ''


def hook(d):
    if d.get('status') == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        done = d.get('downloaded_bytes') or 0
        pct = done / total * 100 if total else 0
        sp = d.get('speed')
        sys.stdout.write(f'\r  التحميل: {pct:.0f}%  ({human(done)} / {human(total)})'
                         + (f'  {human(sp)}/s' if sp else '') + '   ')
        sys.stdout.flush()
    elif d.get('status') == 'finished':
        sys.stdout.write('\r  اكتمل التنزيل، جارٍ المعالجة...   \n')


def main():
    print('=' * 50)
    print('  Video Downloader - Android')
    print('=' * 50)
    if len(sys.argv) > 1:
        urls = sys.argv[1:]
    else:
        urls = []
        print('   الصق الروابط (رابط في كل سطر) ثم اضغط Enter، واكتب done للانتهاء:')
        while True:
            try:
                line = input('> ').strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            if line.lower() in ('done', 'exit', 'خروج'):
                break
            urls.append(line)
    if not urls:
        print('  لا توجد روابط.')
        return
    print(f'  سيتم الحفظ في: {FOLDER}')
    opts = {
        'outtmpl': os.path.join(FOLDER, '%(title)s.%(ext)s'),
        'format': get_format(),
        'merge_output_format': FMT,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'progress_hooks': [hook],
        'retries': 10,
        'socket_timeout': 30,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            for url in urls:
                print(f'\n  بدء تحميل: {url}')
                try:
                    ydl.download([url])
                except Exception as e:
                    print(f'\n  فشل التحميل: {e}')
        print('\n  تم بفضل الله ✓')
    except Exception as e:
        print(f'\n  خطأ: {e}')


if __name__ == '__main__':
    main()
