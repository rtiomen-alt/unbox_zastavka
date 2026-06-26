import streamlit as st
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import moviepy.editor as mpy
import tempfile
import os
import random

# ---------- Настройка шрифта ----------
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

def draw_static_frame(word):
    """Рисует статичный кадр с заданным словом."""
    return draw_frame_from_list(list(word))

def draw_frame_from_list(display_chars):
    """Создаёт кадр по массиву из 11 символов (статичный, без скроллинга)."""
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
            bbox = draw.textbbox((0, 0), ch, font=font, anchor='lt')
            text_w = bbox[2] - bbox[0]
            x = x0 + (CELL_W - text_w) / 2
            draw.text((x, y0), ch, font=font, fill=WHITE, anchor='lt')
        else:
            draw.text((x_center, y_center), ch, font=font, fill=WHITE, anchor='mm')
    return np.array(img)

def generate_spin_params(target_word, alphabet, spin_duration, fps):
    """
    Для каждой позиции создаёт параметры скроллинга:
    - pool: список символов для бесконечной прокрутки
    - speed: пикселей в секунду
    Возвращает списки pools и speeds длиной COLS.
    """
    # Диапазон скоростей: от 2 до 5 полных высот ячейки за время вращения
    v_min = 2 * CELL_H / spin_duration
    v_max = 5 * CELL_H / spin_duration
    pools = []
    speeds = []
    for i in range(COLS):
        if target_word[i] == ' ':
            pools.append([])
            speeds.append(0.0)
            continue

        # Случайный пул длиной 30 из алфавита
        pool = random.choices(alphabet, k=30)
        pools.append(pool)

        # Генерация скорости, не совпадающей с левым соседом (если сосед не пустой)
        for _ in range(100):
            v = random.uniform(v_min, v_max)
            if i > 0 and target_word[i-1] != ' ' and abs(v - speeds[i-1]) < 0.3 * (v_max - v_min):
                continue
            break
        speeds.append(v)
    return pools, speeds

def draw_spin_frame(t_spin, pools, speeds, target_word, last_frame=False):
    """
    Рисует кадр вращения.
    t_spin: время от начала вращения в секундах
    pools, speeds: списки для каждой позиции
    last_frame: если True, рисует целевое слово статично
    """
    if last_frame:
        return draw_frame_from_list(list(target_word))

    img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    draw = ImageDraw.Draw(img)
    for i in range(COLS):
        if target_word[i] == ' ':
            continue
        pool = pools[i]
        speed = speeds[i]
        # Смещение в пикселях
        offset = (t_spin * speed) % (len(pool) * CELL_H)
        idx = int(offset // CELL_H) % len(pool)
        frac = (offset % CELL_H) / CELL_H  # 0..1 доля смещения вниз

        # Символ, уходящий вниз (текущий)
        ch_cur = pool[idx]
        # Следующий символ, появляющийся сверху
        ch_next = pool[(idx + 1) % len(pool)]

        x0 = LEFT + i * CELL_W
        # Позиция по вертикали для текущего символа: верхняя граница смещается вниз на frac*CELL_H
        y_cur = TOP + frac * CELL_H
        # Для следующего символа: верхняя граница на CELL_H выше, т.е. y_next = TOP + (frac - 1) * CELL_H
        y_next = TOP + (frac - 1) * CELL_H

        # Рисуем оба символа (без обрезки, выход за пределы ячейки допустим)
        for ch, y in [(ch_cur, y_cur), (ch_next, y_next)]:
            if is_letter(ch):
                bbox = draw.textbbox((0, 0), ch, font=font, anchor='lt')
                text_w = bbox[2] - bbox[0]
                x = x0 + (CELL_W - text_w) / 2
                draw.text((x, y), ch, font=font, fill=WHITE, anchor='lt')
            else:
                # Для символов центрируем горизонтально и вертикально относительно середины ячейки
                x_center = x0 + CELL_W // 2
                # Вертикально: центр символа должен быть на y + CELL_H/2 ?
                # Так как ячейка фиксирована по верхнему краю, но символы могут быть разной высоты,
                # центрируем относительно середины ячейки (y + CELL_H/2)
                draw.text((x_center, y + CELL_H/2), ch, font=font, fill=WHITE, anchor='mm')
    return np.array(img)

# ---------- Интерфейс Streamlit ----------
st.set_page_config(page_title="Slot Video Generator", layout="wide")
st.title("🎰 Генератор видео с барабаном (скроллинг)")

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
    total = 2 * (t1 + t2 + t3) + t4

    # Заранее готовим параметры скроллинга для трёх фаз вращения
    spin_params = []
    target_words = [word2, word3, word4]
    spin_durations = [t1, t2, t3]
    for dur, tw in zip(spin_durations, target_words):
        pools, speeds = generate_spin_params(tw, alphabet, dur, fps)
        spin_params.append((pools, speeds, tw, dur))

    # Тайминги фаз (секунды)
    t0 = t1
    t1_end = t0 + t1
    t2_end = t1_end + t2
    t3_end = t2_end + t2
    t4_end = t3_end + t3
    t5_end = t4_end + t3
    t6_end = t5_end + t4   # total

    def make_frame(t):
        # Статика 1
        if t < t0:
            return draw_static_frame(words[0])

        # Вращение 1 -> word2
        if t < t1_end:
            pools, speeds, tw, dur = spin_params[0]
            t_spin = t - t0
            last = (t >= t1_end - 1.0 / fps)  # последний кадр фазы
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

    with st.spinner("Генерируем видео с анимацией барабана..."):
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
        file_name="slot_scroll.mp4",
        mime="video/mp4"
    )
