from PIL import Image, ImageDraw, ImageFont

FT = "C:/Windows/Fonts/msyh.ttc"
FTB = "C:/Windows/Fonts/msyhbd.ttc"
W = 1600
BG = (255, 255, 255)
INK = (25, 28, 33)
GREY = (95, 102, 112)
ACC = (176, 32, 32)

def font(sz, bold=False):
    try:
        return ImageFont.truetype(FTB if bold else FT, sz)
    except Exception:
        return ImageFont.load_default()

F_TITLE = font(52, True)
F_SUB = font(28)
F_H = font(34, True)
F_B = font(27)
F_S = font(23)
F_MONO = font(27, True)

def wrap(draw, text, f, maxw):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=f) > maxw:
            lines.append(cur); cur = ch
        else:
            cur += ch
    lines.append(cur)
    return lines

# ---- 上部：标题 ----
head_h = 190
canvas = Image.new("RGB", (W, head_h), BG)
d = ImageDraw.Draw(canvas)
d.rectangle([0, 0, W, 10], fill=ACC)
d.text((48, 42), "拍摄位置判定：西安钟楼 · 西北侧广场", font=F_TITLE, fill=INK)
d.text((50, 122), "西安钟楼夜景 · iQOO 15 · 2026-09-19 19:22 · 判定：机位在钟楼西北约 85 m，朝东南 138° 拍摄", font=F_SUB, fill=GREY)

# ---- 主图区 ----
main_h = 660
photo = Image.open("annot_photo.jpg").convert("RGB")
photo.thumbnail((890, main_h))
mp = Image.open("map_annot.jpg").convert("RGB").crop((150, 150, 1650, 1650))
mp.thumbnail((640, main_h))

sec = Image.new("RGB", (W, main_h + 44), BG)
x = 48
sec.paste(photo, (x, 44))
px0 = x + photo.width + 24
sec.paste(mp, (px0, 44))
d2 = ImageDraw.Draw(sec)
d2.text((48, 8), "① 像素实测：钟楼两面投影宽 624 / 561 px", font=F_H, fill=INK)
d2.text((px0, 8), "② 机位落点与朝向扇形", font=F_H, fill=INK)

# ---- 证据链 ----
ev = [
 ("K1  主体锚定", "照片主体为三重檐攒尖顶、绿琉璃瓦、金宝顶、砖砌券门基座，外围为环形花坛盘道＋十字街 —— 唯一对应西安钟楼（明洪武十七年，全国重点文保，WGS84 34.26147/108.94278）。水印时间为 2026-09-19 19:22。", "photo.jpg"),
 ("K2  相机方位（实测）", "像素扫描基座左右棱与转角棱：左面投影 624 px、右面投影 561 px，比值 1.11 → 两面与视线夹角约 42°/48°，即相机几乎落在钟楼的对角线方向上（偏离约 3°），因此照片中同时看到钟楼相邻两个面。", "annot_photo.jpg"),
 ("K3  机位侧别（排除）", "卫星图：钟楼东南角紧贴开元商城大楼（无空地），东北角为钟楼邮局，西南为钟楼饭店一线；只有西北/西侧是开阔人行广场。照片前景是能容数十人的大铺装广场，因此机位只能在西北侧，排除东南侧与东北侧。", "sat_se_zoom.jpg"),
 ("K4  距离反算", "基座可见宽 1185 px、钟楼通高（宝顶至基座底）905 px。按手机主摄 1x（水平 FOV≈55°）反算：相机距钟楼中心约 85 m；若为长焦则距离相应放大，方位结论不变。", "annot_photo.jpg"),
 ("K5  机位与朝向", "以钟楼中心为原点、方位 318°（西北）、距离 85 m 落点，扇形朝东南 138°（水平视角 54°）—— 扇形完全落在西大街北侧人行广场内，与照片中『广场—栏杆—绿化带—盘道车流—环形花坛—钟楼』的地物序列一致。", "map_annot.jpg"),
]

rows = []
maxw = W - 400
tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
for t, b, img in ev:
    rows.append((t, wrap(tmp, b, F_B, maxw), img))
ev_h = sum(max(150, 20 + 40 * len(r[1])) for r in rows) + 30 * len(rows) + 40

# ---- 底部 ----
foot_h = 320
H = head_h + main_h + 44 + ev_h + foot_h
out = Image.new("RGB", (W, H), BG)
out.paste(canvas, (0, 0))
out.paste(sec, (0, head_h))
d = ImageDraw.Draw(out)

y = head_h + main_h + 44
d.rectangle([0, y, W, y + 4], fill=(220, 224, 230))
d.text((48, y + 22), "证据链", font=F_H, fill=ACC)
y += 84
for t, lines, img in rows:
    thumb = Image.open(img).convert("RGB")
    thumb.thumbnail((260, 150))
    ty = y + max(0, (max(150, 20 + 40 * len(lines)) - thumb.height) // 2)
    out.paste(thumb, (48, ty))
    d.text((336, y + 4), t, font=F_H, fill=ACC)
    for i, ln in enumerate(lines):
        d.text((336, y + 50 + i * 40), ln, font=F_B, fill=INK)
    y += max(150, 20 + 40 * len(lines)) + 30

d.rectangle([0, y, W, y + 4], fill=(220, 224, 230))
y += 24
d.text((48, y), "结论坐标", font=F_H, fill=ACK if False else ACC)
d.text((48, y + 46), "WGS84  34.26204 N, 108.94216 E   （±40 m）", font=F_MONO, fill=INK)
d.text((48, y + 86), "GCJ-02  34.26046 N, 108.94682 E      BD-09  34.26671 N, 108.95324 E", font=F_S, fill=GREY)
d.text((48, y + 126), "相机朝向：东南约 138°   可见面：钟楼北面（画面左，较正）＋ 西面（画面右，较侧）", font=F_B, fill=INK)
d.text((48, y + 166), "置信度：城市级 高（唯一锚点钟楼）｜片区级 高（西北侧广场）｜点位级 中（±40 m，缺该时段车行道街景逐点比对）", font=F_B, fill=ACC)

out.save("conclusion.jpg", quality=90)
print(out.size)
