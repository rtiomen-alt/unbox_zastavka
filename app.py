import streamlit as st
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import moviepy.editor as mpy
import tempfile
import os
import random
import glob

# ---------- Автоподбор шрифтов из корня репозитория ----------
def get_available_fonts():
    ttf_files = glob.glob("*.ttf")
    fonts = {}
    for path in ttf_files:
        name = os.path.basename(path)
        fonts[name] = path
    if not fonts:
        st.error("Не найдено ни одного .ttf шрифта в корне репозитория.")
        st.stop()
    return fonts

available_fonts = get_available_fonts()

# Инициализация выбранного шрифта в session_state
if "selected_font" not in st.session_state:
    st.session_state.selected_font = list(available_fonts.keys())[0]

FONT_PATH = available_fonts[st.session_state.selected_font]
FONT_SIZE = 90

try:
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
except IOError:
    st.error(f"Не удалось загрузить шрифт {FONT_PATH}.")
    st.stop()

# ---------- Параметры ячеек и фона ----------
CELL_W, CELL_H = 76, 83          # 20×22 мм при 96 dpi
COLS = 11
WIDTH, HEIGHT = 1920, 1080
LEFT = (WIDTH - COLS * CELL_W) // 2
TOP = (HEIGHT - CELL_H) // 2

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# ---------- Session state для 6 слотов изображений ----------
if "img_slots" not in st.session_state:
    st.session_state.img_slots = [
        {"file": None, "word_idx": 0, "cell_idx": 0, "scale": 1.0, "offset_x": 0, "offset_y": 0}
        for _ in range(6)
    ]

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

def draw_image_on_cell(cell_img, pil_img, scale, offset_x, offset_y):
    """Рисует PIL-изображение на cell_img с учётом масштаба и смещения."""
    if pil_img is None:
        return
    img_w, img_h = pil_img.size
    avail_w = CELL_W * scale
    avail_h = CELL_H * scale
    ratio = min(avail_w / img_w, avail_h / img_h)
    new_w = int(img_w * ratio)
    new_h = int(img_h * ratio)
    resized = pil_img.resize((new_w, new_h), Image.LANCZOS)
    x = (CELL_W - new_w) // 2 + offset_x
    y = (CELL_H - new_h) // 2 + offset_y
    if resized.mode == 'RGBA':
        cell_img.paste(resized, (x, y), resized)
    else:
        cell_img.paste(resized, (x, y))

