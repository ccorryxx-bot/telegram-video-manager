import os
import sys
import asyncio
import cv2
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
import subprocess

# Config from Environment
API_ID = int(os.getenv('TG_API_ID'))
API_HASH = os.getenv('TG_API_HASH')
BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID'))
VIDEO_URL = os.getenv('VIDEO_URL')
SESSION_STRING = os.getenv('TG_SESSION') # This will be added later

async def main():
    print(f"Processing Video: {VIDEO_URL}")
    
    # 1. Download Video using yt-dlp
    video_file = "video.mp4"
    subprocess.run(["yt-dlp", "-o", video_file, VIDEO_URL])
    
    if not os.path.exists(video_file):
        print("Download failed")
        return

    # 2. Take 4 Screenshots using OpenCV
    cap = cv2.VideoCapture(video_file)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps
    
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

    # 3. Get Video Info for Caption
    title = subprocess.check_output(["yt-dlp", "--get-title", VIDEO_URL]).decode().strip()
    caption = f"🎬 **{title}**\n\n📌 Video Source: {VIDEO_URL}\n\n#Video #Manager"

    # 4. Upload to Telegram using Telethon (User Session)
    # Note: We need a session string for persistent login without phone code
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()
    
    # Upload screenshots as a group
    await client.send_file(CHANNEL_ID, screenshots, caption=caption)
    
    # Upload Video file
    await client.send_file(CHANNEL_ID, video_file, caption="Full Video File", supports_streaming=True)
    
    await client.disconnect()
    print("Upload Complete")

if __name__ == "__main__":
    asyncio.run(main())
