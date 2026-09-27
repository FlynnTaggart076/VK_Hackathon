"""Bounded raster previews produced by the worker from closed source bytes."""

from __future__ import annotations

import io
from pathlib import Path

import pypdfium2
from PIL import Image, ImageOps


def generate_previews(content: bytes, mime_type: str, directory: Path) -> list[Path]:
    if mime_type == "application/pdf":
        with pypdfium2.PdfDocument(content) as pdf:
            pages = []
            for page in pdf:
                width, height = page.get_size()
                scale = min(1.5, 1600 / max(width, height))
                if int(width * scale) * int(height * scale) > 25_000_000:
                    raise ValueError("Preview pixel limit exceeded")
                pages.append(page.render(scale=scale).to_pil().convert("RGB"))
    else:
        with Image.open(io.BytesIO(content)) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((1600, 1600))
            pages = [image]
    outputs = []
    for number, image in enumerate(pages, start=1):
        output = directory / f"page-{number}.png"
        image.save(output, format="PNG", optimize=True)
        outputs.append(output)
    return outputs