# ---------- Универсальная отрисовка кадра по списку символов ----------
def draw_frame_from_list(display_chars, image_map=None, word_idx=None):
    """Рисует кадр. Если image_map передан, показывает изображения в соответствующих ячейках."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    for i, ch in enumerate(display_chars):
        x0 = LEFT + i * CELL_W
        if image_map is not None and (word_idx, i) in image_map:
            cell_img = Image.new("RGB", (CELL_W, CELL_H), BLACK)
            pil_img, scale, off_x, off_y = image_map[(word_idx, i)]
            draw_image_on_cell(cell_img, pil_img, scale, off_x, off_y)
        else:
            if ch == ' ':
                continue
            cell_img = Image.new("RGB", (CELL_W, CELL_H), BLACK)
            draw_cell(cell_img, ch, y_rel=0, is_letter_char=is_letter(ch))
        img.paste(cell_img, (x0, TOP))
    return np.array(img)

# Удобная обёртка для статического слова
def draw_static_frame(word, word_idx, image_map):
    return draw_frame_from_list(list(word), image_map, word_idx)

# ---------- Генерация параметров для режима «барабан» (скроллинг) ----------
def generate_spin_params(target_word, alphabet, spin_duration, fps, image_map, tw_idx):
    v_min = 2 * CELL_H / spin_duration
    v_max = 5 * CELL_H / spin_duration
    pools = []
    speeds = []
    for i in range(COLS):
        if (tw_idx, i) in image_map or target_word[i] == ' ':
            pools.append([])
            speeds.append(0.0)
            continue
        pool = random.choices(alphabet, k=30)
        pools.append(pool)
        for _ in range(100):
            v = random.uniform(v_min, v_max)
            if i > 0 and target_word[i-1] != ' ' and (tw_idx, i-1) not in image_map:
                if abs(v - speeds[i-1]) < 0.3 * (v_max - v_min):
                    continue
            break
        speeds.append(v)
    return pools, speeds

def draw_spin_frame(t_spin, pools, speeds, target_word, last_frame=False,
                    target_word_idx=None, image_map=None):
    if last_frame:
        return draw_static_frame(target_word, target_word_idx, image_map)

    img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    for i in range(COLS):
        if (target_word_idx, i) in image_map or target_word[i] == ' ':
            continue
        pool = pools[i]
        speed = speeds[i]
        if not pool:
            continue

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

# ---------- Генерация параметров для режима «смена» (простая замена символов) ----------
def generate_switch_sequences(target_word, alphabet, base_duration, fps, image_map, tw_idx):
    total_frames = int(base_duration * fps)
    min_switches = 5
    max_switches = max(min_switches + 1, total_frames // 3)
    N = []
    sequences = []
    for i in range(COLS):
        if (tw_idx, i) in image_map or target_word[i] == ' ':
            sequences.append([])
            N.append(0)
            continue
        while True:
            candidate = random.randint(min_switches, max_switches)
            if i > 0 and target_word[i-1] != ' ' and (tw_idx, i-1) not in image_map:
                if candidate == N[i-1]:
                    continue
            break
        N.append(candidate)
        seq = [random.choice(alphabet) for _ in range(candidate - 1)]
        seq.append(target_word[i])
        sequences.append(seq)
    return N, sequences

def draw_switch_frame(t_spin, sequences, N_list, target_word, last_frame,
                      target_word_idx, image_map, spin_duration, fps):
    if last_frame:
        return draw_static_frame(target_word, target_word_idx, image_map)
    display_chars = []
    for i in range(COLS):
        if (target_word_idx, i) in image_map:
            display_chars.append(' ')   # чёрная ячейка
        elif target_word[i] == ' ':
            display_chars.append(' ')
        else:
            n = N_list[i]
            if n == 0:
                display_chars.append(target_word[i])
            else:
                idx = int(t_spin * fps * n / (spin_duration * fps))
                idx = min(idx, n - 1)
                display_chars.append(sequences[i][idx])
    return draw_frame_from_list(display_chars)

# ---------- Превью для настройки изображения ----------
def generate_preview(word, cell_idx, pil_img, scale, off_x, off_y):
    """Создаёт миниатюру 3 ячейки: левый сосед, центральная (с картинкой), правый сосед."""
    preview = Image.new("RGB", (3 * CELL_W, CELL_H), BLACK)
    # Левая ячейка
    left_idx = cell_idx - 1
    if 0 <= left_idx < COLS and word[left_idx] != ' ':
        cell_img = Image.new("RGB", (CELL_W, CELL_H), BLACK)
        draw_cell(cell_img, word[left_idx], y_rel=0, is_letter(word[left_idx]))
        preview.paste(cell_img, (0, 0))
    # Центральная ячейка
    cell_img = Image.new("RGB", (CELL_W, CELL_H), BLACK)
    if pil_img is not None:
        draw_image_on_cell(cell_img, pil_img, scale, off_x, off_y)
    elif cell_idx < COLS and word[cell_idx] != ' ':
        draw_cell(cell_img, word[cell_idx], y_rel=0, is_letter(word[cell_idx]))
    preview.paste(cell_img, (CELL_W, 0))
    # Правая ячейка
    right_idx = cell_idx + 1
    if 0 <= right_idx < COLS and word[right_idx] != ' ':
        cell_img = Image.new("RGB", (CELL_W, CELL_H), BLACK)
        draw_cell(cell_img, word[right_idx], y_rel=0, is_letter(word[right_idx]))
        preview.paste(cell_img, (2 * CELL_W, 0))
    return preview

# ---------- Интерфейс Streamlit ----------
st.set_page_config(page_title="Slot Video Generator", layout="wide")
st.title("🎰 Генератор видео с барабаном")

with st.sidebar:
    # Выбор шрифта
    font_names = list(available_fonts.keys())
    selected_font_name = st.selectbox(
        "Шрифт",
        font_names,
        index=font_names.index(st.session_state.selected_font)
    )
    st.session_state.selected_font = selected_font_name

    # Выбор режима вращения
    mode = st.selectbox("Режим вращения", ["барабан", "смена"], index=0)

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

    # Изображения
    with st.expander("🖼️ Изображения в ячейках (до 6)"):
        # Подготовка текущих слов для превью
        words_ui = [word1, word2, word3, word4]
        for slot in range(6):
            st.markdown(f"**Слот {slot+1}**")
            uploaded = st.file_uploader(
                "PNG изображение",
                type=["png"],
                key=f"img_uploader_{slot}",
                help="Загрузите PNG (с прозрачностью или без)"
            )
            if uploaded is not None:
                st.session_state.img_slots[slot]["file"] = Image.open(uploaded).convert("RGBA")
            else:
                st.session_state.img_slots[slot]["file"] = None

            col1, col2 = st.columns(2)
            with col1:
                word_choice = st.selectbox(
                    "Надпись",
                    options=[1, 2, 3, 4],
                    index=st.session_state.img_slots[slot]["word_idx"],
                    key=f"img_word_{slot}"
                )
                cell_choice = st.number_input(
                    "Ячейка (1–11)",
                    min_value=1, max_value=11,
                    value=st.session_state.img_slots[slot]["cell_idx"] + 1,
                    key=f"img_cell_{slot}"
                ) - 1
            with col2:
                scale = st.slider(
                    "Масштаб",
                    min_value=0.3, max_value=2.5,
                    value=st.session_state.img_slots[slot]["scale"],
                    step=0.1, key=f"img_scale_{slot}"
                )
                off_x = st.slider(
                    "Смещение X (px)",
                    min_value=-20, max_value=20,
                    value=st.session_state.img_slots[slot]["offset_x"],
                    step=1, key=f"img_offx_{slot}"
                )
                off_y = st.slider(
                    "Смещение Y (px)",
                    min_value=-20, max_value=20,
                    value=st.session_state.img_slots[slot]["offset_y"],
                    step=1, key=f"img_offy_{slot}"
                )

            # Обновляем session_state
            st.session_state.img_slots[slot]["word_idx"] = word_choice - 1
            st.session_state.img_slots[slot]["cell_idx"] = cell_choice
            st.session_state.img_slots[slot]["scale"] = scale
            st.session_state.img_slots[slot]["offset_x"] = off_x
            st.session_state.img_slots[slot]["offset_y"] = off_y

            # Превью
            pil_img = st.session_state.img_slots[slot]["file"]
            word_for_preview = words_ui[word_choice - 1]  # слово, к которому привязан слот
            preview_img = generate_preview(
                word_for_preview,
                cell_choice,
                pil_img,
                scale, off_x, off_y
            )
            # Увеличиваем для наглядности в 3 раза
            preview_img = preview_img.resize((3 * CELL_W * 2, CELL_H * 2), Image.NEAREST)
            st.image(preview_img, caption=f"Предпросмотр: {word_for_preview} (ячейка {cell_choice+1})", width=3*CELL_W*2)

    generate_btn = st.button("✨ Создать видео", type="primary")

if generate_btn:
    words = [word1, word2, word3, word4]
    durations = [t1, t2, t3, t4]
    alphabet = get_alphabet(words)
    if not alphabet:
        st.error("Нет ни одного символа для вращения (все ячейки пустые).")
        st.stop()

    # Собираем карту изображений
    image_map = {}
    for slot in st.session_state.img_slots:
        if slot["file"] is not None:
            key = (slot["word_idx"], slot["cell_idx"])
            image_map[key] = (slot["file"], slot["scale"], slot["offset_x"], slot["offset_y"])

    fps = 30
    total_duration = 2 * (t1 + t2 + t3) + t4

    # Параметры для трёх фаз вращения
    spin_params = []
    target_words = [word2, word3, word4]
    target_indices = [1, 2, 3]
    spin_durations = [t1, t2, t3]
    for dur, tw, tw_idx in zip(spin_durations, target_words, target_indices):
        if mode == "барабан":
            pools, speeds = generate_spin_params(tw, alphabet, dur, fps, image_map, tw_idx)
            spin_params.append(("scroll", pools, speeds, tw, dur, tw_idx))
        else:  # "смена"
            N, seqs = generate_switch_sequences(tw, alphabet, dur, fps, image_map, tw_idx)
            spin_params.append(("switch", N, seqs, tw, dur, tw_idx))

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
            return draw_static_frame(words[0], 0, image_map)

        # Вращение 1 -> word2
        if t < t1_end:
            entry = spin_params[0]
            t_spin = t - t0
            last = (t >= t1_end - 1.0 / fps)
            if entry[0] == "scroll":
                _, pools, speeds, tw, dur, tw_idx = entry
                return draw_spin_frame(t_spin, pools, speeds, tw, last, tw_idx, image_map)
            else:
                _, N, seqs, tw, dur, tw_idx = entry
                return draw_switch_frame(t_spin, seqs, N, tw, last, tw_idx, image_map, dur, fps)

        # Статика 2
        if t < t2_end:
            return draw_static_frame(words[1], 1, image_map)

        # Вращение 2 -> word3
        if t < t3_end:
            entry = spin_params[1]
            t_spin = t - t2_end
            last = (t >= t3_end - 1.0 / fps)
            if entry[0] == "scroll":
                _, pools, speeds, tw, dur, tw_idx = entry
                return draw_spin_frame(t_spin, pools, speeds, tw, last, tw_idx, image_map)
            else:
                _, N, seqs, tw, dur, tw_idx = entry
                return draw_switch_frame(t_spin, seqs, N, tw, last, tw_idx, image_map, dur, fps)

        # Статика 3
        if t < t4_end:
            return draw_static_frame(words[2], 2, image_map)

        # Вращение 3 -> word4
        if t < t5_end:
            entry = spin_params[2]
            t_spin = t - t4_end
            last = (t >= t5_end - 1.0 / fps)
            if entry[0] == "scroll":
                _, pools, speeds, tw, dur, tw_idx = entry
                return draw_spin_frame(t_spin, pools, speeds, tw, last, tw_idx, image_map)
            else:
                _, N, seqs, tw, dur, tw_idx = entry
                return draw_switch_frame(t_spin, seqs, N, tw, last, tw_idx, image_map, dur, fps)

        # Статика 4 (конец)
        return draw_static_frame(words[3], 3, image_map)

    with st.spinner("Генерируем видео..."):
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
        file_name="slot_video.mp4",
        mime="video/mp4"
    )
