import streamlit as st
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import moviepy.editor as mpy
import tempfile
import os
import random

# ---------- Шрифт ----------
FONT_SIZE = 90
FONT_PATH = "Montserrat-Bold.ttf"

if not os.path.exists(FONT_PATH):
    st.error(f"Файл шрифта '{FONT_PATH}' не найден. Добавьте его в репозиторий.")
    st.stop()

try:
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
except IOError:
    st.error("Не удалось загрузить шрифт из локального файла.")
    st.stop()

# ---------- Параметры ячеек и фона ----------
CELL_W, CELL_H = 76, 83          # 20×22 мм при 96 dpi
COLS = 11
WIDTH, HEIGHT = 1920, 1080
LEFT = (WIDTH - COLS * CELL_W) // 2
TOP = (HEIGHT - CELL_H) // 2

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

def is_letter(ch):
    """Заглавная латиница или кириллица (включая Ё)."""
    return ('A' <= ch <= 'Z') or ('А' <= ch <= 'Я') or ch == 'Ё'

def get_alphabet(words):
    """Все уникальные символы из слов, кроме пробела."""
    chars = set()
    for w in words:
        for ch in w:
            if ch != ' ':
                chars.add(ch)
    return sorted(list(chars))

# ---------- Рисование одной ячейки (с обрезкой) ----------
def draw_cell(cell_img, ch, y_rel, is_letter_char):
    draw = ImageDraw.Draw(cell_img)
    if ch == ' ':
        return
    if is_letter_char:
        bbox = draw.textbbox((0, 0), ch, font=font, anchor='lt')
        text_w = bbox[2] - bbox[0]
        x = (CELL_W - text_w) / 2
        draw.text((x, y_rel), ch, font=font, fill=WHITE, anchor='lt')
    else:
        x_center = CELL_W / 2
        y_center = y_rel + CELL_H / 2
        draw.text((x_center, y_center), ch, font=font, fill=WHITE, anchor='mm')

# ---------- Статический кадр ----------
def draw_static_frame(word):
    img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    for i, ch in enumerate(word):
        if ch == ' ':
            continue
        cell_img = Image.new("RGB", (CELL_W, CELL_H), BLACK)
        draw_cell(cell_img, ch, y_rel=0, is_letter_char=is_letter(ch))
        x0 = LEFT + i * CELL_W
        img.paste(cell_img, (x0, TOP))
    return np.array(img)

# ---------- Параметры скроллинга ----------
def generate_spin_params(target_word, alphabet, spin_duration, fps):
    v_min = 2 * CELL_H / spin_duration
    v_max = 5 * CELL_H / spin_duration
    pools = []
    speeds = []
    for i in range(COLS):
        if target_word[i] == ' ':
            pools.append([])
            speeds.append(0.0)
            continue
        pool = random.choices(alphabet, k=30)
        pools.append(pool)
        for _ in range(100):
            v = random.uniform(v_min, v_max)
            if i > 0 and target_word[i-1] != ' ' and abs(v - speeds[i-1]) < 0.3 * (v_max - v_min):
                continue
            break
        speeds.append(v)
    return pools, speeds

