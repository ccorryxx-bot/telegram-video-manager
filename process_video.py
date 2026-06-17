import os
import sys
import asyncio
import cv2
import subprocess
import json
import requests
import traceback
import time
import math
from telethon import TelegramClient, types, utils

# Environment Variables
API_ID = int(os.environ.get('API_ID', '0'))
API_HASH = os.environ.get('API_HASH', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
VIDEO_URL = os.environ.get('VIDEO_URL', '')
PHOTO_CAPTION_TEMPLATE = os.environ.get('PHOTO_CAPTION', '#Video #PremiumV2')
VIDEO_CAPTION_TEMPLATE = os.environ.get('VIDEO_CAPTION', '# Full Video Outta')
NUM_PHOTOS = int(os.environ.get('NUM_PHOTOS', '4'))
POST_MODE = os.environ.get('POST_MODE', 'both')
CHAT_ID = os.environ.get('CHAT_ID', '')
WORKER_URL = os.environ.get('WORKER_URL', '')
WORKFLOW_NAME = os.environ.get('WORKFLOW_NAME', 'Unknown Workflow')
MAX_FILE_SIZE_MB = 2000 # 2GB in MB
TARGET_RESOLUTION = os.environ.get('TARGET_RESOLUTION', '720p')

# Target Channel ID
raw_channel_id = os.environ.get('TARGET_CHANNEL_ID', '0').strip()
try:
    if raw_channel_id.startswith('-100'):
        TARGET_CHANNEL_ID = int(raw_channel_id)
    elif raw_channel_id.isdigit():
        TARGET_CHANNEL_ID = int(f"-100{raw_channel_id}")
    else:
        TARGET_CHANNEL_ID = int(raw_channel_id)
except ValueError:
    print(f"Error: Invalid TARGET_CHANNEL_ID format: '{raw_channel_id}'")
    sys.exit(1)

def send_progress(text):
    full_text = f"[{WORKFLOW_NAME}]\n{text}"
    print(full_text)
    if CHAT_ID and WORKER_URL:
        try:
            requests.post(WORKER_URL, json={
                "chat_id": CHAT_ID,
                "progress_text": full_text
            })
        except: pass

def get_video_info(file_path):
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-show_format', '-show_streams', file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        duration = int(float(data['format']['duration']))
        width, height = 0, 0
        for stream in data['streams']:
            if stream['codec_type'] == 'video':
                width = int(stream['width'])
                height = int(stream['height'])
                break
        return duration, width, height
    except Exception as e:
        print(f"Metadata Error: {e}")
        return 0, 0, 0

async def retry_async(func, *args, retries=3, delay=5, **kwargs):
    for i in range(retries):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if i == retries - 1: raise e
            send_progress(f"⚠️ Attempt {i+1} failed. Retrying in {delay}s...")
            await asyncio.sleep(delay)

def retry_sync(func, *args, retries=3, delay=5, **kwargs):
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if i == retries - 1: raise e
            send_progress(f"⚠️ Attempt {i+1} failed. Retrying in {delay}s...")
            time.sleep(delay)

def capture_screenshot(video_path, time_pos, output_path):
    try:
        cmd = [
            'ffmpeg', '-y', '-ss', str(time_pos), '-i', video_path,
            '-frames:v', '1', '-update', '1', '-q:v', '2', output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg capture error at {time_pos}s: {e}")
        return False

async def fast_upload(client, file_path, connections=8):
    file_size = os.path.getsize(file_path)
    part_size = 512 * 1024
    parts_count = math.ceil(file_size / part_size)
    file_id = utils.generate_random_long()
    is_large = file_size > 10 * 1024 * 1024
    
    with open(file_path, 'rb') as f:
        pool = []
        for i in range(parts_count):
            chunk = f.read(part_size)
            if is_large:
                pool.append(client(types.functions.upload.SaveBigFilePartRequest(
                    file_id=file_id, file_part=i, file_total_parts=parts_count, bytes=chunk
                )))
            else:
                pool.append(client(types.functions.upload.SaveFilePartRequest(
                    file_id=file_id, file_part=i, bytes=chunk
                )))
            
            if len(pool) >= connections:
                await asyncio.gather(*pool)
                pool = []
        if pool:
            await asyncio.gather(*pool)
            
    if is_large:
        return types.InputFileBig(id=file_id, parts=parts_count, name=os.path.basename(file_path))
    else:
        return types.InputFile(id=file_id, parts=parts_count, name=os.path.basename(file_path), md5_checksum='')

async def main():
    if not VIDEO_URL:
        print("No VIDEO_URL provided.")
        return

    send_progress(f"📥 Downloading: {VIDEO_URL}")
    raw_video = 'raw_video.mp4'
    final_video = 'final_video.mp4'
    thumbnail = 'thumb.jpg'
    video_title = "Premium Video"
    screenshots = []
    video_parts = []

    try:
        def download_video():
            cmd = [
                'yt-dlp', '-f', 'bestvideo+bestaudio/best', '--merge-output-format', 'mp4',
                '--impersonate', 'chrome', '-o', raw_video, VIDEO_URL
            ]
            process = subprocess.run(cmd, capture_output=True, text=True)
            if process.returncode != 0:
                raise Exception(f"yt-dlp failed: {process.stderr}")
            return True

        retry_sync(download_video)
        
        title_res = subprocess.run(['yt-dlp', '--get-title', VIDEO_URL], capture_output=True, text=True)
        if title_res.returncode == 0:
            video_title = title_res.stdout.strip()

        if not os.path.exists(raw_video):
            raise Exception("Download failed: File not found.")

        send_progress("📸 Generating screenshots...")
        duration, width, height = get_video_info(raw_video)
        if duration > 0:
            thumb_pos = duration * 0.1
            capture_screenshot(raw_video, thumb_pos, thumbnail)
            for i in range(1, NUM_PHOTOS + 1):
                shot_pos = (duration / (NUM_PHOTOS + 1)) * i
                shot_path = f'screenshot_{i}.jpg'
                if capture_screenshot(raw_video, shot_pos, shot_path):
                    screenshots.append(shot_path)
        
        send_progress("⚙️ Processing video (Pro Mode: Fast-Start & Dynamic Res)...")
        try:
            watermark_text = "V3 PREMIUM"
            vf = f"drawtext=text='{watermark_text}':x=10:y=10:fontsize=24:fontcolor=white@0.5:box=1:boxcolor=black@0.2"
            if height > 0:
                if TARGET_RESOLUTION == '1080p' and height >= 1080: vf += ",scale=-2:1080"
                elif TARGET_RESOLUTION == '720p' and height >= 720: vf += ",scale=-2:720"
                else: vf += ",scale='trunc(iw/2)*2:trunc(ih/2)*2'"
            
            subprocess.run([
                'ffmpeg', '-y', '-i', raw_video, '-vf', vf,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k', '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', final_video
            ], check=True, capture_output=True)
        except Exception as e:
            send_progress(f"⚠️ Processing Warning: {str(e)}. Using raw video.")
            final_video = raw_video

        video_parts = [final_video]
        file_size_mb = os.path.getsize(final_video) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            send_progress(f"✂️ Splitting video ({file_size_mb:.2f}MB)...")
            video_parts = []
            duration, _, _ = get_video_info(final_video)
            num_parts = math.ceil(file_size_mb / MAX_FILE_SIZE_MB)
            part_duration = duration / num_parts
            for i in range(num_parts):
                part_file = f"part_{i}_{final_video}"
                subprocess.run([
                    'ffmpeg', '-y', '-i', final_video, '-ss', str(i * part_duration),
                    '-t', str(part_duration), '-c', 'copy', '-movflags', '+faststart', part_file
                ], check=True)
                video_parts.append(part_file)

        send_progress("🚀 Uploading to Telegram (Pro Mode)...")
        uploader = TelegramClient('bot_uploader', API_ID, API_HASH)
        await uploader.start(bot_token=BOT_TOKEN)
        async with uploader:
            has_thumb = os.path.exists(thumbnail)
            thumb_file = thumbnail if has_thumb else None
            
            async def upload_logic():
                if POST_MODE == 'video':
                    # ROBUST APPROACH: Let Telethon handle the media types
                    # Upload screenshots and video part 1
                    media = []
                    for i, img in enumerate(screenshots):
                        cap = f"📸🎬 **{video_title}**\n\n{VIDEO_CAPTION_TEMPLATE}" if i == 0 else ""
                        media.append(await uploader.upload_file(img))
                    
                    # Add video part 1
                    v_dur, v_w, v_h = get_video_info(video_parts[0])
                    video_file = await fast_upload(uploader, video_parts[0])
                    
                    # Send as album
                    # For albums, we need to wrap them in InputMedia
                    media_group = []
                    for i, m in enumerate(media):
                        cap = f"📸🎬 **{video_title}**\n\n{VIDEO_CAPTION_TEMPLATE}" if i == 0 else ""
                        media_group.append(types.InputMediaUploadedPhoto(file=m, caption=cap, parse_mode='markdown'))
                    
                    media_group.append(types.InputMediaUploadedDocument(
                        file=video_file, mime_type='video/mp4',
                        attributes=[types.DocumentAttributeVideo(duration=v_dur, w=v_w, h=v_h, supports_streaming=True)],
                        thumb=await uploader.upload_file(thumb_file) if thumb_file else None
                    ))
                    await uploader.send_file(TARGET_CHANNEL_ID, media_group)

                elif POST_MODE == 'both':
                    if screenshots:
                        await uploader.send_file(TARGET_CHANNEL_ID, screenshots, caption=f"📸 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}", parse_mode='markdown')
                    for i, part in enumerate(video_parts):
                        d, w, h = get_video_info(part)
                        suffix = f" (Part {i+1}/{len(video_parts)})" if len(video_parts) > 1 else ""
                        cap = f"🎬 **{video_title}{suffix}**\n\n{VIDEO_CAPTION_TEMPLATE}"
                        await uploader.send_file(
                            TARGET_CHANNEL_ID, await fast_upload(uploader, part), caption=cap,
                            thumb=thumb_file if i == 0 else None, parse_mode='markdown',
                            attributes=[types.DocumentAttributeVideo(duration=d, w=w, h=h, supports_streaming=True)]
                        )
                elif POST_MODE == 'album' and screenshots:
                    await uploader.send_file(TARGET_CHANNEL_ID, screenshots, caption=f"📸 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}", parse_mode='markdown')

            await retry_async(upload_logic)

        send_progress("✅ Task Completed Successfully!")

    except Exception as e:
        error_type = type(e).__name__
        error_detail = str(e)
        stack_trace = traceback.format_exc()
        error_msg = (
            f"❌ **Critical Error in Workflow**\n\n"
            f"**Workflow:** `{WORKFLOW_NAME}`\n"
            f"**Error Type:** `{error_type}`\n"
            f"**Message:** `{error_detail}`\n\n"
            f"**Video URL:** {VIDEO_URL}\n"
            f"**Stack Trace:**\n```python\n{stack_trace[:500]}...\n```"
        )
        print(stack_trace)
        send_progress(error_msg)
    finally:
        files = [raw_video, final_video, thumbnail, 'last_resort.jpg'] + screenshots + video_parts
        for f in files:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

if __name__ == '__main__':
    asyncio.run(main())
