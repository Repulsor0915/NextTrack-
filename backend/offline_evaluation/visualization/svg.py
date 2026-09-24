"""Small reusable SVG primitives for dependency-free report figures."""

from __future__ import annotations

from html import escape


BACKGROUND = "#ffffff"
TEXT = "#17314a"
GRID = "#d9e1e8"
COLORS = {
    "primary": "#2864a7",
    "secondary": "#c77720",
    "tertiary": "#16817c",
    "quaternary": "#8656a7",
}


def grouped_bar_chart(
    *, title: str, subtitle: str, rows: list[dict], series: list[tuple[str, str]],
    maximum: float | None = None, value_suffix: str = "",
) -> str:
    """Render labelled horizontal bars from already summarized values."""

    width = 1080
    label_width = 300
    plot_width = 700
    row_height = max(34, 18 * len(series) + 12)
    height = 125 + row_height * len(rows) + 45
    values = [
        float(row[key])
        for row in rows
        for key, _color in series
        if row.get(key) is not None
    ]
    scale_max = maximum if maximum is not None else (max(values) if values else 1.0)
    scale_max = scale_max or 1.0
    parts = [
        f'<rect width="{width}" height="{height}" fill="{BACKGROUND}"/>',
        f'<text x="40" y="44" font-size="25" font-weight="700" fill="{TEXT}">{escape(title)}</text>',
        f'<text x="40" y="72" font-size="14" fill="{TEXT}">{escape(subtitle)}</text>',
    ]
    for index, row in enumerate(rows):
        y = 105 + index * row_height
        parts.append(
            f'<text x="{label_width - 12}" y="{y + 14}" text-anchor="end" '
            f'font-size="13" fill="{TEXT}">{escape(str(row["label"]))}</text>'
        )
        parts.append(
            f'<line x1="{label_width}" y1="{y + row_height - 4}" '
            f'x2="{label_width + plot_width}" y2="{y + row_height - 4}" stroke="{GRID}"/>'
        )
        for series_index, (key, color) in enumerate(series):
            value = row.get(key)
            if value is None:
                continue
            bar_y = y + series_index * 18
            bar_width = max(0.0, min(plot_width, float(value) / scale_max * plot_width))
            parts.append(
                f'<rect x="{label_width}" y="{bar_y}" width="{bar_width:.2f}" '
                f'height="13" rx="2" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{min(label_width + bar_width + 6, width - 65):.2f}" '
                f'y="{bar_y + 11}" font-size="11" fill="{TEXT}">'
                f'{float(value):.3f}{escape(value_suffix)}</text>'
            )
    legend_x = 40
    legend_y = height - 20
    for key, color in series:
        parts.append(
            f'<rect x="{legend_x}" y="{legend_y - 11}" width="12" height="12" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{legend_x + 18}" y="{legend_y}" font-size="12" fill="{TEXT}">{escape(key)}</text>'
        )
        legend_x += 175
    description = escape(subtitle)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">'
        f'<title id="title">{escape(title)}</title>'
        f'<desc id="description">{description}</desc>'
        + "".join(parts)
        + "</svg>\n"
    )
