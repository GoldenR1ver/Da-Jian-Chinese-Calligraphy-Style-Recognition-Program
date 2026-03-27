"""八维书法雷达图（Matplotlib）。"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from matplotlib.font_manager import FontProperties

from .style_math import EIGHT_DIMENSION_KEYS, EIGHT_DIMENSION_ZH


def render_eight_dim_radar(
    user_eight: dict[str, float],
    out_path: Path,
    *,
    title: str = "我的书法八维",
    max_value: float = 100.0,
) -> Path:
    """
    user_eight: 键为 zhonghe, duanzhuang, ... yanmei，值为 0–100。
    返回写入的文件路径。
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Set CJK-capable font on Windows for Chinese labels.
    try:
        font_path = "C:/Windows/Fonts/simhei.ttf"
        if os.path.exists(font_path):
            custom_font = FontProperties(fname=font_path)
            plt.rcParams["font.family"] = custom_font.get_name()
        else:
            plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "Microsoft YaHei"]
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        print("字体设置失败，可能需要手动安装中文字体")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    labels = [EIGHT_DIMENSION_ZH[k] for k in EIGHT_DIMENSION_KEYS]
    values = [float(user_eight.get(k, 0.0)) for k in EIGHT_DIMENSION_KEYS]
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    values_closed = np.concatenate([values, [values[0]]])
    angles_closed = np.concatenate([angles, [angles[0]]])

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(projection="polar"))
    ax.plot(angles_closed, values_closed, "o-", linewidth=2, color="#2c5aa0")
    ax.fill(angles_closed, values_closed, alpha=0.25, color="#2c5aa0")
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, max_value)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_title(title, fontsize=14, pad=20)
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path.resolve()


# 兼容旧名
render_six_dim_radar = render_eight_dim_radar
