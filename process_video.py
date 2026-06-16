import os
import sys
import json
import asyncio
import cv2
import yt_dlp
import re
from telethon import TelegramClient, events
from telethon.tl.types import InputMediaPhoto

# Config from environment
API_ID = int(os.environ.get('TG_API_ID'))
API_HASH = os.environ.get('TG_API_HASH')
BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')

# Get inputs from the repository dispatch payload
event_payload = os.environ.get('GITHUB_EVENT_PAYLOAD')
payload_data = json.loads(event_payload) if event_payload else {}
client_payload = payload_data.get('client_payload', {})
VIDEO_URL = client_payload.get('video_url')
PHOTO_CAPTION_TEMPLATE = client_payload.get('photo_caption', "#Video #PremiumV2")
VIDEO_CAPTION_TEMPLATE = client_payload.get('video_caption', "# Full Video Outta")
NUM_PHOTOS = int(client_payload.get('num_photos', 4))

TARGET_CHANNEL_ID = client_payload.get('target_channel_id')
if TARGET_CHANNEL_ID:
    try:
        TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID)
    except ValueError:
        TARGET_CHANNEL_ID = int(os.environ.get('TG_CHANNEL_ID', 0))
else:
    TARGET_CHANNEL_ID = int(os.environ.get('TG_CHANNEL_ID', 0))

async def main():
    if not VIDEO_URL or not TARGET_CHANNEL_ID:
        print("Missing required parameters.")
        return

    print(f"Processing video for Channel {TARGET_CHANNEL_ID}: {VIDEO_URL}")
    video_path = 'video.mp4'
    video_title = "Video"

    # 1. Download Video
    # Check if it's a Telegram link
    is_telegram = "t.me/" in VIDEO_URL
    
    if is_telegram:
        print("Telegram link detected. Using Telethon for download...")
        async with TelegramClient('bot_downloader', API_ID, API_HASH).start(bot_token=BOT_TOKEN) as client:
            # Parse channel and message ID from URL
            # Example: https://t.me/channel_name/123 or https://t.me/c/123456/789
            parts = VIDEO_URL.split('/')
            msg_id = int(parts[-1])
            peer = parts[-2]
            
            if peer == 'c': # Private channel
                peer = int("-100" + parts[-3])
            
            try:
                message = await client.get_messages(peer, ids=msg_id)
                if message and message.video:
                    print("Downloading video from Telegram...")
                    await client.download_media(message.video, file=video_path)
                    video_title = message.text[:50] if message.text else "Telegram Video"
                else:
                    print("No video found in the Telegram message.")
                    return
            except Exception as e:
                print(f"Error downloading from Telegram: {e}")
                return
    else:
        print("General link detected. Using yt-dlp...")
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': video_path,
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(VIDEO_URL, download=True)
                if info:
                    video_title = info.get('title', 'Video')
                else:
                    print("yt-dlp could not extract info.")
                    # Check if file was still downloaded (sometimes it happens even if extract_info returns None)
                    if not os.path.exists(video_path):
                        return
        except Exception as e:
            print(f"yt-dlp Error: {e}")
            if not os.path.exists(video_path):
                return

    if not os.path.exists(video_path):
        print("Video file not found after download attempt.")
        return

    # 2. Extract Screenshots
    print("Extracting screenshots...")
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames <= 0:
        print("Error: Could not read video frames.")
        cap.release()
    else:
        screenshots = []
        for i in range(1, NUM_PHOTOS + 1):
            frame_pos = int((total_frames / (NUM_PHOTOS + 1)) * i)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            ret, frame = cap.read()
            if ret:
                filename = f'screenshot_{i}.jpg'
                cv2.imwrite(filename, frame)
                screenshots.append(filename)
        cap.release()

        # 3. Upload to Telegram
        print("Uploading to Telegram...")
        async with TelegramClient('bot_uploader', API_ID, API_HASH).start(bot_token=BOT_TOKEN) as client:
            # Upload Photos as Album
            photo_caption = f"🎬 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}"
            media = []
            for i, s in enumerate(screenshots):
                if i == 0:
                    media.append(InputMediaPhoto(open(s, 'rb'), caption=photo_caption, parse_mode='markdown'))
                else:
                    media.append(InputMediaPhoto(open(s, 'rb')))
            
            if media:
                await client.send_file(TARGET_CHANNEL_ID, media)
                print(f"Photos uploaded.")

            # Upload Video
            video_caption = f"🎬 **{video_title}**\n\n{VIDEO_CAPTION_TEMPLATE}"
            def progress_callback(current, total):
                if total > 0:
                    print(f'Uploading video: {current * 100 / total:.1f}%')
            
            await client.send_file(
                TARGET_CHANNEL_ID, 
                video_path, 
                caption=video_caption, 
                parse_mode='markdown',
                supports_streaming=True,
                progress_callback=progress_callback
            )
            print(f"Video uploaded to {TARGET_CHANNEL_ID}.")

if __name__ == '__main__':
    asyncio.run(main())
