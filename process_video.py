import os
import sys
import asyncio
import subprocess
import json
import requests
import traceback
import time
import math
from telethon import TelegramClient
from telethon.tl import types

# ── Environment Variables ──────────────────────────────────────────────────────
API_ID              = os.environ.get('API_ID', '0')
API_HASH            = os.environ.get('API_HASH', '')
BOT_TOKEN           = os.environ.get('BOT_TOKEN', '')
VIDEO_URL           = os.environ.get('VIDEO_URL', '')
PHOTO_CAPTION       = os.environ.get('PHOTO_CAPTION', '#Video #PremiumV2')
VIDEO_CAPTION       = os.environ.get('VIDEO_CAPTION', '# Full Video Outta')
NUM_PHOTOS          = int(os.environ.get('NUM_PHOTOS', '4'))
POST_MODE           = os.environ.get('POST_MODE', 'both')
CHAT_ID             = os.environ.get('CHAT_ID', '')
WORKER_URL          = os.environ.get('WORKER_URL', '')
WORKFLOW_NAME       = os.environ.get('WORKFLOW_NAME', 'Unknown Workflow')
TARGET_RESOLUTION   = os.environ.get('TARGET_RESOLUTION', '720p')
MAX_FILE_SIZE_MB    = 2000
PH_USERNAME         = os.environ.get('PH_USERNAME', '')
PH_PASSWORD         = os.environ.get('PH_PASSWORD', '')

# ── Channel ID parse ───────────────────────────────────────────────────────────
def parse_channel_id(raw):
    raw = raw.strip()
    try:
        if raw.startswith('-100'):   return int(raw)
        elif raw.lstrip('-').isdigit(): return int(raw)
        else: raise ValueError
    except ValueError:
        print(f"❌ Invalid TARGET_CHANNEL_ID: '{raw}'")
        sys.exit(1)

TARGET_CHANNEL_ID = parse_channel_id(os.environ.get('TARGET_CHANNEL_ID', '0'))

# ── Helpers ────────────────────────────────────────────────────────────────────
def send_progress(text):
    msg = f"[{WORKFLOW_NAME}]\n{text}"
    print(msg)
    if CHAT_ID and WORKER_URL:
        try:
            requests.post(WORKER_URL, json={"chat_id": CHAT_ID, "progress_text": msg}, timeout=10)
        except Exception:
            pass

def preflight_check():
    """Fail fast — check all required secrets before doing any work."""
    required = {
        'API_ID': API_ID, 'API_HASH': API_HASH,
        'BOT_TOKEN': BOT_TOKEN, 'VIDEO_URL': VIDEO_URL,
    }
    missing = [k for k, v in required.items() if not v or v == '0']
    if missing:
        send_progress(f"❌ Missing required secrets: {', '.join(missing)}\nWorkflow ကို stop လုပ်လိုက်ပါတယ်။")
        sys.exit(1)
    send_progress("✅ Pre-flight check passed — secrets OK")

def get_video_info(path):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', path],
            capture_output=True, text=True)
        data = json.loads(r.stdout)
        duration = int(float(data['format']['duration']))
        w, h = 0, 0
        for s in data['streams']:
            if s['codec_type'] == 'video':
                w, h = int(s['width']), int(s['height'])
                break
        return duration, w, h
    except Exception as e:
        print(f"ffprobe error: {e}")
        return 0, 0, 0

def capture_screenshot(video_path, time_pos, out_path):
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-ss', str(time_pos), '-i', video_path,
             '-frames:v', '1', '-update', '1', '-q:v', '2', out_path],
            check=True, capture_output=True)
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception as e:
        print(f"Screenshot error at {time_pos}s: {e}")
        return False

