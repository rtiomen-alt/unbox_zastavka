import streamlit as st
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import moviepy.editor as mpy
import tempfile
import os
import random

# ---------- Настройка шрифта ----------
FONT_SIZE = 90
FONT_PATH = "Montserrat-Bold.ttf"  # файл лежит рядом с app.py

if not os.path.exists(FONT_PATH):
    st.error(f"Файл шрифта '{FONT_PATH}' не найден. Добавьте его в репозиторий.")
    st.stop()

try:
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
except IOError:
    st.error("Не удалось загрузить шрифт из локального файла.")
    st.stop()

# ---------- Параметры ячеек и фона ----------
CELL_W, CELL_H = 76, 83          # 20x22 мм при 96 dpi
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

def generate_sequences(target_word, alphabet, base_duration, fps):
    """
    Для каждой позиции создаём список случайных символов.
    Длина списка = N_i (случайное целое), последний символ = target_word[i].
    N_i для соседей различаются.
    """
    total_frames = int(base_duration * fps)
    min_switches = 5
    max_switches = max(min_switches + 1, total_frames // 3)
    N = []
    for i in range(COLS):
        if target_word[i] == ' ':
            N.append(0)
            continue
        while True:
            candidate = random.randint(min_switches, max_switches)
            if i > 0 and target_word[i-1] != ' ' and candidate == N[i-1]:
                continue
            if i < COLS-1 and target_word[i+1] != ' ' and candidate == (N[i-1] if i>0 else None):
                continue
            N.append(candidate)
            break

    sequences = []
    for i in range(COLS):
        if target_word[i] == ' ':
            sequences.append([])
            continue
        seq = [random.choice(alphabet) for _ in range(N[i]-1)]
        seq.append(target_word[i])
        sequences.append(seq)
    return N, sequences

def draw_frame(display_chars):
    """Создаёт кадр (numpy RGB) по массиву символов для 11 ячеек."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    draw = ImageDraw.Draw(img)
    for i, ch in enumerate(display_chars):
        if ch == ' ':
            continue
        x0 = LEFT + i * CELL_W
        y0 = TOP
        x_center = x0 + CELL_W // 2
        y_center = y0 + CELL_H // 2

        if is_letter(ch):
            # Буква: верхнее выравнивание + горизонтальное центрирование
            bbox = draw.textbbox((0, 0), ch, font=font, anchor='lt')
            text_w = bbox[2] - bbox[0]
            x = x0 + (CELL_W - text_w) / 2
            draw.text((x, y0), ch, font=font, fill=WHITE, anchor='lt')
        else:
            # Символы и цифры: полное центрирование
            draw.text((x_center, y_center), ch, font=font, fill=WHITE, anchor='mm')
    return np.array(img)

# ---------- Интерфейс Streamlit ----------
st.set_page_config(page_title="Slot Video Generator", layout="wide")
st.title("🎰 Генератор видео с барабаном")

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
    total = 2*(t1 + t2 + t3) + t4

    spin_data = []
    target_words = [word2, word3, word4]
    spin_durations = [t1, t2, t3]
    for dur, tw in zip(spin_durations, target_words):
        N, seq = generate_sequences(tw, alphabet, dur, fps)
        spin_data.append((dur, tw, N, seq))

    t0 = t1
    t1_end = t0 + t1
    t2_end = t1_end + t2
    t3_end = t2_end + t2
    t4_end = t3_end + t3
    t5_end = t4_end + t3
    t6_end = t5_end + t4

    def make_frame(t):
        if t < t0:
            return draw_frame(list(words[0]))
        elif t < t1_end:
            spin_idx = 0
            t_spin = t - t0
        elif t < t2_end:
            return draw_frame(list(words[1]))
        elif t < t3_end:
            spin_idx = 1
            t_spin = t - t2_end
        elif t < t4_end:
            return draw_frame(list(words[2]))
        elif t < t5_end:
            spin_idx = 2
            t_spin = t - t4_end
        else:
            return draw_frame(list(words[3]))

        dur, target, N_list, sequences = spin_data[spin_idx]
        display = []
        for i in range(COLS):
            if target[i] == ' ':
                display.append(' ')
            else:
                seq = sequences[i]
                n = N_list[i]
                idx = min(int(t_spin * fps / (dur * fps) * n), n - 1) if n > 0 else 0
                display.append(seq[idx])
        return draw_frame(display)

    with st.spinner("Генерируем видео... Пожалуйста, подождите."):
        clip = mpy.VideoClip(make_frame, duration=total)
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
        file_name="slot_video.mp4",
        mime="video/mp4"
    )
