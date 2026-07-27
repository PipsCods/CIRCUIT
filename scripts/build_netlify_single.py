#!/usr/bin/env python3
"""Build a self-contained Netlify directory for the static CIRCUIT demo."""
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
OUTPUT = ROOT / "netlify-upload"
ASSETS = (
    "index.html",
    "styles.css",
    "demo-data.js",
    "product-data.js",
    "app.js",
    "workflow.html",
    "workflow.css",
    "workflow.js",
)


def main():
    missing = [name for name in ASSETS if not (DEMO / name).is_file()]
    if missing:
        raise RuntimeError(
            "demo export is missing required assets: " + ", ".join(missing)
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        shutil.copyfile(DEMO / name, OUTPUT / name)

    print(
        f"Wrote {len(ASSETS)} static assets to {OUTPUT} "
        f"({sum((OUTPUT / name).stat().st_size for name in ASSETS):,} bytes)"
    )


if __name__ == "__main__":
    main()
