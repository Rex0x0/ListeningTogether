import tkinter as tk
from tkinter import font as tkfont
import threading
import time
import requests
from PIL import Image, ImageTk
import io
import netease_client
from ThemeTokens import ThemeTokens

# --- 全局变量 ---
currently_displayed_song = None
album_cover_photo = None  # 保持对 PhotoImage 的引用


def update_album_art(image_url):
    """下载封面并更新专辑图区域。"""
    global album_cover_photo
    try:
        response = requests.get(image_url, timeout=5)
        response.raise_for_status()
        image_data = response.content

        pil_image = Image.open(io.BytesIO(image_data))
        pil_image = pil_image.resize((200, 200), Image.LANCZOS)

        album_cover_photo = ImageTk.PhotoImage(pil_image)
        album_cover_label.config(image=album_cover_photo)

    except requests.exceptions.RequestException as e:
        print(f"下载图片失败: {e}")
        album_cover_label.config(image=placeholder_photo)
    except Exception as e:
        print(f"处理图片失败: {e}")
        album_cover_label.config(image=placeholder_photo)


def polling_loop():
    """定时拉取当前歌曲并刷新界面。"""
    global currently_displayed_song

    while True:
        song_info, error_message = netease_client.get_current_netease_song()

        if song_info:
            song, artist = song_info

            if song != currently_displayed_song:
                print(f"检测到新歌曲: {song}")
                currently_displayed_song = song

                commentary_text.set(f"▶ 正在播放\n{song}\n{artist}\n\n正在获取详情…")
                album_cover_label.config(image=placeholder_photo)

                track_details, detail_error = netease_client.get_track_info(song, artist)

                if track_details:
                    commentary = (
                        f"{track_details['name']}\n"
                        f"{track_details['artist']}\n"
                        f"专辑 · {track_details['album']}\n"
                        f"发行 · {track_details['release_year']}"
                    )
                    commentary_text.set(commentary)

                    threading.Thread(
                        target=update_album_art, args=(track_details["cover_url"],), daemon=True
                    ).start()
                else:
                    commentary_text.set(detail_error or "无法获取曲目详情")

        else:
            if currently_displayed_song is not None or "欢迎" in commentary_text.get():
                currently_displayed_song = None
                commentary_text.set(error_message or "等待播放中的歌曲…")
                album_cover_label.config(image=placeholder_photo)

        time.sleep(5)


# --- 主题色（与 ThemeTokens / UIDesign 对齐）---
T = ThemeTokens
BG_PAGE = T["bgPage"]
BG_CARD = T["bgSecondary"]
BG_INNER = T["bgPrimary"]
ACCENT = T["accent"]
TEXT_HIGH = T["textHigh"]
TEXT_MED = T["textMedium"]
TEXT_LOW = T["textLow"]
DIVIDER = T["divider"]

# --- GUI ---
root = tk.Tk()
root.title("Music Together — MusicFriend")
root.geometry("560x300")
root.minsize(480, 280)
root.configure(bg=BG_PAGE)

# 字体
ff = T["fontFamily"]
title_font = tkfont.Font(family=ff[0], size=T["headingSize"], weight="bold")
body_font = tkfont.Font(family=ff[0], size=T["bodySize"])

outer = tk.Frame(root, bg=BG_PAGE, padx=14, pady=14)
outer.pack(fill=tk.BOTH, expand=True)

# 主卡片容器
main_card = tk.Frame(outer, bg=BG_CARD, highlightbackground=DIVIDER, highlightthickness=1)
main_card.pack(fill=tk.BOTH, expand=True)

inner = tk.Frame(main_card, bg=BG_CARD, padx=14, pady=12)
inner.pack(fill=tk.BOTH, expand=True)

# 顶栏标题
header = tk.Frame(inner, bg=BG_CARD)
header.pack(fill=tk.X, pady=(0, 10))

accent_bar = tk.Frame(header, bg=ACCENT, width=4, height=22)
accent_bar.pack(side=tk.LEFT, padx=(0, 10))
accent_bar.pack_propagate(False)

title_lbl = tk.Label(
    header,
    text="网易云 · 当前播放",
    font=title_font,
    fg=TEXT_HIGH,
    bg=BG_CARD,
    anchor=tk.W,
)
title_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

# 中部：封面 + 信息卡
content_row = tk.Frame(inner, bg=BG_CARD)
content_row.pack(fill=tk.BOTH, expand=True)

# 封面区（嵌套圆角视觉：外框 + 内底）
cover_wrap = tk.Frame(
    content_row,
    bg=BG_INNER,
    highlightbackground=DIVIDER,
    highlightthickness=1,
    padx=4,
    pady=4,
)
cover_wrap.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

placeholder_image = Image.new("RGB", (200, 200), color=BG_INNER)
placeholder_photo = ImageTk.PhotoImage(placeholder_image)

album_cover_label = tk.Label(cover_wrap, image=placeholder_photo, bg=BG_INNER, bd=0)
album_cover_label.pack()

# 文本信息卡
info_card = tk.Frame(
    content_row,
    bg=BG_INNER,
    highlightbackground=DIVIDER,
    highlightthickness=1,
)
info_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

commentary_text = tk.StringVar()
commentary_label = tk.Label(
    info_card,
    textvariable=commentary_text,
    wraplength=300,
    justify=tk.LEFT,
    anchor=tk.NW,
    font=body_font,
    fg=TEXT_MED,
    bg=BG_INNER,
    padx=12,
    pady=10,
)
commentary_label.pack(fill=tk.BOTH, expand=True)

# 状态条
status_bar = tk.Frame(inner, bg=BG_PAGE, height=28)
status_bar.pack(fill=tk.X, pady=(10, 0))
status_hint = tk.Label(
    status_bar,
    text="与网页端共听主题一致 · 暗色卡片布局",
    font=tkfont.Font(family=ff[0], size=9),
    fg=TEXT_LOW,
    bg=BG_PAGE,
    anchor=tk.W,
)
status_hint.pack(fill=tk.X, padx=2)

commentary_text.set("欢迎使用 MusicFriend！正在初始化…")

polling_thread = threading.Thread(target=polling_loop, daemon=True)
polling_thread.start()

netease_client.initialize_netease()

root.mainloop()
