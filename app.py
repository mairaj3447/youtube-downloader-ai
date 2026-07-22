import whisper
import sys
from flask import Flask, render_template, request, send_file, jsonify
from urllib.parse import urlparse, parse_qs
import subprocess
import os
import glob
import json
import re

COOKIES_FILE = os.environ.get("COOKIES_FILE", "/etc/secrets/cookies.txt")
FFMPEG_LOCATION = os.environ.get(
    "FFMPEG_LOCATION",
    r"C:\pythonproj\ffmpeg\bin"
)
app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_youtube_url(url):
    parsed = urlparse(url)
    if "youtu.be" in parsed.netloc:
        video_id = parsed.path.lstrip("/")
        return f"https://www.youtube.com/watch?v={video_id}"
    elif "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        v = qs.get("v")
        if v:
            return f"https://www.youtube.com/watch?v={v[0]}"
    return url.split("?")[0]

def run_yt_dlp(cmd):
    print("Running command:")
    print(" ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    print("Return code:", result.returncode)
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout

def download_audio(url):
    output_filename = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-f",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--ffmpeg-location",
        FFMPEG_LOCATION,
        "-o",
        output_filename
    ]

    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        cmd.extend([
            "--cookies",
            COOKIES_FILE
        ])

    cmd.append(url)

    run_yt_dlp(cmd)

    list_of_files = glob.glob(os.path.join(DOWNLOAD_FOLDER, "*.mp3"))

    if list_of_files:
        latest_file = max(list_of_files, key=os.path.getmtime)
        return latest_file

    return None


def download_video(url, quality=None):
    output_filename = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "--ffmpeg-location",
        FFMPEG_LOCATION,
        "--extractor-args",
        "youtube:player_client=android",
        "-o",
        output_filename
    ]

    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        cmd.extend([
            "--cookies",
            COOKIES_FILE
        ])

    cmd.append(url)

    run_yt_dlp(cmd)

    list_of_files = glob.glob(os.path.join(DOWNLOAD_FOLDER, "*.mp4"))

    if list_of_files:
        latest_file = max(list_of_files, key=os.path.getmtime)
        return latest_file

    return None