def classify_download_error(stderr):
    s = stderr.lower()
    if 'login' in s or 'require' in s or 'password' in s or 'sign in' in s:
        return "🔐 Login လိုတဲ့ video — credentials မမှန် သို့မဟုတ် session expired"
    if 'deleted' in s or 'removed' in s or 'not available' in s or 'does not exist' in s:
        return "🚫 Video ကို ဖျက်ပြီးပြီ သို့မဟုတ် ရနိုင်တော့မည်မဟုတ်"
    if 'geo' in s or 'your country' in s or 'blocked' in s:
        return "🌏 Geo-blocked — ဒီ region မှာ ကြည့်လို့မရဘူး"
    if 'unsupported url' in s or 'no video formats' in s:
        return "🔗 URL format မမှန်ဘူး သို့မဟုတ် site ကို support မလုပ်ဘူး"
    if 'redirection' in s:
        return "↩️ Redirect detected — video ကို login မှ ကြည့်ရတာဖြစ်နိုင်တယ်"
    return f"❌ Download failed:\n{stderr[:300]}"

# ── Download with 3 fallback strategies ───────────────────────────────────────
def download_video(raw_video):
    base_cmd = ['yt-dlp', '--merge-output-format', 'mp4', '-o', raw_video]
    creds    = ['--username', PH_USERNAME, '--password', PH_PASSWORD] if PH_USERNAME and PH_PASSWORD else []

    strategies = [
        # 1. Best quality + browser impersonation + credentials
        base_cmd + ['-f', 'bestvideo+bestaudio/best', '--impersonate', 'chrome'] + creds + [VIDEO_URL],
        # 2. Any available format + credentials (relaxed)
        base_cmd + ['-f', 'best'] + creds + [VIDEO_URL],
        # 3. Fallback: no impersonation, no format preference
        base_cmd + creds + [VIDEO_URL],
    ]

    last_err = ''
    for i, cmd in enumerate(strategies, 1):
        send_progress(f"📥 Download strategy {i}/3 ...")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(raw_video):
            return True
        last_err = r.stderr
        print(f"Strategy {i} failed: {last_err[:200]}")

    raise Exception(classify_download_error(last_err))