# ---------- Кадр вращения с обрезкой ----------
def draw_spin_frame(t_spin, pools, speeds, target_word, last_frame=False):
    # Если last_frame=True, показываем первую букву следующего слова во всех непустых ячейках
    if last_frame:
        first_char = target_word[0] if target_word[0] != ' ' else ' '
        display_word = ''.join([first_char if target_word[i] != ' ' else ' ' for i in range(COLS)])
        return draw_static_frame(display_word)

    img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    for i in range(COLS):
        if target_word[i] == ' ':
            continue
        pool = pools[i]
        speed = speeds[i]

        offset = (t_spin * speed) % (len(pool) * CELL_H)
        idx = int(offset // CELL_H) % len(pool)
        frac = (offset % CELL_H) / CELL_H

        ch_cur = pool[idx]
        ch_next = pool[(idx + 1) % len(pool)]

        y_rel_cur = frac * CELL_H
        y_rel_next = (frac - 1) * CELL_H

        cell_img = Image.new("RGB", (CELL_W, CELL_H), BLACK)
        draw_cell(cell_img, ch_next, y_rel_next, is_letter(ch_next))
        draw_cell(cell_img, ch_cur, y_rel_cur, is_letter(ch_cur))

        x0 = LEFT + i * CELL_W
        img.paste(cell_img, (x0, TOP))
    return np.array(img)

# ---------- Интерфейс Streamlit ----------
st.set_page_config(page_title="Slot Video Generator", layout="wide")
st.title("🎰 Генератор видео с барабаном (финал – первая буква)")

with st.sidebar:
    st.header("Надписи (до 11 символов)")
    word1 = st.text_input("Надпись 1", value="ПРИВЕТ", max_chars=11).ljust(11)[:11]
    word2 = st.text_input("Надпись 2", value="HELLO", max_chars=11).ljust(11)[:11]
    word3 = st.text_input("Надпись 3", value="12345", max_chars=11).ljust(11)[:11]
    word4 = st.text_input("Надпись 4", value="СИМВОЛ", max_chars=11).ljust(11)[:11]

    st.header("Длительности (сек)")
    t1 = st.number_input("Показ 1-й надписи", min_value=0.5, value=2.0, step=0.5)
    t2 = st.number_input("Показ 2-й надписи", min_value=0.5, value=2.0, step=0.5)
    t3 = st.number_input("Показ 3-й надписи", min_value=0.5, value=2.0, step=0.5)
    t4 = st.number_input("Показ 4-й надписи", min_value=0.5, value=2.0, step=0.5)

    generate_btn = st.button("✨ Создать видео", type="primary")

if generate_btn:
    words = [word1, word2, word3, word4]
    durations = [t1, t2, t3, t4]
    alphabet = get_alphabet(words)
    if not alphabet:
        st.error("Нет ни одного символа для вращения (все ячейки пустые).")
        st.stop()

    fps = 30
    total_duration = 2 * (t1 + t2 + t3) + t4

    spin_params = []
    target_words = [word2, word3, word4]
    spin_durations = [t1, t2, t3]
    for dur, tw in zip(spin_durations, target_words):
        pools, speeds = generate_spin_params(tw, alphabet, dur, fps)
        spin_params.append((pools, speeds, tw, dur))

    t0 = t1
    t1_end = t0 + t1
    t2_end = t1_end + t2
    t3_end = t2_end + t2
    t4_end = t3_end + t3
    t5_end = t4_end + t3
    t6_end = t5_end + t4

    def make_frame(t):
        # Статика 1
        if t < t0:
            return draw_static_frame(words[0])

        # Вращение 1 -> word2
        if t < t1_end:
            pools, speeds, tw, dur = spin_params[0]
            t_spin = t - t0
            last = (t >= t1_end - 1.0 / fps)
            return draw_spin_frame(t_spin, pools, speeds, tw, last_frame=last)

        # Статика 2
        if t < t2_end:
            return draw_static_frame(words[1])

        # Вращение 2 -> word3
        if t < t3_end:
            pools, speeds, tw, dur = spin_params[1]
            t_spin = t - t2_end
            last = (t >= t3_end - 1.0 / fps)
            return draw_spin_frame(t_spin, pools, speeds, tw, last_frame=last)

        # Статика 3
        if t < t4_end:
            return draw_static_frame(words[2])

        # Вращение 3 -> word4
        if t < t5_end:
            pools, speeds, tw, dur = spin_params[2]
            t_spin = t - t4_end
            last = (t >= t5_end - 1.0 / fps)
            return draw_spin_frame(t_spin, pools, speeds, tw, last_frame=last)

        # Статика 4 (конец)
        return draw_static_frame(words[3])

    with st.spinner("Генерируем видео с акцентом на первую букву..."):
        clip = mpy.VideoClip(make_frame, duration=total_duration)
        tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        clip.write_videofile(
            tmpfile.name,
            fps=fps,
            codec="libx264",
            audio=False,
            verbose=False,
            logger=None
        )
        clip.close()

    with open(tmpfile.name, "rb") as f:
        video_bytes = f.read()
    os.unlink(tmpfile.name)

    st.success("Видео готово!")
    st.download_button(
        label="📥 Скачать MP4",
        data=video_bytes,
        file_name="slot_first_char_final.mp4",
        mime="video/mp4"
    )
