"""Generate realistic, high-fidelity Catppuccin Mocha terminal GIF demo for Angrist."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Colors (Catppuccin Mocha palette)
BG_COLOR = (30, 30, 46)          # #1e1e2e Base
BAR_COLOR = (24, 24, 37)         # #181825 Mantle
TEXT_COLOR = (205, 214, 244)     # #cdd6f4 Text
PROMPT_COLOR = (137, 180, 250)   # #89b4fa Blue
DIM_COLOR = (108, 112, 134)      # #6c7086 Overlay0
GREEN_COLOR = (166, 227, 161)    # #a6e3a1 Green
RED_COLOR = (243, 139, 168)      # #f38ba8 Red
YELLOW_COLOR = (249, 226, 175)   # #f9e2af Yellow
CYAN_COLOR = (148, 226, 213)     # #94e2d5 Teal
PEACH_COLOR = (250, 179, 135)    # #fab387 Peach
CURSOR_COLOR = (245, 224, 220)   # #f5e0dc Rosewater

BTN_RED = (243, 139, 168)
BTN_YELLOW = (249, 226, 175)
BTN_GREEN = (166, 227, 161)

WIDTH = 980
HEIGHT = 560
PADDING = 24
TOP_BAR_HEIGHT = 38
LINE_HEIGHT = 22

FONT_PATH = "C:/Windows/Fonts/CascadiaMono.ttf"
if not os.path.exists(FONT_PATH):
    FONT_PATH = "C:/Windows/Fonts/consola.ttf"

FONT_SIZE = 14
FONT = ImageFont.truetype(FONT_PATH, FONT_SIZE)
FONT_BOLD = ImageFont.truetype(FONT_PATH, FONT_SIZE)


def draw_window_frame(title: str = "angrist - terminal") -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Title Bar
    draw.rectangle([(0, 0), (WIDTH, TOP_BAR_HEIGHT)], fill=BAR_COLOR)
    draw.line([(0, TOP_BAR_HEIGHT), (WIDTH, TOP_BAR_HEIGHT)], fill=(49, 50, 68), width=1)

    # Window buttons
    draw.ellipse([(16, 13), (28, 25)], fill=BTN_RED)
    draw.ellipse([(36, 13), (48, 25)], fill=BTN_YELLOW)
    draw.ellipse([(56, 13), (68, 25)], fill=BTN_GREEN)

    # Title text
    bbox = draw.textbbox((0, 0), title, font=FONT)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, 11), title, font=FONT, fill=DIM_COLOR)

    return img


def render_terminal(lines: list[list[tuple[str, tuple[int, int, int]]]], cursor: bool = False) -> Image.Image:
    base = draw_window_frame()
    draw = ImageDraw.Draw(base)

    y = TOP_BAR_HEIGHT + 16
    for line_segments in lines:
        x = PADDING
        for text, color in line_segments:
            draw.text((x, y), text, font=FONT, fill=color)
            bbox = draw.textbbox((x, y), text, font=FONT)
            x = bbox[2]
        y += LINE_HEIGHT

    if cursor:
        # Draw block cursor at end of last line
        last_line = lines[-1] if lines else []
        x = PADDING
        for text, _ in last_line:
            bbox = draw.textbbox((x, y - LINE_HEIGHT), text, font=FONT)
            x = bbox[2]
        draw.rectangle([(x + 2, y - LINE_HEIGHT + 3), (x + 10, y - LINE_HEIGHT + FONT_SIZE + 3)], fill=CURSOR_COLOR)

    return base


def generate_demo():
    frames = []
    durations = []

    # Command 1 to type
    cmd1 = "angrist fix --file demo/payment_processor.py --target PaymentProcessor.settle_batch"
    
    # Typing cmd1
    for i in range(0, len(cmd1) + 1, 3):
        typed = cmd1[:i]
        lines = [
            [("felix@dev", GREEN_COLOR), (":", DIM_COLOR), ("~/angrist", CYAN_COLOR), ("$ ", PROMPT_COLOR), (typed, TEXT_COLOR)]
        ]
        frames.append(render_terminal(lines, cursor=True))
        durations.append(40)

    # Execute fix
    fix_output = [
        [("felix@dev", GREEN_COLOR), (":", DIM_COLOR), ("~/angrist", CYAN_COLOR), ("$ ", PROMPT_COLOR), (cmd1, TEXT_COLOR)],
        [("Tree-sitter: ", CYAN_COLOR), ("Target 'PaymentProcessor.settle_batch' locked (lines 80-115)", TEXT_COLOR)],
        [("Git Sandbox: ", CYAN_COLOR), ("Created isolated worktree 'angrist-sandbox-8a12c4'", DIM_COLOR)],
        [("Baseline:    ", PEACH_COLOR), ("pytest demo/test_payment_processor.py -> 1 FAILED (captured)", YELLOW_COLOR)],
        [("Patcher:     ", CYAN_COLOR), ("Synthesizing fix via gpt-oss-120b...", DIM_COLOR)],
        [("AST Gate:    ", GREEN_COLOR), ("100% target containment verified (0 sibling lines modified)", GREEN_COLOR)],
        [("Lint Gate:   ", GREEN_COLOR), ("ruff check -> clean (0 new errors)", GREEN_COLOR)],
        [("Test Gate:   ", GREEN_COLOR), ("pytest demo/test_payment_processor.py -> 3 PASSED (0 regressions)", GREEN_COLOR)],
        [("Success:     ", GREEN_COLOR), ("Verified patch safely committed on branch 'angrist-sandbox-8a12c4'", TEXT_COLOR)],
    ]

    for step in range(2, len(fix_output) + 1):
        frames.append(render_terminal(fix_output[:step], cursor=(step == len(fix_output))))
        durations.append(350 if step < len(fix_output) else 1500)

    # Command 2: angrist benchmark
    bench_prefix = list(fix_output)
    bench_prefix.append([])
    cmd2 = "angrist benchmark"
    for i in range(0, len(cmd2) + 1, 2):
        typed = cmd2[:i]
        curr = list(bench_prefix)
        curr[-1] = [("felix@dev", GREEN_COLOR), (":", DIM_COLOR), ("~/angrist", CYAN_COLOR), ("$ ", PROMPT_COLOR), (typed, TEXT_COLOR)]
        frames.append(render_terminal(curr, cursor=True))
        durations.append(45)

    # Benchmark Results Table (Compact & Elegant)
    bench_table = [
        [("felix@dev", GREEN_COLOR), (":", DIM_COLOR), ("~/angrist", CYAN_COLOR), ("$ ", PROMPT_COLOR), (cmd2, TEXT_COLOR)],
        [("SWE-bench Lite Evaluation (10-Instance Curated Suite):", CYAN_COLOR)],
        [("-" * 72, DIM_COLOR)],
        [("Instance ID                     Target Function        Status   Duration", DIM_COLOR)],
        [("-" * 72, DIM_COLOR)],
        [("psf__requests-1142              prepare_url            ", TEXT_COLOR), ("PASS", GREEN_COLOR), ("     2.52s", DIM_COLOR)],
        [("marshmallow__marshmallow-1343   Schema._do_load        ", TEXT_COLOR), ("PASS", GREEN_COLOR), ("     2.50s", DIM_COLOR)],
        [("pallets__flask-4045             Blueprint.add_url_rule ", TEXT_COLOR), ("PASS", GREEN_COLOR), ("     2.52s", DIM_COLOR)],
        [("django__django-11099            ASCIIUsernameValidator ", TEXT_COLOR), ("PASS", GREEN_COLOR), ("     2.00s", DIM_COLOR)],
        [("pallets__flask-4992             Config.from_file       ", TEXT_COLOR), ("PASS", GREEN_COLOR), ("     2.42s", DIM_COLOR)],
        [("pylint-dev__pylint-5859         EncodingChecker.open   ", TEXT_COLOR), ("PASS", GREEN_COLOR), ("     1.99s", DIM_COLOR)],
        [("pytest-dev__pytest-11148        import_path            ", TEXT_COLOR), ("FAIL", RED_COLOR),   ("     2.43s", DIM_COLOR)],
        [("django__django-11049            DurationField.get_msg  ", TEXT_COLOR), ("PASS", GREEN_COLOR), ("     2.58s", DIM_COLOR)],
        [("sphinx-doc__sphinx-10325        inherited_members_opt  ", TEXT_COLOR), ("PASS", GREEN_COLOR), ("     2.53s", DIM_COLOR)],
        [("psf__requests-1963              resolve_redirect_method", TEXT_COLOR), ("PASS", GREEN_COLOR), ("  1.98s", DIM_COLOR)],
        [("-" * 72, DIM_COLOR)],
        [("Pass Rate: 9/10 (90.0%) | Zero Worktree Leaks | 100% AST Invariance", GREEN_COLOR)],
    ]

    for step in range(2, len(bench_table) + 1):
        frames.append(render_terminal(bench_table[:step], cursor=(step == len(bench_table))))
        durations.append(120 if step < len(bench_table) else 4000)

    out_path = Path("demo/demo.gif")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save optimized animated GIF
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"Demo GIF saved to {out_path} ({len(frames)} frames)")


if __name__ == "__main__":
    generate_demo()
