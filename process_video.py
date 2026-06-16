import os
import sys
import asyncio
import cv2
import requests
from telethon import TelegramClient

# Environment Variables
API_ID = int(os.environ.get('API_ID', '0'))
API_HASH = os.environ.get('API_HASH', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
VIDEO_URL = os.environ.get('VIDEO_URL', '')
PHOTO_CAPTION_TEMPLATE = os.environ.get('PHOTO_CAPTION', '#Video #PremiumV2')
VIDEO_CAPTION_TEMPLATE = os.environ.get('VIDEO_CAPTION', '# Full Video Outta')
NUM_PHOTOS = int(os.environ.get('NUM_PHOTOS', '4'))

# Robust Channel ID parsing
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

async def main():
    if not VIDEO_URL:
        print("No VIDEO_URL provided.")
        return

    print(f"Processing video for Channel {TARGET_CHANNEL_ID}: {VIDEO_URL}")
    video_path = 'video.mp4'
    video_title = "Premium Video"

    # 1. Download Video
    try:
        if 't.me/' in VIDEO_URL:
            print("Telegram link detected. Using Telethon for download...")
            downloader = TelegramClient('bot_downloader', API_ID, API_HASH)
            await downloader.start(bot_token=BOT_TOKEN)
            async with downloader:
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
            r = requests.get(VIDEO_URL, stream=True, timeout=60)
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        print(f"Download Error: {e}")
        return

    # 2. Extract Screenshots
    screenshots = []
    if os.path.exists(video_path):
        try:
            print("Extracting screenshots...")
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                print("Error: Could not read video frames.")
                cap.release()
                return
                
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

        # 3. Upload to Telegram
        if screenshots or os.path.exists(video_path):
            try:
                print("Uploading to Telegram...")
                uploader = TelegramClient('bot_uploader', API_ID, API_HASH)
                await uploader.start(bot_token=BOT_TOKEN)
                async with uploader:
                    # Upload Photos as Album
                    if screenshots:
                        photo_caption = f"🎬 **{video_title}**\n\n{PHOTO_CAPTION_TEMPLATE}"
                        await uploader.send_file(TARGET_CHANNEL_ID, screenshots, caption=photo_caption, parse_mode='markdown')
                        print(f"Photos uploaded.")

                    # Upload Video
                    if os.path.exists(video_path):
                        video_caption = f"🎬 **{video_title}**\n\n{VIDEO_CAPTION_TEMPLATE}"
                        await uploader.send_file(
                            TARGET_CHANNEL_ID, 
                            video_path, 
                            caption=video_caption, 
                            parse_mode='markdown',
                            supports_streaming=True
                        )
                        print("Video uploaded successfully.")
            except Exception as e:
                print(f"Upload Error: {e}")

    # Cleanup
    if os.path.exists(video_path):
        os.remove(video_path)
    for s in screenshots:
        if os.path.exists(s):
            os.remove(s)

if __name__ == '__main__':
    asyncio.run(main())