def get_title(video_url):
    creds = ['--username', PH_USERNAME, '--password', PH_PASSWORD] if PH_USERNAME and PH_PASSWORD else []
    r = subprocess.run(['yt-dlp', '--get-title'] + creds + [video_url], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "Premium Video"

# ── Main ───────────────────────────────────────────────────────────────────────
async def main():
    preflight_check()

    raw_video  = 'raw_video.mp4'
    final_video = 'final_video.mp4'
    thumbnail  = 'thumb.jpg'
    screenshots = []
    video_parts = []

    try:
        # ── 1. Download ────────────────────────────────────────────────────────
        download_video(raw_video)
        video_title = get_title(VIDEO_URL)
        send_progress(f"✅ Downloaded: {video_title}")

        # ── 2. Screenshots ─────────────────────────────────────────────────────
        send_progress(f"📸 Generating {NUM_PHOTOS} screenshots...")
        duration, width, height = get_video_info(raw_video)
        if duration > 0:
            capture_screenshot(raw_video, duration * 0.1, thumbnail)
            for i in range(1, NUM_PHOTOS + 1):
                pos  = (duration / (NUM_PHOTOS + 1)) * i
                path = f'screenshot_{i}.jpg'
                if capture_screenshot(raw_video, pos, path):
                    screenshots.append(path)
        send_progress(f"✅ {len(screenshots)} screenshots ready")

        # ── 3. Process (watermark + encode) ───────────────────────────────────
        send_progress("⚙️ Processing video...")
        try:
            vf = "drawtext=text='PREMIUM':x=10:y=10:fontsize=24:fontcolor=white@0.5:box=1:boxcolor=black@0.2"
            if height > 0:
                if   TARGET_RESOLUTION == '1080p' and height >= 1080: vf += ",scale=-2:1080"
                elif TARGET_RESOLUTION == '720p'  and height >= 720:  vf += ",scale=-2:720"
                else: vf += ",scale='trunc(iw/2)*2:trunc(ih/2)*2'"
            subprocess.run([
                'ffmpeg', '-y', '-i', raw_video, '-vf', vf,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k', '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', final_video
            ], check=True, capture_output=True)
            send_progress("✅ Video processed (720p + watermark)")
        except Exception as e:
            send_progress(f"⚠️ Encode warning: {e} — raw video သုံးမယ်")
            final_video = raw_video

        # ── 4. Split if > 2GB ──────────────────────────────────────────────────
        video_parts = [final_video]
        size_mb = os.path.getsize(final_video) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            send_progress(f"✂️ Splitting video ({size_mb:.0f}MB > {MAX_FILE_SIZE_MB}MB)...")
            video_parts = []
            dur, _, _ = get_video_info(final_video)
            n = math.ceil(size_mb / MAX_FILE_SIZE_MB)
            part_dur = dur / n
            for i in range(n):
                pf = f'part_{i}.mp4'
                subprocess.run([
                    'ffmpeg', '-y', '-i', final_video,
                    '-ss', str(i * part_dur), '-t', str(part_dur),
                    '-c', 'copy', '-movflags', '+faststart', pf
                ], check=True, capture_output=True)
                video_parts.append(pf)
            send_progress(f"✅ Split into {n} parts")

        # ── 5. Upload via Telethon Public API ──────────────────────────────────
        send_progress("🚀 Connecting to Telegram...")
        client = TelegramClient('bot_session', int(API_ID), API_HASH)
        await client.start(bot_token=BOT_TOKEN)

        async with client:
            thumb = thumbnail if os.path.exists(thumbnail) else None

            send_progress("📤 Uploading...")

            if POST_MODE == 'album':
                # Photos only
                if screenshots:
                    await client.send_file(
                        TARGET_CHANNEL_ID, screenshots,
                        caption=f"📸 **{video_title}**\n\n{PHOTO_CAPTION}",
                        parse_mode='markdown')

            elif POST_MODE == 'both':
                # Photos first, then video separately
                if screenshots:
                    await client.send_file(
                        TARGET_CHANNEL_ID, screenshots,
                        caption=f"📸 **{video_title}**\n\n{PHOTO_CAPTION}",
                        parse_mode='markdown')
                    send_progress("✅ Photos uploaded")

                for i, part in enumerate(video_parts):
                    dur, w, h = get_video_info(part)
                    suffix = f" (Part {i+1}/{len(video_parts)})" if len(video_parts) > 1 else ""
                    cap = f"🎬 **{video_title}{suffix}**\n\n{VIDEO_CAPTION}"
                    await client.send_file(
                        TARGET_CHANNEL_ID, part,
                        caption=cap, parse_mode='markdown',
                        thumb=thumb if i == 0 else None,
                        supports_streaming=True,
                        attributes=[types.DocumentAttributeVideo(
                            duration=dur, w=w, h=h, supports_streaming=True)])
                    send_progress(f"✅ Video part {i+1}/{len(video_parts)} uploaded")

            elif POST_MODE == 'video':
                # Photos + video in one album
                media = screenshots[:]
                media.append(video_parts[0])
                dur, w, h = get_video_info(video_parts[0])
                await client.send_file(
                    TARGET_CHANNEL_ID, media,
                    caption=f"🎬 **{video_title}**\n\n{VIDEO_CAPTION}",
                    parse_mode='markdown',
                    supports_streaming=True)

        send_progress("✅ Task Completed Successfully!")

    except Exception as e:
        stack = traceback.format_exc()
        send_progress(
            f"❌ **Critical Error**\n\n"
            f"**Workflow:** `{WORKFLOW_NAME}`\n"
            f"**Error:** `{type(e).__name__}`\n"
            f"**Message:** {str(e)}\n\n"
            f"**URL:** {VIDEO_URL}\n"
            f"```python\n{stack[:600]}\n```"
        )
        print(stack)
        sys.exit(1)

    finally:
        cleanup = [raw_video, final_video, thumbnail] + screenshots + video_parts
        for f in cleanup:
            if f and os.path.exists(f):
                try: os.remove(f)
                except: pass

if __name__ == '__main__':
    asyncio.run(main())
