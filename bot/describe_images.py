"""Create searchable captions for knowledge-base screenshots."""
import argparse
import os
import subprocess
import sys
DEFAULT_KB = "/Users/agent/knowledge/BUILDIN_SELECTED_EXPORT_FINAL"
PROMPT = "Опиши скриншот для индекса саппорта: что за экран, какие шаги/кнопки/поля видны. Пиши только видимое, кратко, по-русски."
def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--kb-path", default=os.environ.get("KB_PATH", DEFAULT_KB)); parser.add_argument("--limit", type=int, default=0, help="0 = all images")
    args = parser.parse_args(); images = []
    for root, dirs, files in os.walk(args.kb_path):
        dirs.sort(); images.extend(os.path.join(root, name) for name in sorted(files) if name.lower().endswith(".png"))
    images = images[:args.limit] if args.limit else images
    for number, image in enumerate(images, 1):
        caption = image + ".caption.txt"; print("[%d/%d] %s" % (number, len(images), image), flush=True)
        try:
            subprocess.run(["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-m", "gpt-5.6-terra", "-i", image, "-o", caption, PROMPT], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, check=True)
            print("  saved: %s" % caption)
        except (OSError, subprocess.SubprocessError) as exc: print("  ERROR: %s" % exc, file=sys.stderr)
if __name__ == "__main__": main()
