#!/usr/bin/env python3
"""Promo provenance: forensic SIGNALS (never verdicts) for a token's promo
images/videos. Checks: hashes (sha256 + perceptual aHash/dHash for reuse
matching against a local index), container/stream metadata (ffprobe), EXIF and
software/generator tags (Pillow, exiftool if installed), C2PA content
credentials (c2patool if installed), video frame sampling with per-frame
perceptual hashes, duplicate/looped frames, and audio presence.

usage: provenance.py <file> [<file> ...] [--index cache/media_index.jsonl] [--out path.json]
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from grok_the_block.data import CACHE_DIR, write_json

IMG = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic"}
AI_HINTS = ["stable diffusion", "midjourney", "dall", "openai", "firefly", "comfyui", "automatic1111", "novelai", "flux",
            "runway", "sora", "kling", "pika", "luma", "veo", "hailuo", "imagen", "ideogram", "leonardo", "grok", "aurora", "wan", "hunyuan", "ltx"]
EDIT_HINTS = ["photoshop", "capcut", "premiere", "after effects", "davinci", "canva", "lavf", "ffmpeg", "handbrake", "inshot"]


def which(x):
    return shutil.which(x) or (str(Path.home() / ".local/bin" / x) if (Path.home() / ".local/bin" / x).exists() else None)


def phash(img):
    from PIL import Image
    g = img.convert("L")
    a = g.resize((8, 8), Image.LANCZOS); px = list(a.tobytes()); m = sum(px) / 64
    ah = sum(1 << i for i, p in enumerate(px) if p > m)
    d = g.resize((9, 8), Image.LANCZOS); q = list(d.tobytes())
    dh = sum(1 << (r * 8 + c) for r in range(8) for c in range(8) if q[r * 9 + c] > q[r * 9 + c + 1])
    return f"{ah:016x}", f"{dh:016x}"


def ham(a, b): return bin(int(a, 16) ^ int(b, 16)).count("1")


def run(cmd, timeout=120):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e: return None


def hints(blob):
    b = blob.lower()
    return sorted({h for h in AI_HINTS if h in b}), sorted({h for h in EDIT_HINTS if h in b})


def analyze(path: Path, index: list):
    sig = {"file": str(path), "sizeBytes": path.stat().st_size, "signals": [], "notes": []}
    data = path.read_bytes(); sig["sha256"] = hashlib.sha256(data).hexdigest()
    blob = ""
    # C2PA
    c2 = which("c2patool")
    if c2:
        r = run([c2, str(path)])
        if r and r.returncode == 0 and r.stdout.strip().startswith("{"):
            sig["c2pa"] = {"present": True, "manifest": json.loads(r.stdout)}
            blob += r.stdout
            sig["signals"].append("C2PA content credentials present (read the manifest's claim generator / actions; they can name an AI tool).")
        else:
            sig["c2pa"] = {"present": False, "detail": (r.stderr.strip()[:200] if r else "c2patool failed")}
            sig["notes"].append("No C2PA credentials. Normal for most media and for anything re-encoded by X/Telegram; absence proves nothing.")
    else:
        sig["notes"].append("c2patool not installed; C2PA not checked.")
    # exiftool
    ex = which("exiftool")
    if ex:
        r = run([ex, "-j", "-G", str(path)])
        if r and r.returncode == 0:
            sig["exiftool"] = json.loads(r.stdout)[0]; blob += r.stdout
    is_img = path.suffix.lower() in IMG
    frames = []
    if is_img:
        from PIL import Image, ExifTags
        im = Image.open(path)
        sig["image"] = {"format": im.format, "size": im.size, "mode": im.mode}
        exif = {ExifTags.TAGS.get(k, str(k)): str(v)[:200] for k, v in (im.getexif() or {}).items()}
        sig["exif"] = exif; blob += json.dumps(exif) + json.dumps({k: str(v)[:500] for k, v in im.info.items()})
        if "parameters" in im.info or "prompt" in im.info or "workflow" in im.info:
            sig["signals"].append("PNG text chunk with generation parameters/prompt/workflow (typical of Stable Diffusion / ComfyUI output).")
        if not exif:
            sig["notes"].append("No EXIF. Common for screenshots, platform re-uploads and generated images alike.")
        elif "Make" in exif or "Model" in exif:
            sig["signals"].append(f"Camera EXIF present: {exif.get('Make', '')} {exif.get('Model', '')} (can be forged).")
        w, h = im.size
        if w % 64 == 0 and h % 64 == 0 and max(w, h) in (512, 768, 1024, 1152, 1216, 1344, 1536, 2048):
            sig["signals"].append(f"Dimensions {w}x{h} match common diffusion-model output sizes (weak signal).")
        frames.append(phash(im))
    else:
        r = run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)])
        if r and r.returncode == 0:
            fp = json.loads(r.stdout); sig["ffprobe"] = fp; blob += r.stdout
            v = [s for s in fp.get("streams", []) if s.get("codec_type") == "video"]
            a = [s for s in fp.get("streams", []) if s.get("codec_type") == "audio"]
            dur = float(fp.get("format", {}).get("duration", 0) or 0)
            sig["video"] = {"duration": dur, "streams": len(v), "audio": bool(a),
                            "codec": v[0].get("codec_name") if v else None, "size": f"{v[0].get('width')}x{v[0].get('height')}" if v else None,
                            "fps": v[0].get("r_frame_rate") if v else None, "encoder": fp.get("format", {}).get("tags", {}).get("encoder"),
                            "creation_time": fp.get("format", {}).get("tags", {}).get("creation_time")}
            if not a: sig["signals"].append("No audio track.")
            if v and dur and dur <= 10.5: sig["signals"].append(f"Short clip ({dur:.1f}s), within typical AI video generation lengths (weak signal).")
            with tempfile.TemporaryDirectory() as td:
                n = 12
                rate = max(n / dur, 0.1) if dur else 1
                run(["ffmpeg", "-v", "quiet", "-i", str(path), "-vf", f"fps={rate},scale=256:-1", "-frames:v", str(n), f"{td}/f%03d.png"], 300)
                from PIL import Image
                for f in sorted(Path(td).glob("*.png")):
                    frames.append(phash(Image.open(f)))
            if len(frames) > 2:
                dups = sum(1 for i in range(1, len(frames)) if ham(frames[i][1], frames[i - 1][1]) <= 2)
                if dups >= len(frames) // 2: sig["signals"].append(f"{dups}/{len(frames) - 1} sampled frames nearly identical (static image, slideshow, or loop).")
                if ham(frames[0][1], frames[-1][1]) <= 6 and dur > 2: sig["signals"].append("First and last sampled frames nearly identical (possible seamless loop).")
    ai, ed = hints(blob)
    if ai: sig["signals"].append(f"Metadata mentions generator-like names: {', '.join(ai)} (verify in raw metadata; could be coincidental).")
    if ed: sig["signals"].append(f"Metadata mentions encoder/editor: {', '.join(ed)} (re-encoded or edited).")
    sig["perceptualHashes"] = [{"aHash": a, "dHash": d} for a, d in frames]
    # reuse vs local index
    matches = []
    for rec in index:
        if rec["sha256"] == sig["sha256"] and rec["file"] != str(path):
            matches.append({"file": rec["file"], "label": rec.get("label"), "match": "exact"}); continue
        best = min((ham(x["dHash"], y["dHash"]) for x in sig["perceptualHashes"] for y in rec["perceptualHashes"]), default=99)
        if best <= 6 and rec["file"] != str(path):
            matches.append({"file": rec["file"], "label": rec.get("label"), "match": f"perceptual (distance {best})"})
    if matches: sig["signals"].append(f"Visual reuse: matches {len(matches)} previously indexed file(s).")
    sig["reuseMatches"] = matches
    sig["reverseSearchHint"] = "Have the bot run a reverse image search on 1-2 extracted frames (WebSearch / browser) to find earlier copies."
    return sig


def main():
    ap = argparse.ArgumentParser(description='Grok The Block · promo provenance: check promo media for reuse, edits and generation signals.', epilog="An evolution of CryptOSINT by @varien. Read-only."); ap.add_argument("files", nargs="+"); ap.add_argument("--label", default="")
    ap.add_argument("--index", default=str(CACHE_DIR / "media_index.jsonl")); ap.add_argument("--out")
    a = ap.parse_args()
    ip = Path(a.index); index = [json.loads(l) for l in ip.read_text().splitlines()] if ip.exists() else []
    results = []
    for f in a.files:
        r = analyze(Path(f), index); r["label"] = a.label; results.append(r)
        print(f"\n{f}  sha256 {r['sha256'][:16]}…  C2PA: {r.get('c2pa', {}).get('present')}")
        for s in r["signals"]: print("  SIGNAL:", s)
        for n in r["notes"]: print("  note:  ", n)
    ip.parent.mkdir(parents=True, exist_ok=True)
    with ip.open("a") as fh:
        for r in results: fh.write(json.dumps({k: r[k] for k in ("file", "sha256", "perceptualHashes", "label")}) + "\n")
    out = Path(a.out) if a.out else Path(__file__).resolve().parents[3] / "out" / "provenance.json"
    write_json(out, {"results": results, "disclaimer": "Signals only, never a verdict. Missing metadata is normal; present metadata can be forged."})
    print(f"\nJSON: {out}")


if __name__ == "__main__":
    main()
