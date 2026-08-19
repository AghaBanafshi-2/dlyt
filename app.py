# app.py ریشه اصلی
from flask import Flask, request, jsonify, send_file, render_template_string
import yt_dlp
import os
import re
import time
import threading
import requests
import json
import tempfile

app = Flask(__name__)

# ==================== تنظیمات ====================
# در Railway از پورت 8080 استفاده کن
PORT = int(os.environ.get('PORT', 8080))
PROXY = None  # در Railway معمولاً نیازی به پروکسی نیست

# استفاده از پوشه موقت در Railway
DOWNLOAD_FOLDER = tempfile.mkdtemp()
print(f"📁 پوشه دانلود: {DOWNLOAD_FOLDER}")

# ==================== توابع ====================
def get_video_info(url):
    """گرفتن اطلاعات ویدیو"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'retries': 3,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
        if PROXY:
            ydl_opts['proxy'] = PROXY
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            duration = info.get('duration', 0)
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            seconds = duration % 60
            
            if hours > 0:
                duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                duration_str = f"{minutes}:{seconds:02d}"
            
            # گرفتن فرمت‌های موجود
            formats = []
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    formats.append({
                        'quality': f.get('format_note', 'Unknown'),
                        'resolution': f.get('resolution', 'Unknown'),
                        'ext': f.get('ext', 'mp4'),
                        'filesize': f.get('filesize', 0),
                        'format_id': f.get('format_id', '')
                    })
            
            return {
                'success': True,
                'title': info.get('title', 'Unknown'),
                'duration': duration_str,
                'views': info.get('view_count', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'video_id': info.get('id', ''),
                'description': info.get('description', '')[:200],
                'formats': formats[:10]
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)[:100]
        }

def download_video(url, quality='high', format_type='video'):
    """دانلود ویدیو"""
    try:
        print(f"📥 شروع دانلود: {url}")
        
        opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'socket_timeout': 30,
            'retries': 5,
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s_%(id)s.%(ext)s'),
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
        }
        
        if PROXY:
            opts['proxy'] = PROXY
        
        # تنظیم کیفیت
        if format_type == 'video':
            if quality == 'high':
                opts['format'] = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
            elif quality == 'medium':
                opts['format'] = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
            elif quality == 'low':
                opts['format'] = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
            else:  # highest
                opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
            opts['merge_output_format'] = 'mp4'
        else:  # audio
            opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        # تابع پیشرفت
        def progress_hook(d):
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', '0%').strip()
                speed = d.get('_speed_str', '0 KB/s').strip()
                print(f"⏳ {percent} - سرعت: {speed}")
            elif d['status'] == 'finished':
                print(f"✅ دانلود کامل شد")
        
        opts['progress_hooks'] = [progress_hook]
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if format_type == 'audio':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            # پیدا کردن فایل
            if not os.path.exists(filename):
                for file in os.listdir(DOWNLOAD_FOLDER):
                    if info.get('id') in file or info.get('title') in file:
                        filename = os.path.join(DOWNLOAD_FOLDER, file)
                        break
            
            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                return {
                    'success': True,
                    'filename': os.path.basename(filename),
                    'title': info.get('title', 'Unknown'),
                    'size': file_size,
                    'size_mb': f"{file_size / (1024 * 1024):.2f} MB"
                }
            else:
                return {'success': False, 'error': 'فایل پیدا نشد'}
                
    except Exception as e:
        return {'success': False, 'error': str(e)[:200]}

# ==================== HTML ====================
HTML = '''
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎬 دانلودر یوتیوب</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0f0f0f;
            min-height: 100vh;
            padding: 20px;
            direction: rtl;
            color: #fff;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: #1a1a1a;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.8);
            border: 1px solid #333;
        }
        h1 {
            text-align: center;
            color: #ff6b6b;
            font-size: 2.5em;
            margin-bottom: 5px;
        }
        h1 span { color: #fff; }
        .subtitle {
            text-align: center;
            color: #888;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .input-area {
            background: #242424;
            border-radius: 15px;
            padding: 20px;
            margin: 20px 0;
        }
        .input-area input {
            width: 100%;
            padding: 15px;
            border: 2px solid #333;
            border-radius: 10px;
            font-size: 16px;
            direction: ltr;
            background: #1a1a1a;
            color: #fff;
        }
        .input-area input:focus {
            outline: none;
            border-color: #ff6b6b;
        }
        .input-area input::placeholder {
            color: #666;
        }
        .options {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin: 15px 0;
        }
        .options select {
            padding: 12px;
            border: 2px solid #333;
            border-radius: 10px;
            font-size: 14px;
            background: #1a1a1a;
            color: #fff;
            cursor: pointer;
        }
        .options select:focus {
            outline: none;
            border-color: #ff6b6b;
        }
        .options select option {
            background: #1a1a1a;
        }
        .download-btn {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 10px;
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .download-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(238,90,36,0.4);
        }
        .download-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .info-box {
            background: #242424;
            border-radius: 15px;
            padding: 20px;
            margin: 20px 0;
            display: none;
        }
        .info-box.show { display: block; }
        .info-box img {
            max-width: 100%;
            border-radius: 10px;
            margin-bottom: 15px;
        }
        .info-box h2 {
            font-size: 18px;
            color: #fff;
            margin-bottom: 10px;
        }
        .info-box .meta {
            color: #888;
            font-size: 14px;
        }
        .status-text {
            text-align: center;
            color: #888;
            margin: 10px 0;
            display: none;
            font-weight: bold;
        }
        .status-text.show { display: block; }
        .status-text.success { color: #28a745; }
        .status-text.error { color: #dc3545; }
        .footer {
            text-align: center;
            margin-top: 20px;
            color: #555;
            font-size: 12px;
        }
        .loader {
            border: 3px solid #333;
            border-radius: 50%;
            border-top: 3px solid #ff6b6b;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
            display: none;
        }
        .loader.show { display: block; }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .format-list {
            margin-top: 15px;
            padding: 10px;
            background: #1a1a1a;
            border-radius: 10px;
        }
        .format-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 12px;
            border-bottom: 1px solid #333;
            color: #aaa;
            font-size: 13px;
        }
        .format-item:last-child { border-bottom: none; }
        .format-item .quality { color: #ff6b6b; }
        @media (max-width: 600px) {
            .container { padding: 15px; }
            h1 { font-size: 1.8em; }
            .options { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>🎬 <span>دانلودر</span> یوتیوب</h1>
    <p class="subtitle">⚡ شبیه نیوپایپ - بدون فیلتر و سریع</p>
    
    <div class="input-area">
        <input type="text" id="urlInput" placeholder="لینک یوتیوب رو اینجا بذار...">
        <div class="options">
            <select id="qualitySelect">
                <option value="high">🎥 کیفیت بالا (1080p)</option>
                <option value="medium">🎥 کیفیت متوسط (720p)</option>
                <option value="low">🎥 کیفیت پایین (480p)</option>
                <option value="highest">🎥 بهترین کیفیت</option>
            </select>
            <select id="typeSelect">
                <option value="video">🎬 ویدیو</option>
                <option value="audio">🎵 فقط صدا (MP3)</option>
            </select>
        </div>
        <button class="download-btn" onclick="startDownload()">📥 دانلود</button>
    </div>
    
    <div class="loader" id="loader"></div>
    <div class="status-text" id="statusText">⏳ در حال پردازش...</div>
    
    <div class="info-box" id="infoBox">
        <img id="thumbnail" src="">
        <h2 id="title"></h2>
        <div class="meta">
            <span id="uploader"></span> | 
            <span id="duration"></span> | 
            <span id="views"></span>
        </div>
        <div class="format-list" id="formatList"></div>
    </div>
    
    <div class="footer">ساخته شده با ❤️ | دیپلوی شده روی Railway</div>
</div>

<script>
let isDownloading = false;

async function startDownload() {
    if (isDownloading) return;
    
    const url = document.getElementById('urlInput').value.trim();
    if (!url) {
        alert('❌ لطفاً لینک یوتیوب رو وارد کن!');
        return;
    }
    
    const quality = document.getElementById('qualitySelect').value;
    const type = document.getElementById('typeSelect').value;
    
    isDownloading = true;
    const btn = document.querySelector('.download-btn');
    btn.disabled = true;
    btn.textContent = '⏳ در حال دانلود...';
    
    document.getElementById('loader').classList.add('show');
    const statusText = document.getElementById('statusText');
    statusText.classList.add('show');
    statusText.textContent = '🔄 در حال دریافت اطلاعات...';
    statusText.className = 'status-text show';
    
    try {
        // دریافت اطلاعات
        const infoResponse = await fetch('/api/info', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: url})
        });
        const infoData = await infoResponse.json();
        
        if (infoData.success) {
            // نمایش اطلاعات
            document.getElementById('infoBox').classList.add('show');
            document.getElementById('thumbnail').src = infoData.thumbnail || '';
            document.getElementById('title').textContent = infoData.title || 'Unknown';
            document.getElementById('uploader').textContent = '👤 ' + (infoData.uploader || 'Unknown');
            document.getElementById('duration').textContent = '⏱ ' + (infoData.duration || '0:00');
            document.getElementById('views').textContent = '👁 ' + (infoData.views ? infoData.views.toLocaleString() : '0');
            
            // نمایش فرمت‌ها
            const formatList = document.getElementById('formatList');
            formatList.innerHTML = '<div style="color:#888;margin-bottom:10px;">📋 فرمت‌های موجود:</div>';
            if (infoData.formats && infoData.formats.length > 0) {
                infoData.formats.slice(0, 5).forEach(f => {
                    const div = document.createElement('div');
                    div.className = 'format-item';
                    div.innerHTML = `
                        <span class="quality">${f.quality || 'Unknown'}</span>
                        <span>${f.resolution || ''} - ${f.ext || 'mp4'}</span>
                    `;
                    formatList.appendChild(div);
                });
            }
        }
        
        // شروع دانلود
        statusText.textContent = '⏳ در حال دانلود... (ممکنه چند دقیقه طول بکشه)';
        
        const downloadResponse = await fetch('/api/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                url: url,
                quality: quality,
                type: type
            })
        });
        
        const downloadData = await downloadResponse.json();
        
        if (downloadData.success) {
            statusText.textContent = '✅ دانلود کامل شد! حجم: ' + (downloadData.size_mb || 'نامشخص');
            statusText.className = 'status-text show success';
            
            // دانلود فایل
            setTimeout(() => {
                window.location.href = '/download/' + downloadData.filename;
            }, 1000);
            
        } else {
            statusText.textContent = '❌ خطا: ' + downloadData.error;
            statusText.className = 'status-text show error';
        }
        
    } catch (error) {
        statusText.textContent = '❌ خطا: ' + error.message;
        statusText.className = 'status-text show error';
        console.error('Error:', error);
    }
    
    document.getElementById('loader').classList.remove('show');
    isDownloading = false;
    btn.disabled = false;
    btn.textContent = '📥 دانلود';
}
</script>
</body>
</html>
'''

# ==================== مسیرها ====================
@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/info', methods=['POST'])
def api_info():
    try:
        data = request.get_json()
        url = data.get('url', '')
        if not url:
            return jsonify({'success': False, 'error': 'لینک وارد نشده'})
        
        result = get_video_info(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download', methods=['POST'])
def api_download():
    try:
        data = request.get_json()
        url = data.get('url', '')
        quality = data.get('quality', 'high')
        type_ = data.get('type', 'video')
        
        if not url:
            return jsonify({'success': False, 'error': 'لینک وارد نشده'})
        
        result = download_video(url, quality, type_)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download/<path:filename>')
def download_file(filename):
    try:
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        return 'فایل پیدا نشد', 404
    except Exception as e:
        return f'خطا: {str(e)}', 500

# ==================== اجرا ====================
if __name__ == '__main__':
    print("="*60)
    print("🎬 دانلودر یوتیوب - Railway")
    print("="*60)
    print(f"🌐 آدرس: http://localhost:{PORT}")
    print(f"📁 پوشه دانلود: {DOWNLOAD_FOLDER}")
    print("="*60)
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
