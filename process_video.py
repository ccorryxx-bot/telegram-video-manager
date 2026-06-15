import os
import sys
import json
import asyncio
import cv2
import yt_dlp
from telethon import TelegramClient, events
from telethon.tl.types import InputMediaPhoto

# Config from environment (GitHub Actions Secrets or Payload)
API_ID = os.environ.get('TG_API_ID')
API_HASH = os.environ.get('TG_API_HASH')
BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
CHANNEL_ID = int(os.environ.get('TG_CHANNEL_ID', 0))

# Get inputs from the repository dispatch payload
event_payload = os.environ.get('GITHUB_EVENT_PAYLOAD')
payload_data = json.loads(event_payload) if event_payload else {}
client_payload = payload_data.get('client_payload', {})

VIDEO_URL = client_payload.get('video_url')
PHOTO_CAPTION_TEMPLATE = client_payload.get('photo_caption', "#Video #PremiumV2")
VIDEO_CAPTION_TEMPLATE = client_payload.get('video_caption', "# Full Video Outta")
NUM_PHOTOS = int(client_payload.get('num_photos', 4))

async def main():
    if not VIDEO_URL:
        print("No video URL provided.")
        return

    print(f"Processing video: {VIDEO_URL}")
    
    # 1. Download Video
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'video.mp4',
        'quiet': True,
        'no_warnings': True,
    }
    
    video_title = "Video"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(VIDEO_URL, download=True)
        video_title = info.get('title', 'Video')

    # 2. Extract Screenshots
    cap = cv2.VideoCapture('video.mp4')
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps
    
    screenshots = []
    for i in range(1, NUM_PHOTOS + 1):
        # Pick frames at regular intervals
        frame_pos = int((total_frames / (NUM_PHOTOS + 1)) * i)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ret, frame = cap.read()
        if ret:
            filename = f'screenshot_{i}.jpg'
            cv2.imwrite(filename, frame)
            screenshots.append(filename)
    cap.release()

    # 3. Upload to Telegram
    async with TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN) as client:
        # Upload Photos as Album
        photo_caption = f"🎬 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}"
        media = [InputMediaPhoto(open(s, 'rb')) for s in screenshots]
        # Only add caption to the first photo
        if media:
            media[0] = InputMediaPhoto(open(screenshots[0], 'rb'), caption=photo_caption, parse_mode='markdown')
        
        await client.send_file(CHANNEL_ID, media)
        print("Photos uploaded.")

        # Upload Video
        video_caption = f"🎬 **{video_title}**\n\n{VIDEO_CAPTION_TEMPLATE}"
        
        def progress_callback(current, total):
            print(f'Uploading video: {current * 100 / total:.1f}%')

        await client.send_file(
            CHANNEL_ID, 
            'video.mp4', 
            caption=video_caption, 
            parse_mode='markdown',
            supports_streaming=True,
            progress_callback=progress_callback
        )
        print("Video uploaded.")

if __name__ == '__main__':
    asyncio.run(main())
