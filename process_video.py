import os
import sys
import asyncio
import cv2
import re
import subprocess
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeVideo

# Config from Environment
API_ID = int(os.getenv('TG_API_ID'))
API_HASH = os.getenv('TG_API_HASH')
BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID'))
VIDEO_URL = os.getenv('VIDEO_URL')
SESSION_STRING = os.getenv('TG_SESSION')

async def main():
    print(f"Processing Video: {VIDEO_URL}")
    video_file = "video.mp4"
    title = "Video File"
    
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()

    # Check if it's a Telegram Link
    tg_match = re.match(r'https?://t\.me/([^/]+)/(\d+)', VIDEO_URL)
    
    if tg_match:
        print("Telegram Link Detected. Downloading via Telethon...")
        channel_username = tg_match.group(1)
        message_id = int(tg_match.group(2))
        
        try:
            # Download directly from Telegram
            msg = await client.get_messages(channel_username, ids=message_id)
            if msg and msg.media:
                await client.download_media(msg, video_file)
                title = msg.text[:50] if msg.text else f"Telegram Video {message_id}"
            else:
                print("No media found in the Telegram message.")
                await client.disconnect()
                return
        except Exception as e:
            print(f"Error downloading from Telegram: {e}")
            await client.disconnect()
            return
    else:
        # 1. Download Video using yt-dlp for non-telegram links
        print("Non-Telegram Link. Downloading via yt-dlp...")
        subprocess.run(["yt-dlp", "-o", video_file, VIDEO_URL])
        try:
            title = subprocess.check_output(["yt-dlp", "--get-title", VIDEO_URL]).decode().strip()
        except:
            title = "Video File"

    if not os.path.exists(video_file):
        print("Download failed")
        await client.disconnect()
        return

    # 2. Take 4 Screenshots using OpenCV
    cap = cv2.VideoCapture(video_file)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0: fps = 24
    
    screenshots = []
    for i in range(1, 5):
        frame_no = int(total_frames * (i * 0.2))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if ret:
            name = f"ss_{i}.jpg"
            cv2.imwrite(name, frame)
            screenshots.append(name)
    cap.release()

    # 3. Prepare Caption
    caption = f"🎬 **{title}**\n\n📌 Video Source: {VIDEO_URL}\n\n#Video #Manager"

    # 4. Upload to Telegram
    print("Uploading to Telegram...")
    # Upload screenshots as a group
    if screenshots:
        await client.send_file(CHANNEL_ID, screenshots, caption=caption)
    
    # Upload Video file
    await client.send_file(CHANNEL_ID, video_file, caption="Full Video File", supports_streaming=True)
    
    await client.disconnect()
    print("Upload Complete")

if __name__ == "__main__":
    asyncio.run(main())
