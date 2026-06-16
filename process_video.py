import os
import sys
import asyncio
import cv2
import subprocess
import json
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

async def main():
    if not VIDEO_URL:
        print("No VIDEO_URL provided.")
        return

    print(f"Processing: {VIDEO_URL} (Mode: {POST_MODE})")
    raw_video = 'raw_video.mp4'
    final_video = 'final_video.mp4'
    video_title = "Premium Video"

    # 1. Download using yt-dlp (Universal Downloader)
    try:
        print("Downloading using yt-dlp...")
        # yt-dlp handles Telegram, YouTube, and many other sites
        cmd = [
            'yt-dlp', 
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4', 
            '--merge-output-format', 'mp4',
            '-o', raw_video,
            VIDEO_URL
        ]
        subprocess.run(cmd, check=True)
        
        # Get title
        title_cmd = ['yt-dlp', '--get-title', VIDEO_URL]
        title_res = subprocess.run(title_cmd, capture_output=True, text=True)
        if title_res.returncode == 0:
            video_title = title_res.stdout.strip()
    except Exception as e:
        print(f"Download Error: {e}")
        return

    if not os.path.exists(raw_video):
        print("Download failed: File not found.")
        return

    # 2. Convert to Telegram-compatible format (H.264/AAC)
    try:
        print("Converting to Telegram-compatible format...")
        convert_cmd = [
            'ffmpeg', '-y', '-i', raw_video,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-pix_fmt', 'yuv420p', # Critical for compatibility
            final_video
        ]
        subprocess.run(convert_cmd, check=True)
    except Exception as e:
        print(f"Conversion Error: {e}. Using raw video as fallback.")
        final_video = raw_video

    # 3. Extract Screenshots
    screenshots = []
    if os.path.exists(final_video) and POST_MODE in ['album', 'both']:
        try:
            print("Extracting screenshots...")
            cap = cv2.VideoCapture(final_video)
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

    # 4. Upload to Telegram with Metadata
    try:
        print("Uploading to Telegram...")
        uploader = TelegramClient('bot_uploader', API_ID, API_HASH)
        await uploader.start(bot_token=BOT_TOKEN)
        async with uploader:
            duration, width, height = get_video_info(final_video)
            
            if POST_MODE == 'album' and screenshots:
                photo_caption = f"📸 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}"
                await uploader.send_file(TARGET_CHANNEL_ID, screenshots, caption=photo_caption, parse_mode='markdown')
            
            elif POST_MODE == 'video' and os.path.exists(final_video):
                video_caption = f"🎬 **{video_title}**\n\n{VIDEO_CAPTION_TEMPLATE}"
                await uploader.send_file(
                    TARGET_CHANNEL_ID, 
                    final_video, 
                    caption=video_caption, 
                    parse_mode='markdown', 
                    supports_streaming=True,
                    attributes=[types.DocumentAttributeVideo(
                        duration=duration,
                        w=width,
                        h=height,
                        supports_streaming=True
                    )]
                )
            
            elif POST_MODE == 'both':
                if screenshots:
                    photo_caption = f"📸 **{video_title} (Preview)**\n\n{PHOTO_CAPTION_TEMPLATE}"
                    await uploader.send_file(TARGET_CHANNEL_ID, screenshots, caption=photo_caption, parse_mode='markdown')
                if os.path.exists(final_video):
                    video_caption = f"🎬 **{video_title} (Full Video)**\n\n{VIDEO_CAPTION_TEMPLATE}"
                    await uploader.send_file(
                        TARGET_CHANNEL_ID, 
                        final_video, 
                        caption=video_caption, 
                        parse_mode='markdown', 
                        supports_streaming=True,
                        attributes=[types.DocumentAttributeVideo(
                            duration=duration,
                            w=width,
                            h=height,
                            supports_streaming=True
                        )]
                    )
        print("Upload completed successfully.")
    except Exception as e:
        print(f"Upload Error: {e}")

    # Cleanup
    for f in [raw_video, final_video] + screenshots:
        if os.path.exists(f):
            os.remove(f)

if __name__ == '__main__':
    asyncio.run(main())
