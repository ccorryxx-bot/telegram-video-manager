import os
import sys
import asyncio
import cv2
import requests
from telethon import TelegramClient
from telethon.tl.types import InputMediaPhoto

# Environment Variables
API_ID = int(os.environ.get('API_ID', '0'))
API_HASH = os.environ.get('API_HASH', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
TARGET_CHANNEL_ID = int(os.environ.get('TARGET_CHANNEL_ID', '0'))
VIDEO_URL = os.environ.get('VIDEO_URL', '')
PHOTO_CAPTION_TEMPLATE = os.environ.get('PHOTO_CAPTION', '#Video #PremiumV2')
VIDEO_CAPTION_TEMPLATE = os.environ.get('VIDEO_CAPTION', '# Full Video Outta')
NUM_PHOTOS = int(os.environ.get('NUM_PHOTOS', '4'))

async def main():
    if not VIDEO_URL:
        print("No VIDEO_URL provided.")
        return

    print(f"Processing video for Channel {TARGET_CHANNEL_ID}: {VIDEO_URL}")
    video_path = 'video.mp4'
    video_title = "Premium Video"

    # 1. Download Video
    if 't.me/' in VIDEO_URL:
        print("Telegram link detected. Using Telethon for download...")
        downloader = TelegramClient('bot_downloader', API_ID, API_HASH)
        await downloader.start(bot_token=BOT_TOKEN)
        async with downloader:
            # Extract channel and message ID from t.me link
            parts = VIDEO_URL.split('/')
            channel_username = parts[-2]
            message_id = int(parts[-1])
            
            entity = await downloader.get_entity(channel_username)
            message = await downloader.get_messages(entity, ids=message_id)
            
            if message and message.video:
                print("Downloading video from Telegram...")
                await downloader.download_media(message.video, file=video_path)
                if message.text:
                    video_title = message.text[:50]
            else:
                print("No video found in Telegram message.")
                return
    else:
        print(f"Downloading video from URL: {VIDEO_URL}")
        r = requests.get(VIDEO_URL, stream=True)
        with open(video_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # 2. Extract Screenshots
    if os.path.exists(video_path):
        print("Extracting screenshots...")
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
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
        uploader = TelegramClient('bot_uploader', API_ID, API_HASH)
        await uploader.start(bot_token=BOT_TOKEN)
        async with uploader:
            # Upload Photos as Album
            photo_caption = f"🎬 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}"
            media = []
            for i, s in enumerate(screenshots):
                # Telethon's InputMediaPhoto uses 'file' instead of positional argument in some versions, 
                # but the standard way to send album with captions is using upload_file first or send_file with a list.
                # Actually, in Telethon, send_file with a list of files works as an album.
                media.append(s)
            
            if media:
                # To add caption to the first photo of the album in Telethon:
                # We can use the 'caption' parameter in send_file, it will apply to the whole album or the first photo.
                await uploader.send_file(TARGET_CHANNEL_ID, media, caption=photo_caption, parse_mode='markdown')
                print(f"Photos uploaded.")

            # Upload Video
            video_caption = f"🎬 **{video_title}**\n\n{VIDEO_CAPTION_TEMPLATE}"
            def progress_callback(current, total):
                if total > 0:
                    print(f'Uploading video: {current * 100 / total:.1f}%')
            
            await uploader.send_file(
                TARGET_CHANNEL_ID, 
                video_path, 
                caption=video_caption, 
                parse_mode='markdown',
                supports_streaming=True,
                progress_callback=progress_callback
            )
            print("Video uploaded successfully.")

    # Cleanup
    if os.path.exists(video_path):
        os.remove(video_path)
    for s in screenshots:
        if os.path.exists(s):
            os.remove(s)

if __name__ == '__main__':
    asyncio.run(main())