def get_youtube_transcript_improved(video_id):
    """Improved transcript extraction using multiple methods"""
    try:
        print(f"🔄 Attempting to extract transcript for video: {video_id}")
        
        # Method 1: Try to get auto-generated subtitles
        cmd1 = [
            'yt-dlp',
            '--skip-download',
            '--write-auto-sub',
            '--sub-format', 'txt',
            '--sub-lang', 'en',
            '--print-json',
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        
        result1 = subprocess.run(cmd1, capture_output=True, text=True)
        
        # Check if auto-sub file was created
        auto_sub_files = glob.glob('*[Aa]uto*[Ss]ub*.txt') + glob.glob('*[Ss]ubtitle*.txt')
        
        if auto_sub_files:
            latest_sub = max(auto_sub_files, key=os.path.getmtime)
            with open(latest_sub, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Clean up
            for sub_file in auto_sub_files:
                os.remove(sub_file)
            
            if content.strip():
                print("✅ Found auto-generated subtitles")
                return content
        
        # Method 2: Try manual subtitles
        cmd2 = [
            'yt-dlp',
            '--skip-download',
            '--write-sub',
            '--sub-format', 'txt',
            '--sub-lang', 'en',
            '--print-json',
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        
        manual_sub_files = glob.glob('*[Mm]anual*[Ss]ub*.txt') + glob.glob('*en*.txt')
        
        if manual_sub_files:
            latest_sub = max(manual_sub_files, key=os.path.getmtime)
            with open(latest_sub, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Clean up
            for sub_file in manual_sub_files:
                os.remove(sub_file)
            
            if content.strip():
                print("✅ Found manual subtitles")
                return content
        
        # Method 3: Try to extract from video description/commentary
        print("❌ No subtitles found, trying alternative methods...")
        return None
        
    except Exception as e:
        print(f"❌ Transcript extraction error: {e}")
        # Clean up any leftover files
        for pattern in ['*.txt', '*[Ss]ub*']:
            for file in glob.glob(pattern):
                try:
                    os.remove(file)
                except:
                    pass
        return None

def get_video_metadata(url):
    try:
        cmd = [
            'yt-dlp',
            '--skip-download',
            '--print-json',
            url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout.splitlines()[-1])
        title = info.get("title", "")
        description = info.get("description", "")
        uploader = info.get("uploader", "")
        duration = info.get("duration", "")
        
        # Get actual video content info
        categories = info.get("categories", [])
        tags = info.get("tags", [])
        
        # Clean description - remove promotional content
        clean_description = description
        if "Check out our courses:" in description:
            clean_description = description.split("Check out our courses:")[0].strip()
        if "Coupon:" in description:
            clean_description = clean_description.split("Coupon:")[0].strip()
        
        metadata = {
            "title": title,
            "uploader": uploader,
            "duration": f"{duration // 60} minutes" if duration else "Unknown",
            "description": clean_description[:300],  # Limit description
            "categories": categories,
            "tags": tags[:5]  # First 5 tags
        }
        return metadata
    except Exception as e:
        print("Metadata error:", e)
        return None

def create_content_summary(metadata):
    """Create a meaningful summary from video metadata"""
    summary_parts = []
    summary_parts.append("🎬 **Video Content Summary**")
    summary_parts.append("")
    
    summary_parts.append(f"**Title:** {metadata['title']}")
    summary_parts.append(f"**Instructor:** {metadata['uploader']}")
    summary_parts.append(f"**Duration:** {metadata['duration']}")
    summary_parts.append("")
    
    summary_parts.append("**About this video:**")
    if metadata['description']:
        summary_parts.append(metadata['description'])
    else:
        # Create summary from title and categories
        if "Python" in metadata['title'] and "Functions" in metadata['title']:
            summary_parts.append("This appears to be a Python programming tutorial focusing on functions.")
            summary_parts.append("It likely covers:")
            summary_parts.append("• Function definition and syntax")
            summary_parts.append("• Parameters and arguments")
            summary_parts.append("• Return statements")
            summary_parts.append("• Function invocation")
    
    if metadata.get('tags'):
        summary_parts.append("")
        summary_parts.append("**Topics covered:**")
        for tag in metadata['tags']:
            summary_parts.append(f"• {tag}")
    
    summary_parts.append("")
    summary_parts.append("💡 *Note: Full transcript not available. This summary is based on video metadata.*")
    
    return "\n".join(summary_parts)

def transcribe_video(url):
    temp_audio = os.path.join(DOWNLOAD_FOLDER, "temp_audio.%(ext)s")

    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-f",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--ffmpeg-location",
        FFMPEG_LOCATION,
        "-o",
        temp_audio,
    ]
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
            cmd.extend([
                "--cookies",
                COOKIES_FILE
            ])

    cmd.append(url)
    run_yt_dlp(cmd)

    files = glob.glob(os.path.join(DOWNLOAD_FOLDER, "*.mp3"))
    print("MP3 Files:", files)

    if not files:
        raise Exception("No MP3 file found!")

    audio_file = files[0]
    print("Using:", audio_file)

    model = whisper.load_model("base")
    print("Model loaded")

    result = model.transcribe(
    audio_file,
    task="translate"
    )
    print("Transcription finished")
    return result["text"]

def get_video_summary(url):
    parsed = urlparse(url)
    if "youtu.be" in parsed.netloc:
        video_id = parsed.path.lstrip("/")
    elif "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        video_id = qs.get("v", [None])[0]
    else:
        return "❌ Invalid YouTube URL."

    print(f"🎯 Processing: {video_id}")
    
    # Try to get transcript with improved method
    transcript = get_youtube_transcript_improved(video_id)
    if transcript and len(transcript.strip()) > 100:  # Ensure we have meaningful content
        print("✅ Meaningful transcript found")
        # Create a simple content preview
        preview = transcript[:500] + "..." if len(transcript) > 500 else transcript
        word_count = len(transcript.split())
        
        summary = f"""🎬 **Video Transcript Preview**

**Content Sample:**
{preview}

**Transcript Statistics:**
• Total words: {word_count}
• Content available: Full transcript

💡 *This is a preview of the actual video content.*"""
        return summary
    else:
        print("❌ No transcript available, creating metadata summary...")
        metadata = get_video_metadata(url)
        if not metadata:
            return "❌ Unable to retrieve video information."
        
        return create_content_summary(metadata)

@app.route('/')
def index():
    return render_template('main.html', summary=None, url="")

@app.route('/process', methods=['POST'])
def process():
    url = sanitize_youtube_url(request.form['url'])
    action = request.form.get('action')
    download_type = request.form.get('type', 'video')
    
    try:
        if action == 'download':
            if download_type == 'audio':
                file_path = download_audio(url)
            else:
                quality = request.form.get('quality')
                file_path = download_video(url, quality)
                
            if file_path and os.path.exists(file_path):
                return send_file(file_path, as_attachment=True)
            else:
                return "❌ Download failed - file not found", 500
                
        elif action == 'summarize':
            summary = transcribe_video(url)
            return render_template('main.html', summary=summary, url=url)
            
        else:
            return "❌ Invalid action", 400
            
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

@app.route('/preview', methods=['POST'])
def preview():
    url = sanitize_youtube_url(request.form['url'])
    try:
        cmd = [
            'yt-dlp',
            '--skip-download',
            '--print-json',
            url
        ]
        output = run_yt_dlp(cmd)
        info = json.loads(output.splitlines()[-1])
        title = info.get('title', 'Unknown Title')
        thumbnail = info.get('thumbnail', '')
        return jsonify({"title": title, "thumbnail": thumbnail})
    except Exception as e:
        return jsonify({"error": "Could not fetch video info"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
