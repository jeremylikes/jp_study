import csv
import os
import subprocess
import sys
from pathlib import Path

# -----------------------
# CONFIG (edit if needed)
# -----------------------
ROOT = Path(r"C:\jpvideo")
CSV_PATH = ROOT / "cards.tsv"
OUT_DIR = ROOT / "out"
TMP_DIR = ROOT / "tmp"

FONT_PATH = r"C:\Windows\Fonts\NotoSansJP-VF.ttf"

# Video settings
WIDTH, HEIGHT = 1920, 1080
FPS = 30
BG_COLOR = "#111111"

# Timing (seconds)
WORD_S = 5          # Word displays for 5 seconds
PAUSE1_S = 0        # No pause - transitions directly to info
INFO_S = 10         # Reading and examples display for 10 seconds
PAUSE2_S = 0        # No pause - transitions directly to next card
TOTAL_S = WORD_S + PAUSE1_S + INFO_S + PAUSE2_S

# Text layout
WORD_SIZE = 180
READING_SIZE = 92
JP_EX_SIZE = 96
EN_EX_SIZE = 50

# Text wrapping - maximum width for text (leaves margins on sides)
TEXT_MAX_WIDTH = 1600  # pixels (out of 1920 total width)

# Y positions (pixels) for info slide - adjusted to accommodate wrapped text
READING_Y = 240
JP_EX_Y = 380
EN_EX_Y = 540

# Line spacing for wrapped text (pixels between lines)
LINE_SPACING = 15

# -----------------------
# Helpers
# -----------------------
def ensure_dirs():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

def run(cmd: list[str]):
    # Print the command for visibility/debug
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

def ffmpeg_exists():
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        print("ERROR: ffmpeg not found on PATH. Install ffmpeg and add its bin folder to PATH.")
        sys.exit(1)

def write_textfile(path: Path, text: str):
    # UTF-8 w/ LF is usually safest for FFmpeg drawtext on Windows
    path.write_text(text if text is not None else "", encoding="utf-8", newline="\n")

def wrap_text_for_display(text: str, max_width_px: int, font_size: int) -> str:
    """
    Manually wrap text to fit within max_width_px pixels.
    Rough estimation: assume average character width is ~0.7 * font_size
    """
    if not text:
        return text
    
    # Rough estimate: average char width is about 0.7 * font_size
    # For Japanese characters, they're typically square, so font_size is a good approximation
    chars_per_line = max(1, int(max_width_px / (font_size * 0.8)))
    
    words = text.split()
    if not words:
        return text
    
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        # For Japanese, count characters more accurately
        word_length = len(word) + (1 if current_line else 0)  # +1 for space if not first word
        if current_length + word_length <= chars_per_line:
            current_line.append(word)
            current_length += word_length
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)
    
    if current_line:
        lines.append(" ".join(current_line))
    
    return "\n".join(lines)  # Actual newlines - FFmpeg textfile reads them as line breaks

def make_clip(idx: int, word: str, reading: str, example_jp: str, example_en: str):
    # Create per-card textfiles (avoids escaping issues)
    word_txt = TMP_DIR / f"{idx:04d}_word.txt"
    reading_txt = TMP_DIR / f"{idx:04d}_reading.txt"
    jp_txt = TMP_DIR / f"{idx:04d}_jp.txt"
    en_txt = TMP_DIR / f"{idx:04d}_en.txt"

    write_textfile(word_txt, word.strip())
    # Wrap text to prevent overflow - use box width for wrapping calculation
    write_textfile(reading_txt, wrap_text_for_display(reading.strip(), TEXT_MAX_WIDTH, READING_SIZE))
    write_textfile(jp_txt, wrap_text_for_display(example_jp.strip(), TEXT_MAX_WIDTH, JP_EX_SIZE))
    write_textfile(en_txt, wrap_text_for_display(example_en.strip(), TEXT_MAX_WIDTH, EN_EX_SIZE))

    out_mp4 = OUT_DIR / f"{idx:04d}.mp4"

    # Enable windows:
    # - word visible from t=0..WORD_S
    # - info visible from t=(WORD_S+PAUSE1_S) .. (WORD_S+PAUSE1_S+INFO_S)
    info_start = WORD_S + PAUSE1_S
    info_end = info_start + INFO_S

    # Convert Windows paths to format FFmpeg can handle
    # Use forward slashes and escape colon with backslash
    def escape_path(p: Path) -> str:
        path_str = str(p).replace("\\", "/")
        # Escape colon in drive letter for FFmpeg filter syntax
        if path_str[1:2] == ":":
            path_str = path_str[0] + "\\:" + path_str[2:]
        return path_str

    font_escaped = escape_path(Path(FONT_PATH))
    word_escaped = escape_path(word_txt)
    reading_escaped = escape_path(reading_txt)
    jp_escaped = escape_path(jp_txt)
    en_escaped = escape_path(en_txt)

    # Build filter string - use single quotes around paths to help FFmpeg parse
    # Text is pre-wrapped in Python to prevent overflow
    vf = (
        f"drawtext=fontfile='{font_escaped}':textfile='{word_escaped}':fontsize={WORD_SIZE}:fontcolor=white:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,{WORD_S})',"
        f"drawtext=fontfile='{font_escaped}':textfile='{reading_escaped}':fontsize={READING_SIZE}:fontcolor=white:"
        f"x=(w-text_w)/2:y={READING_Y}:enable='between(t,{info_start},{info_end})',"
        f"drawtext=fontfile='{font_escaped}':textfile='{jp_escaped}':fontsize={JP_EX_SIZE}:fontcolor=white:"
        f"x=(w-text_w)/2:y={JP_EX_Y}:enable='between(t,{info_start},{info_end})',"
        f"drawtext=fontfile='{font_escaped}':textfile='{en_escaped}':fontsize={EN_EX_SIZE}:fontcolor=white@0.92:"
        f"x=(w-text_w)/2:y={EN_EX_Y}:enable='between(t,{info_start},{info_end})'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={BG_COLOR}:s={WIDTH}x{HEIGHT}:r={FPS}:d={TOTAL_S}",
        "-vf", vf,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        str(out_mp4)
    ]
    run(cmd)

def concat_all(num_clips: int):
    concat_path = OUT_DIR / "concat.txt"
    lines = [f"file '{i:04d}.mp4'\n" for i in range(1, num_clips + 1)]
    concat_path.write_text("".join(lines), encoding="utf-8", newline="\n")

    final_mp4 = OUT_DIR / "jp_vocab_video.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_path),
        "-c", "copy",
        str(final_mp4)
    ]
    run(cmd)
    print(f"\nDONE: {final_mp4}")

def main():
    ffmpeg_exists()
    ensure_dirs()

    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}")
        sys.exit(1)

    # Your CSV: tab-delimited with fields:
    # word    reading    example_jp    example_en
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        required = {"word", "reading", "example_jp", "example_en"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            print("ERROR: CSV headers must be exactly: word<TAB>reading<TAB>example_jp<TAB>example_en")
            print(f"Found headers: {reader.fieldnames}")
            sys.exit(1)

        rows = list(reader)

    if not rows:
        print("ERROR: CSV has no rows.")
        sys.exit(1)

    print(f"Rendering {len(rows)} clips...")
    for idx, row in enumerate(rows, start=1):
        make_clip(
            idx,
            row.get("word", ""),
            row.get("reading", ""),
            row.get("example_jp", ""),
            row.get("example_en", "")
        )

    print("\nConcatenating...")
    concat_all(len(rows))

if __name__ == "__main__":
    main()
