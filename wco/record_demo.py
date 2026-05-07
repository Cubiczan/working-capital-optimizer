"""Record wco-demo.html as an MP4 video using Playwright (sync) + FFmpeg."""

import glob
import subprocess
import time
from pathlib import Path

OUTPUT_DIR = Path("/home/z/my-project/download")
HTML_FILE = Path("/home/z/my-project/download/wco-demo.html")
VIDEO_TMP_DIR = Path("/tmp/wco-recording")
DURATION_SECONDS = 185  # 3 min 5 sec buffer

def main() -> None:
    from playwright.sync_api import sync_playwright

    # Clean temp dir
    import shutil
    if VIDEO_TMP_DIR.exists():
        shutil.rmtree(VIDEO_TMP_DIR)
    VIDEO_TMP_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Recording {HTML_FILE.name} for {DURATION_SECONDS}s ...")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
            record_video_dir=str(VIDEO_TMP_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )

        page = context.new_page()
        page.goto(f"file://{HTML_FILE.resolve()}")
        print("  Page loaded, capturing frames ...")

        # Wait for presentation to complete
        time.sleep(DURATION_SECONDS)

        # Closing context finalizes the recording
        context.close()
        browser.close()

    # Find the recorded webm
    webm_files = glob.glob(str(VIDEO_TMP_DIR / "**" / "*.webm"), recursive=True)
    if not webm_files:
        print("ERROR: No video file found after recording!")
        return

    raw = Path(webm_files[0])
    final = OUTPUT_DIR / "wco-demo.mp4"
    print(f"  Raw: {raw.name} ({raw.stat().st_size / 1024:.0f} KB)")

    # Convert webm → mp4
    print("Converting to MP4 (h264) ...")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-r", "30",
        "-an",  # no audio (slideshow only)
        str(final),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"FFmpeg error:\n{result.stderr[-600:]}")
        return

    # Cleanup
    shutil.rmtree(VIDEO_TMP_DIR, ignore_errors=True)

    size_mb = final.stat().st_size / (1024 * 1024)
    print(f"\nDone! {final} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
