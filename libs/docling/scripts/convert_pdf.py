"""Convert local PDF artifacts with the Newman Labs Docling library."""

import asyncio
from pathlib import Path

import aiofiles.os

from libs.docling.functions import convert_pdf

ARTIFACT_DIRECTORY = Path(__file__).resolve().parents[1] / "artifacts"


async def main() -> int:
    """Convert every PDF in the local artifact directory."""
    await aiofiles.os.makedirs(ARTIFACT_DIRECTORY, exist_ok=True)
    pdf_paths = sorted(
        ARTIFACT_DIRECTORY / name
        for name in await aiofiles.os.listdir(ARTIFACT_DIRECTORY)
        if name.lower().endswith(".pdf")
    )
    if not pdf_paths:
        print(f"Add PDF files to {ARTIFACT_DIRECTORY}")
        return 0

    for pdf_path in pdf_paths:
        result = await convert_pdf(source=pdf_path)
        print(f"Docling {result.version} | {result.page_count} pages | {pdf_path.name}")
        print()
        print(result.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
