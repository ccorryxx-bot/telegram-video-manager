import os
import sys
import asyncio
import cv2
import subprocess
import json
import requests
import traceback
from telethon import TelegramClient, types

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
MAX_FILE_SIZE_MB = 2000 # 2GB in MB
TARGET_RESOLUTION = os.environ.get('TARGET_RESOLUTION', '720p') # Default to 720p

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
    print(text)
    if CHAT_ID and WORKER_URL:
        try:
            requests.post(WORKER_URL, json={
                "chat_id": CHAT_ID,
                "progress_text": text
            })
        except: pass

def get_video_info(file_path):
    """Extract metadata using ffprobe for Telegram upload."""
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

def generate_thumbnail(video_path, thumb_path):
    """Generate a thumbnail at 10% of the video duration with improved FFmpeg command."""
    try:
        duration, _, _ = get_video_info(video_path)
        seek_time = duration * 0.1
        # Added -update 1 and -frames:v 1 for better compatibility
        cmd = [
            'ffmpeg', '-y', '-ss', str(seek_time), '-i', video_path,
            '-frames:v', '1', '-update', '1', '-q:v', '2', thumb_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return True if os.path.exists(thumb_path) else False
    except Exception as e:
        print(f"Thumbnail Generation Error: {e}")
        return False

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
        # 1. Download using yt-dlp
        try:
            cmd = [
                'yt-dlp', 
                '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4', 
                '--merge-output-format', 'mp4',
                '-o', raw_video,
                VIDEO_URL
            ]
            subprocess.run(cmd, check=True)
            
            title_cmd = ['yt-dlp', '--get-title', VIDEO_URL]
            title_res = subprocess.run(title_cmd, capture_output=True, text=True)
            if title_res.returncode == 0:
                video_title = title_res.stdout.strip()
        except Exception as e:
            send_progress(f"❌ Download Error: {str(e)}")
            return

        if not os.path.exists(raw_video):
            send_progress("❌ Download failed: File not found.")
            return

        # Determine target resolution for FFmpeg
        scale_filter = ''
        if TARGET_RESOLUTION == '720p':
            scale_filter = 'scale=-2:720'
        elif TARGET_RESOLUTION == '1080p':
            scale_filter = 'scale=-2:1080'

        # 2. Convert, Watermark, Compress & Apply Quality Selection
        send_progress("⚙️ Applying Watermark and Compression...")
        try:
            watermark_text = "V3 PREMIUM"
            vf_filters = [f"drawtext=text='{watermark_text}':x=10:y=10:fontsize=24:fontcolor=white@0.5:box=1:boxcolor=black@0.2"]
            if scale_filter:
                vf_filters.append(scale_filter)
            
            convert_cmd = [
                'ffmpeg', '-y', '-i', raw_video,
                '-vf', ','.join(vf_filters),
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                '-pix_fmt', 'yuv420p',
                final_video
            ]
            subprocess.run(convert_cmd, check=True)
        except Exception as e:
            send_progress(f"⚠️ Conversion Warning: {str(e)}. Using raw video.")
            final_video = raw_video

        # 3. Auto-Split if file size > 2GB
        video_parts = [final_video]
        if os.path.exists(final_video):
            file_size_mb = os.path.getsize(final_video) / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                send_progress(f"✂️ Splitting video ({file_size_mb:.2f}MB)...")
                video_parts = []
                duration, _, _ = get_video_info(final_video)
                part_duration = duration // (int(file_size_mb / MAX_FILE_SIZE_MB) + 1)
                
                i = 0
                start_time = 0
                while start_time < duration:
                    part_file = f"part_{i}_{final_video}"
                    split_cmd = [
                        'ffmpeg', '-y', '-i', final_video,
                        '-ss', str(start_time), '-t', str(part_duration),
                        '-c', 'copy', part_file
                    ]
                    try:
                        subprocess.run(split_cmd, check=True)
                        video_parts.append(part_file)
                        start_time += part_duration
                        i += 1
                    except Exception as e:
                        send_progress(f"❌ Video split failed for part {i}: {str(e)}")
                        break
                send_progress(f"✅ Split into {len(video_parts)} parts.")

        # 4. Generate Thumbnail and Screenshots
        send_progress("📸 Generating screenshots and thumbnail...")
        has_thumb = generate_thumbnail(video_parts[0], thumbnail)
        
        if os.path.exists(video_parts[0]) and POST_MODE in ['album', 'both', 'video']:
            try:
                cap = cv2.VideoCapture(video_parts[0])
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    for i in range(1, NUM_PHOTOS + 1):
                        frame_pos = int((total_frames / (NUM_PHOTOS + 1)) * i)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                        ret, frame = cap.read()
                        if ret:
                            filename = f'screenshot_{i}.jpg'
                            cv2.imwrite(filename, frame)
                            screenshots.append(filename)
                cap.release()
            except Exception as e:
                print(f"Screenshot Error: {e}")

        # 5. Upload to Telegram
        send_progress("📤 Uploading to Telegram...")
        uploader = TelegramClient('bot_uploader', API_ID, API_HASH)
        await uploader.start(bot_token=BOT_TOKEN)
        async with uploader:
            thumb_file = thumbnail if has_thumb else None
            
            # MODE: Combined Album + Video
            if POST_MODE == 'video':
                media_group = []
                # Add screenshots
                for i, img in enumerate(screenshots):
                    caption = f"📸🎬 **{video_title}**\n\n{VIDEO_CAPTION_TEMPLATE}" if i == 0 else ""
                    media_group.append(types.InputMediaPhoto(file=img, caption=caption, parse_mode='markdown'))
                
                # Add first video part
                duration, width, height = get_video_info(video_parts[0])
                media_group.append(types.InputMediaUploadedDocument(
                    file=await uploader.upload_file(video_parts[0]),
                    mime_type='video/mp4',
                    attributes=[types.DocumentAttributeVideo(
                        duration=duration, w=width, h=height, supports_streaming=True
                    )],
                    thumb=await uploader.upload_file(thumb_file) if thumb_file else None
                ))
                
                await uploader.send_file(TARGET_CHANNEL_ID, media_group)
                
                # Send additional parts if any
                if len(video_parts) > 1:
                    for i in range(1, len(video_parts)):
                        part = video_parts[i]
                        duration, width, height = get_video_info(part)
                        caption = f"🎬 **{video_title} (Part {i+1}/{len(video_parts)})**"
                        await uploader.send_file(
                            TARGET_CHANNEL_ID, part, caption=caption,
                            attributes=[types.DocumentAttributeVideo(duration=duration, w=width, h=height, supports_streaming=True)]
                        )

            # MODE: Separate Album then Video
            elif POST_MODE == 'both':
                if screenshots:
                    photo_caption = f"📸 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}"
                    await uploader.send_file(TARGET_CHANNEL_ID, screenshots, caption=photo_caption, parse_mode='markdown')
                
                for i, part in enumerate(video_parts):
                    duration, width, height = get_video_info(part)
                    part_suffix = f" (Part {i+1}/{len(video_parts)})" if len(video_parts) > 1 else ""
                    video_caption = f"🎬 **{video_title}{part_suffix}**\n\n{VIDEO_CAPTION_TEMPLATE}"
                    await uploader.send_file(
                        TARGET_CHANNEL_ID, part, caption=video_caption,
                        thumb=thumb_file if i == 0 else None,
                        parse_mode='markdown', supports_streaming=True,
                        attributes=[types.DocumentAttributeVideo(duration=duration, w=width, h=height, supports_streaming=True)]
                    )

            # MODE: Album Only
            elif POST_MODE == 'album' and screenshots:
                photo_caption = f"📸 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}"
                await uploader.send_file(TARGET_CHANNEL_ID, screenshots, caption=photo_caption, parse_mode='markdown')

        send_progress("✅ Task Completed Successfully!")

    except Exception as e:
        error_msg = f"❌ **Critical Error:**\n\n`{str(e)}`"
        print(traceback.format_exc())
        send_progress(error_msg)
    finally:
        # Cleanup
        files_to_clean = [raw_video, final_video, thumbnail] + screenshots + video_parts
        for f in files_to_clean:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

if __name__ == '__main__':
    asyncio.run(main())
