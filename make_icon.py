# -*- coding: utf-8 -*-
import math
from PIL import Image, ImageDraw, ImageFilter

SIZE = 256
BG = (244, 120, 120, 255)          # light red
BG_TOP = (255, 160, 150, 255)      # lighter top gradient
ARROW = (255, 255, 255, 255)       # white

img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

r = 56
d.rounded_rectangle([6, 6, SIZE - 6, SIZE - 6], radius=r, fill=BG)

# subtle top-light gradient overlay
ov = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
do = ImageDraw.Draw(ov)
for y in range(SIZE):
    t = 1 - y / SIZE
    c = (int(BG[0] + (BG_TOP[0] - BG[0]) * t),
         int(BG[1] + (BG_TOP[1] - BG[1]) * t),
         int(BG[2] + (BG_TOP[2] - BG[2]) * t), 255)
    do.line([(0, y), (SIZE, y)], fill=c)
ov = ov.filter(ImageFilter.GaussianBlur(24))
img = Image.alpha_composite(img, ov)

# down arrow
cx, cy = SIZE / 2, SIZE / 2
w, h = 120, 128
sx, ex = cx - w / 2, cx + w / 2
sy, ey = cy - h / 2, cy + h / 2
stem_w = 58
head_w = 128
head_h = 58

d2 = ImageDraw.Draw(img)
# stem (rectangle) and head (triangle) combined into one white shape
mask = Image.new('L', (SIZE, SIZE), 0)
dm = ImageDraw.Draw(mask)
dm.rectangle([cx - stem_w / 2, sy, cx + stem_w / 2, ey - head_h / 2], fill=255)
dm.polygon([(cx - head_w / 2, ey - head_h),
            (cx + head_w / 2, ey - head_h),
            (cx, ey)], fill=255)
# slight rounded tip
tip = Image.new('L', (SIZE, SIZE), 0)
dt = ImageDraw.Draw(tip)
dt.polygon([(cx - head_w / 2, ey - head_h),
            (cx + head_w / 2, ey - head_h),
            (cx, ey + head_h)], fill=255)
mask = Image.composite(tip, mask, tip).filter(ImageFilter.MaxFilter(3))
img.putalpha(img.split()[3])

solid = Image.new('RGBA', (SIZE, SIZE), ARROW)
img = Image.composite(solid, img, mask)

img.save(r'D:\VideoDownloader-portable\app_icon.png')
img.save(r'D:\VideoDownloader-portable\app_icon.ico',
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                (128, 128), (256, 256)])
print('ICON SAVED', img.size)
