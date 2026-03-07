import os
import json
import io
import re
import uuid
import shutil
import zipfile
import tempfile
import datetime
import urllib.request
from flask import Flask, render_template_string, request, jsonify, send_file, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading
from functools import wraps

app = Flask(__name__)
CORS(app)
data_lock = threading.RLock()

# Security Token (Lớp trung gian bảo vệ)
CLIENT_TOKEN = "hai_auto_vip_pro_2026"

def require_client_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Client-Token')
        if not token or token != CLIENT_TOKEN:
            print(f"[!] Unauthorized attempt from: {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized client"}), 401
        return f(*args, **kwargs)
    return decorated_function
# Configure paths
BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
EXPORT_FOLDER = os.path.join(BASE_DIR, 'export')
BACKUP_FOLDER = os.path.join(BASE_DIR, 'history')
MAX_HISTORY_FILES = 100

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EXPORT_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)

DATA_FILE = "data.json"
LOG_FILE = "captured_videos.txt"

DEFAULT_DATA = {
    "settings": {},
    "chapters": [],
    "unassigned": [],
    "blocked_vids": [],
    "exercises_chapters": [],
    "exercises_unassigned": []
}

# ----------------- STATIC HTML TEMPLATE -----------------
# This template is used for the standalone, read-only encrypted export.
STATIC_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Khóa Học Toán - Bảo Mật</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="referrer" content="strict-origin-when-cross-origin" />
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        @keyframes pulse-border {
            0% { box-shadow: 0 0 0 0 rgba(255, 193, 7, 0.7); }
            70% { box-shadow: 0 0 0 15px rgba(255, 193, 7, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 193, 7, 0); }
        }
        .landscape-active {
            width: 90vw !important;
            height: 90vh !important;
            max-width: none !important;
            aspect-ratio: auto !important;
        }

        body { background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; height: 100vh; overflow: hidden; margin:0; }
        .sidebar { background: #ffffff; height: 100vh; overflow-y: auto; border-left: 1px solid #dee2e6; }
        .main-content { height: 100vh; overflow-y: auto; padding: 20px; background-color: #0f172a;}
        
        .folder-card { border: 1px solid #dee2e6; border-radius: 8px; margin-bottom: 12px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.05);}
        .folder-header { background: #f8fafc; border-bottom: 1px solid #e2e8f0; padding: 10px; font-weight: bold; display: flex; align-items: center; border-radius: 8px 8px 0 0;}
        
        .subfolder-card { border: 1px dashed #cbd5e1; margin: 4px; background: #f8fafc; border-radius: 6px; }
        .subfolder-header { background: #e2e8f0; padding: 6px 10px; display: flex; align-items: center; border-radius: 6px 6px 0 0;}
        
        .item-row { cursor: pointer; border: 1px solid #f1f5f9; display: flex; align-items: center; padding: 8px 10px; transition: background 0.2s; margin: 4px; border-radius: 6px; background: white;}
        .item-row:hover { background: #e2e8f0; }
        .item-row.active-item { background: #dbeafe; border-left: 4px solid #2563eb; }
        
        .item-icon { font-size: 1.2rem; margin-right: 10px; color: #3b82f6; }
        .chapter-title { font-weight: bold; color: #1e293b; flex-grow: 1; word-break: break-word; min-width: 0; }
        .item-title { color: #334155; font-size: 0.95rem; flex-grow: 1; word-break: break-word; min-width: 0; padding-right: 8px;}
        .time-badge { font-size: 0.8rem; color: #64748b; margin-left: auto; white-space: nowrap; }
        
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #f1f1f1; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

        /* Removed Lock Screen CSS */

        @media (max-width: 768px) {
            body { height: auto; overflow: auto; background-color: #000; }
            .sidebar { height: auto; border-left: none; border-top: 1px solid #dee2e6; background: #fff !important; }
            .main-content { 
                height: auto; 
                padding: 10px 5px !important; 
                position: sticky; 
                top: 0; 
                z-index: 1000; 
                box-shadow: 0 4px 15px rgba(0,0,0,0.5); 
                background-color: #0f172a !important;
            }
            #viewer-placeholder { padding: 30px 0; }
            #viewer-placeholder i { font-size: 2.5rem !important; }
            #viewer-container { aspect-ratio: 16/9; width: 100%; height: auto !important; }
            #viewer-title { font-size: 0.95rem !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80%; }
            .d-flex.justify-content-between.align-items-center.mb-3 { margin-bottom: 8px !important; }
            
            /* Sửa lỗi che khuất trên màn hình lùn */
            .sidebar .p-3.bg-white { padding: 10px !important; }
            .sidebar h5 { font-size: 1rem !important; }
            
            /* Theater mode fix */
            body.theater-mode-active { overflow: hidden !important; }
            .main-content.theater-mode { position: fixed !important; z-index: 9999 !important; }
        }

    </style>
</head>
<body>
    <!-- Main Content -->
    <div class="container-fluid p-0" id="main-app">
        <div class="row m-0">
            <!-- Left col: Viewer -->
            <div class="col-md-9 main-content d-flex flex-column">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h3 id="viewer-title" class="text-white m-0">Chọn một bài giảng để xem</h3>
                    <div class="d-flex gap-2">
                        <a id="viewer-download-btn" href="#" download class="btn btn-outline-light btn-sm px-3" style="display: none;"><i class="bi bi-download me-1"></i>Tải file xuống</a>
                    </div>
                </div>
                <div class="flex-grow-1 w-100 d-flex flex-column bg-black rounded" style="position: relative; min-height: 0;">
                    <div id="viewer-container" class="w-100 flex-grow-1" style="display: none; position: relative;">
                        <!-- Player will be here -->
                    </div>
                    <div id="viewer-placeholder" class="flex-grow-1 d-flex flex-column align-items-center justify-content-center text-muted text-center">
                        <i class="bi bi-play-circle" style="font-size: 4rem;"></i>
                        <p class="mt-2">Player / Trình xem File</p>
                    </div>
                </div>
            </div>

            <!-- Right col: Playlist -->
            <div class="col-md-3 p-0 sidebar d-flex flex-column">
                <div class="p-3 bg-white border-bottom sticky-top shadow-sm z-index-1">
                    <h5 class="m-0 fw-bold" style="color: #1e293b;" id="course-title-display"><i class="bi bi-journal-bookmark-fill me-2 text-primary"></i>Danh sách bài học</h5>
                    <div class="text-muted small mt-1" id="course-author-display"></div>
                </div>
                
                <div class="flex-grow-1 overflow-auto p-3" id="playlist-container">
                    <div id="chapters-list"></div>
                    
                    <!-- Exercises Section -->
                    <div id="exercises-section">
                        <h6 class="mt-4 mb-2 text-primary fw-bold text-uppercase fs-7"><i class="bi bi-pencil-square me-2"></i>Phần Bài Tập</h6>
                        <div id="exercises-list"></div>
                    </div>

                    <h6 class="mt-4 mb-2 text-muted fw-bold text-uppercase fs-7" id="unassigned-header"><i class="bi bi-inbox me-2"></i>Chưa Phân Loại</h6>
                    <div class="card mb-3 border-0 bg-transparent" id="unassigned-card">
                        <div class="list-group list-group-flush" id="unassigned-list"></div>
                        <div class="list-group list-group-flush" id="exercises-unassigned-list"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Welcome Modal -->
    <div class="modal fade" id="welcomeModal" tabindex="-1" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered modal-lg">
        <div class="modal-content shadow-lg border-0">
          <div class="modal-header bg-primary text-white">
            <h5 class="modal-title fw-bold"><i class="bi bi-bell-fill me-2"></i>Thông Báo</h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body p-4" id="welcome-content" style="color: #334155; line-height: 1.6;">
          </div>
          <div class="modal-footer bg-light border-0">
            <button type="button" class="btn btn-primary px-4 fw-bold" data-bs-dismiss="modal">Đã Hiểu</button>
          </div>
        </div>
      </div>
    </div>



    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://www.youtube.com/iframe_api"></script>
    <script>
        // INJECTED PAYLOAD
        const appData = ___REPLACE_ME_DATA___;
        
        let currentItem = null;
        let ytPlayer = null;
        let isPlayerReady = false;

        document.addEventListener("DOMContentLoaded", function() {
            if(appData && appData.settings) {
                document.title = appData.settings.course_title ? appData.settings.course_title : "Khóa Học";
            }
            if(appData) {
                initApp();
            }
        });

        function isMobile() {
            return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768;
        }

        // YouTube IFrame API
        function onYouTubeIframeAPIReady() {
            console.log("YT API Ready");
        }

        function initYT(vidId) {
            isPlayerReady = false;
            let container = document.getElementById('viewer-container');
            container.innerHTML = `
                <div id="player-wrapper" style="width: 100%; height: 100%; position: relative;">
                    <div id="yt-player"></div>
                </div>
            `;
            
            ytPlayer = new YT.Player('yt-player', {
                height: '100%',
                width: '100%',
                videoId: vidId,
                playerVars: {
                    'autoplay': 1,
                    'controls': 1,
                    'modestbranding': 1,
                    'rel': 0,
                    'iv_load_policy': 3
                },
                events: {
                    'onReady': onPlayerReady,
                    'onStateChange': onPlayerStateChange
                }
            });
        }

        function onPlayerReady(event) {
            isPlayerReady = true;
            if (event.target.setVolume) event.target.setVolume(100);
        }

        function onPlayerStateChange(event) {
        }



        function initApp() {
            if(appData.settings) {
                if(appData.settings.course_title) {
                    const safeCourseTitle = appData.settings.course_title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
                    document.getElementById('course-title-display').innerHTML = `<i class="bi bi-journal-bookmark-fill me-2 text-primary"></i>${safeCourseTitle}`;
                }
                if(appData.settings.author_name) document.getElementById('course-author-display').innerText = `Tác giả: ${appData.settings.author_name}`;
            }

            const chapList = document.getElementById('chapters-list');
            const exList = document.getElementById('exercises-list');
            const unassignedList = document.getElementById('unassigned-list');
            const exUnassignedList = document.getElementById('exercises-unassigned-list');
            
            // Render Theory
            if (appData.chapters) {
                chapList.innerHTML = appData.chapters.map(chap => renderFolder(chap, false)).join('');
            }
            
            // Render Exercises
            if (appData.exercises_chapters && appData.exercises_chapters.length > 0) {
                exList.innerHTML = appData.exercises_chapters.map(chap => renderFolder(chap, false)).join('');
                document.getElementById('exercises-section').style.display = 'block';
            } else {
                document.getElementById('exercises-section').style.display = 'none';
            }
            
            // Render Unassigned Theory
            let hasUnassignedTheory = appData.unassigned && appData.unassigned.length > 0;
            if (hasUnassignedTheory) {
                unassignedList.innerHTML = appData.unassigned.map(item => renderAny(item)).join('');
            }
            
            // Render Unassigned Exercises
            let hasUnassignedEx = appData.exercises_unassigned && appData.exercises_unassigned.length > 0;
            if (hasUnassignedEx) {
                exUnassignedList.innerHTML = appData.exercises_unassigned.map(item => renderAny(item)).join('');
            }

            if (!hasUnassignedTheory && !hasUnassignedEx) {
                document.getElementById('unassigned-header').style.display = 'none';
                document.getElementById('unassigned-card').style.display = 'none';
            } else {
                document.getElementById('unassigned-header').style.display = 'block';
                document.getElementById('unassigned-card').style.display = 'block';
            }

            // Show Welcome Modal if configured
            if (appData.settings && appData.settings.welcome_message) {
                document.getElementById('welcome-content').innerHTML = appData.settings.welcome_message;
                var welcomeModal = new bootstrap.Modal(document.getElementById('welcomeModal'));
                welcomeModal.show();
            }
        }

        function renderAny(node, isSub = true) {
            if (!node.type) node.type = node.url ? 'file' : (node.yt_id ? 'video' : 'folder');
            if (node.type === 'folder') return renderFolder(node, isSub);
            return renderItem(node);
        }

        function renderFolder(folder, isSub) {
            let cardClass = isSub ? 'subfolder-card' : 'folder-card';
            let headerClass = isSub ? 'subfolder-header' : 'folder-header';
            let folderIcon = isSub ? '<i class="bi bi-folder2-open text-secondary me-2"></i>' : '<i class="bi bi-folder-fill text-warning me-2"></i>';
            let itemsHtml = (folder.items || []).map(item => renderAny(item, true)).join('');

            const safeFolderTitle = (folder.title || "Thư mục").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
            return `
                <div class="${cardClass}">
                    <div class="${headerClass}" style="cursor: pointer;" onclick="toggleCollapse('folder-body-${folder.id}', this)">
                        ${folderIcon}
                        <div class="chapter-title">${safeFolderTitle}</div>
                        <i class="bi bi-chevron-down text-muted ms-2"></i>
                    </div>
                    <div id="folder-body-${folder.id}" class="list-group list-group-flush" style="padding: 4px; display: none;">
                        ${itemsHtml}
                    </div>
                </div>
            `;
        }

        function renderItem(item) {
            let icon = item.type === 'video' ? '<i class="bi bi-play-btn-fill item-icon"></i>' : '<i class="bi bi-file-earmark-text-fill item-icon text-success"></i>';
            let timeInfo = item.time ? `<span class="time-badge">${item.time}</span>` : '';
            let defaultTitle = item.type === 'video' ? 'Video' : 'File đính kèm';
            // Important: we escape single quotes in id string
            let safeId = item.id.replace(/'/g, "\\'");
            
            const safeItemTitle = (item.title || defaultTitle).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
            return `
                <div class="item-row" id="item-row-${item.id}" onclick="viewItem('${safeId}')">
                    ${icon}
                    <div class="item-title">${safeItemTitle}</div>
                    ${timeInfo}
                </div>
            `;
        }

        function findItemInTree(id, list = null) {
            if (!list) list = appData.chapters.concat(appData.unassigned || []);
            for (let item of list) {
                if (item.id === id) return item;
                if (item.items) {
                    let found = findItemInTree(id, item.items);
                    if (found) return found;
                }
            }
            return null;
        }

        function viewItem(id) {
            let item = findItemInTree(id);
            if (!item || item.type === 'folder') return;
            currentItem = item;
            
            document.querySelectorAll('.item-row').forEach(r => r.classList.remove('active-item'));
            let activeRow = document.getElementById(`item-row-${id}`);
            if (activeRow) activeRow.classList.add('active-item');

            let placeholder = document.getElementById('viewer-placeholder');
            if (placeholder) {
                placeholder.classList.remove('d-flex');
                placeholder.classList.add('d-none');
                placeholder.style.setProperty('display', 'none', 'important');
            }
            let vc = document.getElementById('viewer-container');
            vc.style.display = 'block';
            vc.classList.add('h-100');
            
            const safeTitle = (item.title || "Bài giảng").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
            const safeSource = item.source ? item.source.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;") : '';
            titleSource = safeSource ? ` <span class="badge bg-secondary ms-2">${safeSource}</span>` : '';
            document.getElementById('viewer-title').innerHTML = safeTitle + titleSource;
            
            let dlBtn = document.getElementById('viewer-download-btn');
            let fsBtn = document.getElementById('fullscreen-btn');
            let ctrlBar = document.getElementById('vid-controls');
            
            if(fsBtn) fsBtn.style.display = 'inline-block';
            
            if (item.type === 'video' && item.yt_id) {
                if(dlBtn) dlBtn.style.display = 'none';
                initYT(item.yt_id);
            } else {

                if (item.type === 'file' && item.url) {
                    // Determine if url needs to be resolved locally.
                    // Normally it's /static/uploads/..., we can just use relative paths like ./static/uploads/...
                    let relativeUrl = "." + item.url;
                    if (!item.url.startsWith('/')) relativeUrl = "./" + item.url;
    
                    if(dlBtn) {
                         dlBtn.href = relativeUrl;
                         dlBtn.download = item.title || 'download';
                         dlBtn.style.display = 'inline-block';
                    }
    
                    if (item.url.toLowerCase().endsWith('.pdf')) {
                        vc.innerHTML = `<iframe src="${relativeUrl}" class="w-100 h-100 border-0" allowfullscreen></iframe>`;
                    } else if (item.url.match(/\.(jpeg|jpg|gif|png)$/i)) {
                         vc.innerHTML = `<div class="w-100 h-100 d-flex justify-content-center align-items-center bg-dark"><img src="${relativeUrl}" style="max-height: 100%; max-width: 100%;"></div>`;
                    } else if (item.url.match(/\.(mp4|webm)$/i)) {
                         vc.innerHTML = `<video src="${relativeUrl}" controls autoplay class="w-100 h-100 bg-dark" allowfullscreen></video>`;
                    } else {
                        vc.innerHTML = `
                            <div class="h-100 d-flex flex-column justify-content-center align-items-center bg-white text-dark rounded">
                                <i class="bi bi-file-earmark-arrow-down text-primary mb-3" style="font-size: 4rem;"></i>
                                <h5>Định dạng file không hỗ trợ xem trực tiếp</h5>
                                <a href="${relativeUrl}" target="_blank" class="btn btn-primary mt-3"><i class="bi bi-download me-2"></i>Tải file xuống</a>
                            </div>
                        `;
                    }
                }
            }
        }

        function toggleTheaterMode() {
            let sidebar = document.querySelector('.sidebar');
            let mainContent = document.querySelector('.main-content');
            if (sidebar) {
                if (sidebar.classList.contains('d-none')) {
                    sidebar.classList.remove('d-none');
                    sidebar.classList.add('d-flex');
                    mainContent.classList.remove('col-md-12');
                    mainContent.classList.add('col-md-8');
                } else {
                    sidebar.classList.remove('d-flex');
                    sidebar.classList.add('d-none');
                    mainContent.classList.remove('col-md-8');
                    mainContent.classList.add('col-md-12');
                }
            }
        }




        function toggleFullscreen() {
            let sidebar = document.querySelector('.sidebar');
            let mainContent = document.querySelector('.main-content');
            let body = document.querySelector('body');
            
            if (sidebar) {
                if (sidebar.classList.contains('d-none')) {
                    // Exit Theater Mode
                    sidebar.classList.remove('d-none');
                    sidebar.classList.add('d-flex');
                    mainContent.classList.remove('col-12', 'theater-mode');
                    mainContent.classList.add('col-md-9');
                    body.classList.remove('theater-mode-active');
                    
                    if (document.exitFullscreen && document.fullscreenElement) {
                        document.exitFullscreen().catch(err => console.log(err));
                    }
                    if (screen.orientation && screen.orientation.unlock) {
                       screen.orientation.unlock();
                    }
                } else {
                    // Enter Theater Mode
                    sidebar.classList.remove('d-flex');
                    sidebar.classList.add('d-none');
                    mainContent.classList.remove('col-md-9');
                    mainContent.classList.add('col-12', 'theater-mode');
                    body.classList.add('theater-mode-active');
                    
                    // Request Fullscreen and landscape orientation on mobile
                    let elem = mainContent;
                    if (elem.requestFullscreen) {
                        elem.requestFullscreen().then(() => {
                            if (screen.orientation && screen.orientation.lock) {
                                screen.orientation.lock("landscape").catch(err => console.log(err));
                            }
                        }).catch(err => console.log(err));
                    }
                }
            }
        }

        function toggleCollapse(bodyId, headerEl) {
            let bodyEl = document.getElementById(bodyId);
            let icon = headerEl.querySelector('.bi-chevron-up, .bi-chevron-down');
            if (bodyEl.style.display === 'none') {
                bodyEl.style.display = 'block';
                if (icon) { icon.classList.remove('bi-chevron-down'); icon.classList.add('bi-chevron-up'); }
            } else {
                bodyEl.style.display = 'none';
                if (icon) { icon.classList.remove('bi-chevron-up'); icon.classList.add('bi-chevron-down'); }
            }
        }
    </script>
</body>
</html>"""

# ----------------- MAIN EDIT UI TEMPLATE -----------------
BASE_HTML = r"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Vật lý - 12</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css" rel="stylesheet">
    <meta name="referrer" content="strict-origin-when-cross-origin" />
    <script src="https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js"></script>
    <style>
        body { background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; height: 100vh; overflow: hidden; }
        .sidebar { background: #ffffff; height: 100vh; overflow-y: auto; border-left: 1px solid #dee2e6; }
        .main-content { height: 100vh; overflow-y: auto; padding: 20px; background-color: #0f172a;}
        
        /* Folders & Nested */
        .folder-card { border: 1px solid #dee2e6; border-radius: 8px; margin-bottom: 12px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.05);}
        .folder-header { cursor: grab; background: #f8fafc; border-bottom: 1px solid #e2e8f0; padding: 10px; font-weight: bold; display: flex; align-items: center; justify-content: space-between; border-radius: 8px 8px 0 0;}
        .folder-header:active { cursor: grabbing; }
        
        .subfolder-card { border: 1px dashed #cbd5e1; margin: 4px; background: #f8fafc; border-radius: 6px; }
        .subfolder-header { cursor: grab; background: #e2e8f0; padding: 6px 10px; display: flex; align-items: center; justify-content: space-between; border-radius: 6px 6px 0 0;}
        .subfolder-header:active { cursor: grabbing; }

        .item-row { cursor: grab; border: 1px solid #f1f5f9; display: flex; align-items: center; padding: 8px 10px; transition: background 0.2s; margin: 4px; border-radius: 6px; background: white;}
        .item-row:active { cursor: grabbing; }
        .item-row:hover { background: #e2e8f0; }
        .item-row.active-item { background: #dbeafe; border-left: 4px solid #2563eb; }
        
        .sortable-ghost { opacity: 0.4; }
        .item-icon { font-size: 1.2rem; margin-right: 10px; color: #3b82f6; }
        .chapter-title-input { border: transparent; background: transparent; font-weight: bold; color: #1e293b; outline: none; flex-grow: 1; margin-right: 10px; word-break: break-word; min-width: 0; display: inline-block; cursor: text; }
        .chapter-title-input:focus { border-bottom: 1px solid #3b82f6; background: #fff; }
        .item-title-input { border: transparent; background: transparent; color: #334155; outline: none; width: 100%; font-size: 0.95rem; word-break: break-word; min-width: 0; display: inline-block; cursor: text; }
        .item-title-input:focus { border-bottom: 1px solid #3b82f6; background: #fff; }
        .time-badge { font-size: 0.8rem; color: #64748b; margin-left: auto; white-space: nowrap; }
        
        /* Custom scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #f1f1f1; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
        
        .upload-btn-wrapper { position: relative; overflow: hidden; display: inline-block; }
        .upload-btn-wrapper input[type=file] { font-size: 100px; position: absolute; left: 0; top: 0; opacity: 0; cursor: pointer; }

        /* Loader */
        #loading-overlay { display: none; position: fixed; top:0;left:0;right:0;bottom:0; background:rgba(0,0,0,0.7); z-index: 10000; align-items: center; justify-content: center; color: white;}
        .select-cb { cursor: pointer; transform: scale(1.1); margin-top: 0; }

        @media (max-width: 768px) {
            body { height: auto; overflow: auto; }
            .sidebar { height: auto; border-left: none; border-top: 1px solid #dee2e6; }
            .main-content { height: auto; padding: 10px; position: sticky; top: 0; z-index: 1020; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
            #viewer-placeholder { padding: 40px 0; }
            #viewer-container { aspect-ratio: 16/9; height: auto !important; }
            #viewer-title { font-size: 1.1rem; }
            .container-fluid { height: auto !important; }
            
            /* Responsive full screen fix for mobile theater mode */
            body.theater-mode-active { overflow: hidden !important; height: 100vh !important; width: 100vw !important;}
            .main-content.theater-mode { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 9999 !important; padding: 0 !important; background: #000 !important; }
            .main-content.theater-mode .d-flex.justify-content-between.align-items-center.mb-3 { position: absolute; top: 0; left: 0; right: 0; padding: 10px; background: rgba(0,0,0,0.6); z-index: 10000; margin: 0 !important; opacity: 0; transition: opacity 0.3s;}
            .main-content.theater-mode:hover .d-flex.justify-content-between.align-items-center.mb-3 { opacity: 1; }
            .main-content.theater-mode #viewer-container { height: 100vh !important; }
            .main-content.theater-mode iframe, .main-content.theater-mode video { width: 100%; height: 100%; }
        }

    </style>
</head>
<body>
    <!-- Top Nav / Header for app -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-secondary py-1 border-bottom border-dark">
      <div class="container-fluid">
        <a class="navbar-brand fs-6 fw-bold" href="#">🎓 Manage Playlist</a>
        <div class="collapse navbar-collapse show pb-1 pb-lg-0">
          <ul class="navbar-nav me-auto flex-row gap-3 ms-lg-4 mt-2 mt-lg-0">
            <li class="nav-item">
              <a class="nav-link active fw-bold text-white fs-7 py-0" href="#" onclick="switchMainTab('theory', this)"><i class="bi bi-book"></i> Lý thuyết</a>
            </li>
            <li class="nav-item border-start border-secondary ps-3">
              <a class="nav-link fs-7 text-white-50 py-0" href="#" onclick="switchMainTab('exercises', this)"><i class="bi bi-pencil-square"></i> Chữa đề & Làm đề</a>
            </li>
          </ul>
        </div>
        <div class="ms-auto d-flex">
            <button class="btn btn-sm btn-light text-dark fw-bold shadow-sm" data-bs-toggle="modal" data-bs-target="#settingsModal">
                <i class="bi bi-gear-fill me-1"></i> Cài đặt & Xuất Web
            </button>
        </div>
      </div>
    </nav>

    <div class="container-fluid p-0" style="height: calc(100vh - 42px); position: relative;">
        <!-- VIEW: LÝ THUYẾT -->
        <div id="view-theory" class="row m-0 h-100 w-100" style="display: flex;">
            <!-- Left col: Viewer -->
            <div class="col-md-9 main-content d-flex flex-column border-top border-dark h-100">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h3 id="viewer-title" class="text-white m-0">Chọn một bài giảng để xem</h3>
                    <div class="d-flex gap-2">
                        <button id="fullscreen-btn" class="btn btn-outline-primary btn-sm px-3" onclick="toggleTheaterMode()" style="display: none;"><i class="bi bi-aspect-ratio me-1"></i>Toàn màn hình</button>
                        <a id="viewer-download-btn" href="#" download class="btn btn-outline-light btn-sm px-3" style="display: none;"><i class="bi bi-download me-1"></i>Tải file xuống</a>
                    </div>
                </div>
                <div class="flex-grow-1 w-100 d-flex align-items-center justify-content-center bg-black rounded" style="position: relative; min-height: 0;">
                    <div id="viewer-container" class="w-100 h-100" style="display: none;"></div>
                    <div id="viewer-placeholder" class="text-muted text-center">
                        <i class="bi bi-play-circle" style="font-size: 4rem;"></i>
                        <p class="mt-2">Player / Trình xem File</p>
                    </div>
                </div>
            </div>

            <!-- Right col: Playlist -->
            <div class="col-md-3 p-0 sidebar d-flex flex-column h-100">
                <div class="p-3 bg-white border-bottom shadow-sm z-index-1 flex-shrink-0">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h5 class="m-0 fw-bold text-truncate" style="color: #1e293b; max-width: 40%;" id="sidebar-title"><i class="bi bi-list-nested me-2"></i>Danh sách</h5>
                        <div class="d-flex">
                            <button id="cut-btn" class="btn btn-sm btn-warning me-1 d-none text-dark fw-bold" onclick="cutSelected()"><i class="bi bi-scissors"></i> Cắt (<span id="cut-count">0</span>)</button>
                            <button id="cancel-cut-btn" class="btn btn-sm btn-outline-secondary me-1 d-none" onclick="cancelCut()"><i class="bi bi-x-lg"></i> Há»§y</button>
                            <button class="btn btn-sm btn-primary me-1" onclick="addChapter()"><i class="bi bi-folder-plus"></i></button>
                            <div class="upload-btn-wrapper">
                                <button class="btn btn-sm btn-success"><i class="bi bi-cloud-upload"></i> FILE</button>
                                <input type="file" id="file-upload" onchange="uploadFile(this)" accept=".pdf,.doc,.docx,.jpg,.png,.mp4">
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="flex-grow-1 overflow-auto p-3" id="playlist-container">
                    <!-- Chapters will be rendered here -->
                    <div id="chapters-list" class="sortable-area" style="min-height: 50px;"></div>
                    
                    <h6 class="mt-4 mb-2 text-muted fw-bold text-uppercase fs-7 d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-inbox me-2"></i>Chưa Phân Loại</span>
                        <span id="unassigned-paste-btn"></span>
                    </h6>
                    <div class="card mb-3 border-dashed shadow-sm">
                        <div class="list-group list-group-flush sortable-area min-vh-25" style="min-height: 150px; background: #f8fafc; padding: 4px;" id="unassigned-list"></div>
                    </div>
                </div>
            </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Modals -->

    <!-- Delete Confirm Modal -->
    <div class="modal fade" id="deleteModal" tabindex="-1">
      <div class="modal-dialog modal-sm">
        <div class="modal-content">
          <div class="modal-body text-center">
            <h5 class="mb-3">Xóa mục này?</h5>
            <div class="form-check text-start mb-3" id="block-video-container" style="display:none;">
              <input class="form-check-input" type="checkbox" id="block-video-checkbox" style="cursor: pointer;">
              <label class="form-check-label text-danger" for="block-video-checkbox" style="font-size: 0.85rem; cursor: pointer;">
                Xóa vĩnh viễn (chặn tự động thêm lại từ file log)
              </label>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Há»§y</button>
            <button type="button" class="btn btn-danger btn-sm" id="confirmDeleteBtn">Xóa</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Settings & Export Modal -->
    <div class="modal fade" id="settingsModal" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
           <div class="modal-header bg-light">
             <h5 class="modal-title text-dark"><i class="bi bi-gear me-2"></i>Cài đặt Khóa Học</h5>
             <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
           </div>
           <div class="modal-body bg-white text-dark">
                <!-- Nav tabs -->
                <ul class="nav nav-tabs mb-3" role="tablist">
                  <li class="nav-item" role="presentation">
                    <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#tab-settings" type="button">Cài đặt chung</button>
                  </li>
                  <li class="nav-item" role="presentation">
                    <button class="nav-link text-success" data-bs-toggle="tab" data-bs-target="#tab-export" type="button"><i class="bi bi-box-arrow-up-right me-1"></i>Xuất Web Tĩnh</button>
                  </li>
                </ul>

                <!-- Tab panes -->
                <div class="tab-content">
                  <div class="tab-pane active" id="tab-settings" role="tabpanel">
                      <div class="mb-3">
                        <label class="form-label fw-bold">Tên Khóa Học</label>
                        <input type="text" id="setting-title" class="form-control" placeholder="VD: Khóa Học Vật Lý 12">
                      </div>
                      <div class="mb-3">
                        <label class="form-label fw-bold">Tên Tác Giả / Nguồn</label>
                        <input type="text" id="setting-author" class="form-control" placeholder="VD: Thầy Hải">
                      </div>
                      <div class="mb-3">
                        <label class="form-label fw-bold">Bảng Thông Báo (Hỗ trợ HTML)</label>
                        <textarea id="setting-welcome" class="form-control" rows="4" placeholder="Nhập mã HTML hoặc text để hiển thị pop-up khi học sinh mới mở web..."></textarea>
                      </div>
                      <button class="btn btn-primary w-100" onclick="saveSettingsBase()"><i class="bi bi-save me-2"></i>Lưu Cài Đặt</button>
                  </div>
                  <div class="tab-pane" id="tab-export" role="tabpanel">
                      <div class="alert alert-info py-2 fs-7">
                        Tính năng này sẽ tạo file HTML trực tiếp để bạn có thể Copy Code hoặc tải về. Dữ liệu sẽ không bị mã hóa và không cần giải nén file zip.
                      </div>
                      <button class="btn btn-success w-100 fw-bold mb-2" onclick="exportStaticWeb()"><i class="bi bi-code-slash me-2"></i>Tạo Code HTML</button>
                      <button class="btn btn-primary w-100 fw-bold mb-2" id="copy-code-btn" style="display:none;" onclick="copyCode()"><i class="bi bi-clipboard me-2"></i>Copy Code</button>
                      <a id="download-html-btn" class="btn btn-secondary w-100 fw-bold mb-2" style="display:none;"><i class="bi bi-download me-2"></i>Tải file index.html</a>
                      <textarea id="export-textarea" class="form-control" rows="8" style="display:none;" readonly></textarea>
                  </div>
                </div>
           </div>
        </div>
      </div>
    </div>

    <!-- Loader -->
    <div id="loading-overlay">
        <div class="text-center">
            <div class="spinner-border text-light mb-3" role="status" style="width: 3rem; height: 3rem;"></div>
            <h5 id="loading-text">Đang mã hóa & xuất file...</h5>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let appData = { settings: {}, chapters: [], unassigned: [], exercises_chapters: [], exercises_unassigned: [], blocked_vids: [] };
        let currentItem = null;
        let itemToDelete = null; 
        let deleteModal = new bootstrap.Modal(document.getElementById('deleteModal'));
        let sortables = [];
        
        let selectedIds = new Set();
        let clipboardNodes = [];
        let currentMode = 'theory';
        let isDragging = false;
        let isEditingText = false;
        let lastModifiedTime = null;
        let connectedFolderId = null;
        let serverRevision = '0';
        let isSaving = false;
        let queuedSave = false;
        let suppressRemoteReloadUntil = 0;

        function normalizeClientData(data) {
            if (!data || typeof data !== 'object') {
                data = {};
            }
            if (!data.settings || typeof data.settings !== 'object') data.settings = {};
            if (!Array.isArray(data.chapters)) data.chapters = [];
            if (!Array.isArray(data.unassigned)) data.unassigned = [];
            if (!Array.isArray(data.exercises_chapters)) data.exercises_chapters = [];
            if (!Array.isArray(data.exercises_unassigned)) data.exercises_unassigned = [];
            if (!Array.isArray(data.blocked_vids)) data.blocked_vids = [];
            return data;
        }

        function applyServerState(payload) {
            const incomingData = payload && payload.data ? payload.data : payload;
            appData = normalizeClientData(incomingData || {});
            connectedFolderId = appData.connected_id || null;
            if (payload && payload.revision !== undefined) serverRevision = String(payload.revision);
            if (payload && payload.modified_time !== undefined) lastModifiedTime = payload.modified_time;

            document.getElementById('setting-title').value = appData.settings.course_title || '';
            document.getElementById('setting-author').value = appData.settings.author_name || '';
            document.getElementById('setting-welcome').value = appData.settings.welcome_message || '';
            updateUIHeaders();
            renderPlaylist();
        }

        function buildSavePayload() {
            return {
                revision: serverRevision,
                settings: appData.settings,
                chapters: appData.chapters,
                unassigned: appData.unassigned,
                exercises_chapters: appData.exercises_chapters,
                exercises_unassigned: appData.exercises_unassigned,
                blocked_vids: appData.blocked_vids,
                connected_id: connectedFolderId
            };
        }

        document.addEventListener('focusin', e => {
            if(e.target.hasAttribute('contenteditable') || e.target.tagName === 'INPUT') {
                isEditingText = true;
            }
        });
        document.addEventListener('focusout', e => {
            if(e.target.hasAttribute('contenteditable') || e.target.tagName === 'INPUT') {
                setTimeout(() => { isEditingText = false; }, 500); // Tiny delay to allow saves
            }
        });

        // Polling loop for real-time updates
        setInterval(() => {
            if (isEditingText || isDragging || isSaving || selectedIds.size > 0 || clipboardNodes.length > 0) return;
            if (Date.now() < suppressRemoteReloadUntil) return;
            
            fetch('/api/check_update')
                .then(res => res.json())
                .then(data => {
                    if (lastModifiedTime === null) {
                        lastModifiedTime = data.modified_time;
                        if (data.revision !== undefined) serverRevision = String(data.revision);
                    } else if (data.modified_time !== lastModifiedTime && String(data.revision || '') !== String(serverRevision || '')) {
                        fetch('/api/data')
                            .then(res => res.json())
                            .then(payload => {
                                applyServerState(payload);
                            });
                    }
                })
                .catch(e => {}); // ignore network errors
        }, 2000);

        function getActiveChapters() { return currentMode === 'theory' ? appData.chapters : appData.exercises_chapters; }
        function getActiveUnassigned() { return appData.unassigned; }

        // Load data on start
        fetch('/api/data')
            .then(res => res.json())
            .then(payload => {
                applyServerState(payload);
            });

        function updateUIHeaders() {
            let title = appData.settings.course_title || 'Danh sách bài học';
            document.getElementById('sidebar-title').innerHTML = `<i class="bi bi-list-nested me-2"></i>${title}`;
        }

        function saveSettingsBase() {
            appData.settings.course_title = document.getElementById('setting-title').value;
            appData.settings.author_name = document.getElementById('setting-author').value;
            appData.settings.welcome_message = document.getElementById('setting-welcome').value;
            updateUIHeaders();
            saveStateToServer();
            
            // hide modal
            var myModalEl = document.getElementById('settingsModal');
            var modal = bootstrap.Modal.getInstance(myModalEl);
            modal.hide();
        }

        async function exportZipWeb() {
            document.getElementById('loading-overlay').style.display = 'flex';
            document.getElementById('loading-text').innerText = 'Đang đóng gói file ZIP (Có chứa File Upload)...';

            try {
                appData.chapters = extractItems(document.getElementById('chapters-list'));
                appData.unassigned = extractItems(document.getElementById('unassigned-list'));

                let res = await fetch('/api/export_zip', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(appData)
                });

                if(res.ok) {
                    let blob = await res.blob();
                    let a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = "KhoaHoc_Kiem_Uploads.zip";
                    a.click();
                    document.getElementById('loading-overlay').style.display = 'none';
                    document.getElementById('loading-text').innerText = 'Đang mã hóa & xuất file...';
                } else {
                    alert('Lỗi xuất file ZIP');
                    document.getElementById('loading-overlay').style.display = 'none';
                }
            } catch(e) {
                console.error(e);
                alert("Lỗi: " + e);
                document.getElementById('loading-overlay').style.display = 'none';
            }
        }

        async function exportStaticWeb() {
            document.getElementById('loading-overlay').style.display = 'flex';

            try {
                // Ensure latest DOM state is saved to appData
                appData.chapters = extractItems(document.getElementById('chapters-list'));
                appData.unassigned = extractItems(document.getElementById('unassigned-list'));

                let res = await fetch('/api/export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(appData)
                });

                if(res.ok) {
                    let data = await res.json();
                    if(!data.success) {
                        alert('Lá»—i export: ' + data.error);
                        document.getElementById('loading-overlay').style.display = 'none';
                        return;
                    }
                    
                    let htmlCode = data.html;
                    let textarea = document.getElementById('export-textarea');
                    textarea.value = htmlCode;
                    textarea.style.display = 'block';
                    
                    document.getElementById('copy-code-btn').style.display = 'block';
                    
                    let blob = new Blob([htmlCode], {type: "text/html;charset=utf-8"});
                    let dlBtn = document.getElementById('download-html-btn');
                    dlBtn.href = URL.createObjectURL(blob);
                    dlBtn.download = "index.html";
                    dlBtn.style.display = 'block';
                    
                    document.getElementById('loading-overlay').style.display = 'none';
                } else {
                    let err = await res.json();
                    alert('Lá»—i export: ' + err.error);
                    document.getElementById('loading-overlay').style.display = 'none';
                }
            } catch(e) {
                console.error(e);
                alert("Lỗi chi tiết: " + (e.message || e));
                document.getElementById('loading-overlay').style.display = 'none';
            }
        }

        function copyCode() {
            let textarea = document.getElementById('export-textarea');
            textarea.select();
            document.execCommand('copy');
            alert('Đã copy mã HTML thành công!');
        }

        /* ---------------- Playlist Logic ------------- */

        function renderPlaylist() {
            const chapList = document.getElementById('chapters-list');
            const unassignedList = document.getElementById('unassigned-list');
            
            let chapters = getActiveChapters() || [];
            let unassigned = getActiveUnassigned() || [];
            
            chapList.innerHTML = chapters.map(chap => renderFolder(chap, false)).join('');
            unassignedList.innerHTML = unassigned.map(item => renderAny(item)).join('');
            
            document.getElementById('unassigned-paste-btn').innerHTML = (clipboardNodes.length > 0) ? `<button class="btn btn-sm btn-info text-white p-0 px-2" onclick="pasteToUnassigned()"><i class="bi bi-clipboard-check-fill"></i> Dán ngay</button>` : '';

            initSortable();
        }

        function renderAny(node, isSub = true) {
            if (!node.type) node.type = node.url ? 'file' : (node.yt_id ? 'video' : 'folder'); // infer
            if (node.type === 'folder') return renderFolder(node, isSub);
            return renderItem(node);
        }

        function renderFolder(folder, isSub) {
            let cardClass = isSub ? 'subfolder-card' : 'folder-card';
            let headerClass = isSub ? 'subfolder-header' : 'folder-header';
            let isChecked = selectedIds.has(folder.id) ? 'checked' : '';
            let pasteBtn = (clipboardNodes.length > 0) ? `<button class="btn btn-sm btn-info p-0 ms-2 text-white flex-shrink-0" style="padding: 0 4px!important;" onclick="event.stopPropagation(); pasteHere('${folder.id}')" title="Dán vào đây"><i class="bi bi-box-arrow-in-down-right"></i> Dán</button>` : '';
            
            let uploadBtn = `
            <label class="btn btn-sm text-success p-0 ms-2 mb-0 d-flex align-items-center" title="Tải file vào thư mục này" onclick="event.stopPropagation()">
                <i class="bi bi-cloud-upload" style="font-size: 1.1rem;"></i>
                <input type="file" multiple onchange="uploadFile(this, '${folder.id}')" accept=".pdf,.doc,.docx,.jpg,.png,.mp4" style="display: none;">
            </label>`;
            
            let isConnected = (connectedFolderId === folder.id);
            let connectIcon = isConnected ? 'bi-plug-fill text-danger' : 'bi-plug text-muted';
            let connectTitle = isConnected ? 'Ngắt kết nối' : 'Kết nối với tool capture (Gửi thẳng vào đây)';
            
            let connectBtn = `<button class="btn btn-sm p-0 ms-2" onclick="event.stopPropagation(); connectFolder('${folder.id}')" title="${connectTitle}"><i class="bi ${connectIcon}" style="font-size: 1.1rem;"></i></button>`;

            let btnHtml = pasteBtn + uploadBtn + connectBtn + `<button class="btn btn-sm text-primary p-0 ms-2" onclick="event.stopPropagation(); addFolder('${folder.id}')" title="Thêm mục con"><i class="bi bi-folder-plus"></i></button>`;
            let folderIcon = isSub ? '<i class="bi bi-folder2-open text-secondary me-2"></i>' : '<i class="bi bi-folder-fill text-warning me-2"></i>';
            let isCollapsed = folder.collapsed === true;
            let displayStyle = isCollapsed ? 'none' : 'block';
            let chevronIcon = isCollapsed ? 'bi-chevron-down' : 'bi-chevron-up';

            let itemsHtml = (folder.items || []).map(item => renderAny(item, true)).join('');

            return `
                <div class="${cardClass} item-draggable" data-item-id="${folder.id}" data-type="folder" data-collapsed="${isCollapsed}">
                    <div class="${headerClass}" onclick="event.stopPropagation(); toggleCollapse('${folder.id}', 'folder-body-${folder.id}', this)">
                        <i class="bi bi-grip-vertical text-muted me-1 handle"></i>
                        <input type="checkbox" class="form-check-input select-cb me-2" value="${folder.id}" ${isChecked} onclick="event.stopPropagation(); toggleSelection(this)">
                        ${folderIcon}
                        <span class="chapter-title-input" contenteditable="true" onclick="event.stopPropagation()" onblur="saveState()" onkeydown="if(event.key==='Enter') { this.blur(); event.preventDefault(); }">${(folder.title || "Chương mới").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;")}</span>
                        <button class="btn btn-sm text-secondary p-0 ms-auto" title="Thu gọn/Mở rộng"><i class="bi ${chevronIcon} collapse-icon"></i></button>
                        ${btnHtml}
                        <button class="btn btn-sm text-danger p-0 ms-2 flex-shrink-0" onclick="event.stopPropagation(); promptDelete('${folder.id}')" title="Xóa thư mục"><i class="bi bi-trash"></i></button>
                    </div>
                    <div id="folder-body-${folder.id}" class="list-group list-group-flush sortable-area" style="min-height: 25px; padding: 4px; display: ${displayStyle};">
                        ${itemsHtml}
                    </div>
                </div>
            `;
        }

        function renderItem(item) {
            let icon = item.type === 'video' ? '<i class="bi bi-play-btn-fill item-icon"></i>' : '<i class="bi bi-file-earmark-text-fill item-icon text-success"></i>';
            let timeInfo = item.time ? `<span class="time-badge">${item.time}</span>` : '';
            let activeClass = (currentItem && currentItem.id === item.id) ? 'active-item' : '';
            let defaultTitle = item.type === 'video' ? 'Video' : 'File đính kèm';
            let safeId = item.id.replace(/'/g, "\\'");
            let isChecked = selectedIds.has(item.id) ? 'checked' : '';
            
            return `
                <div class="item-row item-draggable ${activeClass}" id="item-row-${item.id}" data-item-id="${item.id}" data-type="item" onclick="viewItem('${safeId}')">
                    <i class="bi bi-grip-vertical text-muted me-2 handle" onclick="event.stopPropagation()"></i>
                    <input type="checkbox" class="form-check-input select-cb me-2" value="${item.id}" ${isChecked} onclick="event.stopPropagation(); toggleSelection(this)">
                    ${icon}
                    <div class="flex-grow-1 me-2" onclick="event.stopPropagation()">
                         <span class="item-title-input" contenteditable="true" onblur="saveState()" onkeydown="if(event.key==='Enter') { this.blur(); event.preventDefault(); }">${(item.title || defaultTitle).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;")}</span>
                    </div>
                    ${timeInfo}
                    <button class="btn btn-sm text-danger p-0 ms-2 flex-shrink-0" onclick="event.stopPropagation(); promptDelete('${item.id}')" title="Xóa mục này"><i class="bi bi-x-circle"></i></button>
                </div>
            `;
        }
        
        function toggleCollapse(folderId, bodyId, headerEl) {
            let bodyEl = document.getElementById(bodyId);
            if (!bodyEl) return;
            
            // Toggle data attribute on the parent wrapper 
            let folderWrapper = headerEl.closest('.folder-card, .subfolder-card');
            
            let icon = headerEl.querySelector('.collapse-icon');
            if (bodyEl.style.display === 'none') {
                bodyEl.style.display = 'block';
                if (icon) { icon.classList.remove('bi-chevron-down'); icon.classList.add('bi-chevron-up'); }
                if (folderWrapper) folderWrapper.setAttribute('data-collapsed', 'false');
            } else {
                bodyEl.style.display = 'none';
                if (icon) { icon.classList.remove('bi-chevron-up'); icon.classList.add('bi-chevron-down'); }
                if (folderWrapper) folderWrapper.setAttribute('data-collapsed', 'true');
            }
            // Trigger save state so data.json remembers layout preferences immediately
            saveState();
        }

        function toggleSelection(chk) {
            if (chk.checked) selectedIds.add(chk.value);
            else selectedIds.delete(chk.value);
            updateSelectionUI();
        }

        function updateSelectionUI() {
            let cutBtn = document.getElementById('cut-btn');
            if (selectedIds.size > 0) {
                cutBtn.classList.remove('d-none');
                document.getElementById('cut-count').innerText = selectedIds.size;
            } else {
                cutBtn.classList.add('d-none');
            }
        }

        function extractAndRemoveNode(id, list) {
            for (let i = 0; i < list.length; i++) {
                if (list[i].id === id) {
                    return list.splice(i, 1)[0];
                }
                if (list[i].items) {
                    let found = extractAndRemoveNode(id, list[i].items);
                    if (found) return found;
                }
            }
            return null;
        }

        function cutSelected() {
            saveState(); // Ensure UI state is mirrored to variables before slicing

            clipboardNodes = [];
            let chapters = getActiveChapters() || [];
            let unassigned = getActiveUnassigned() || [];

            selectedIds.forEach(id => {
                let n = extractAndRemoveNode(id, chapters) || extractAndRemoveNode(id, unassigned);
                if (n) clipboardNodes.push(n);
            });
            selectedIds.clear();
            updateSelectionUI();
            
            document.getElementById('cancel-cut-btn').classList.remove('d-none');
            saveStateToServer();
            renderPlaylist();
        }

        function cancelCut() {
            if (clipboardNodes.length > 0) {
                let unassigned = getActiveUnassigned();
                if(!unassigned) unassigned = [];
                unassigned.unshift(...clipboardNodes);
                clipboardNodes = [];
            }
            document.getElementById('cancel-cut-btn').classList.add('d-none');
            saveStateToServer();
            renderPlaylist();
        }

        function pasteHere(parentId) {
            if (clipboardNodes.length === 0) return;
            let targetNode = findItemInTree(parentId);
            if (targetNode) {
                if (!targetNode.items || !Array.isArray(targetNode.items)) targetNode.items = [];
                targetNode.items.push(...clipboardNodes);
                clipboardNodes = [];
                document.getElementById('cancel-cut-btn').classList.add('d-none');
                saveStateToServer();
                renderPlaylist();
            }
        }

        function pasteToUnassigned() {
            if (clipboardNodes.length === 0) return;
            let unassigned = getActiveUnassigned();
            if(!unassigned) unassigned = [];
            unassigned.push(...clipboardNodes);
            clipboardNodes = [];
            
            appData.unassigned = unassigned;

            document.getElementById('cancel-cut-btn').classList.add('d-none');
            saveStateToServer();
            renderPlaylist();
        }

        function initSortable() {
            sortables.forEach(s => s.destroy());
            sortables = [];

            document.querySelectorAll('.sortable-area').forEach(el => {
                sortables.push(new Sortable(el, {
                    group: 'shared',
                    animation: 150,
                    handle: '.handle',
                    fallbackOnBody: true,
                    swapThreshold: 0.65,
                    onStart: function() {
                        isDragging = true;
                    },
                    onEnd: function() {
                        isDragging = false;
                        saveState(); 
                    }
                }));
            });
        }

        function findItemInTree(id, list = null) {
            if (!list) list = (appData.chapters || []).concat(appData.unassigned || []).concat(appData.exercises_chapters || []).concat(appData.exercises_unassigned || []);
            for (let item of list) {
                if (item.id === id) return item;
                if (item.items && Array.isArray(item.items)) {
                    let found = findItemInTree(id, item.items);
                    if (found) return found;
                }
            }
            return null;
        }

        function extractItems(container) {
            let res = [];
            container.querySelectorAll(':scope > .item-draggable').forEach(el => {
                let id = el.dataset.itemId;
                let type = el.dataset.type;
                let node = Object.assign({}, findItemInTree(id) || { id: id, type: type });
                
                if (type === 'folder') {
                    let titleEl = el.querySelector('.chapter-title-input');
                    if (titleEl) node.title = (titleEl.value !== undefined ? titleEl.value : titleEl.innerText).trim().replace(/\n/g, ' ');
                    let listEl = el.querySelector('.sortable-area');
                    if (listEl) node.items = extractItems(listEl);
                    node.collapsed = el.dataset.collapsed === 'true';
                } else {
                    let titleEl = el.querySelector('.item-title-input');
                    if (titleEl) node.title = (titleEl.value !== undefined ? titleEl.value : titleEl.innerText).trim().replace(/\n/g, ' ');
                }
                res.push(node);
            });
            return res;
        }

        function saveState() {
            if (currentMode === 'theory') {
                appData.chapters = extractItems(document.getElementById('chapters-list'));
            } else {
                appData.exercises_chapters = extractItems(document.getElementById('chapters-list'));
            }
            appData.unassigned = extractItems(document.getElementById('unassigned-list'));
            saveStateToServer();
        }

        async function saveStateToServer() {
            if (isSaving) {
                queuedSave = true;
                return;
            }

            isSaving = true;
            suppressRemoteReloadUntil = Date.now() + 5000;

            try {
                const res = await fetch('/api/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(buildSavePayload())
                });

                const payload = await res.json().catch(() => ({}));
                if (!res.ok || !payload.success) {
                    if (res.status === 409 && payload.code === 'revision_conflict') {
                        applyServerState(payload);
                        alert('Du lieu vua thay doi o mot luong khac. Tool da nap lai ban moi nhat, khong ghi de len setup vua co.');
                    } else {
                        alert('Khong the luu du lieu: ' + (payload.error || 'Unknown error'));
                    }
                    return;
                }

                if (payload.revision !== undefined) serverRevision = String(payload.revision);
                if (payload.modified_time !== undefined) lastModifiedTime = payload.modified_time;
            } catch (e) {
                alert('Khong the luu du lieu. Vui long thu lai.');
            } finally {
                isSaving = false;
                if (queuedSave) {
                    queuedSave = false;
                    saveStateToServer();
                }
            }
        }

        function connectFolder(id) {
            connectedFolderId = (connectedFolderId === id) ? null : id;
            saveState();
            renderPlaylist();
        }

        function addChapter() {
            let cId = 'folder_' + Date.now();
            let chapters = getActiveChapters();
            if(!chapters) chapters = [];
            chapters.unshift({ id: cId, type: 'folder', title: 'Chương mới', items: [] });
            
            if (currentMode === 'theory') appData.chapters = chapters;
            else appData.exercises_chapters = chapters;
            
            saveStateToServer();
            renderPlaylist();
        }

        function addFolder(parentId) {
            let pNode = findItemInTree(parentId);
            if (pNode) {
                pNode.type = 'folder';
                if (!pNode.items || !Array.isArray(pNode.items)) {
                    pNode.items = [];
                }
                
                let sId = 'folder_' + Date.now() + Math.floor(Math.random()*100);
                pNode.items.unshift({ id: sId, type: 'folder', title: 'Mục con mới', items: [] });
                saveStateToServer();
                renderPlaylist();
            }
        }

        async function uploadFile(input, parentId) {
            if (!input.files || input.files.length === 0) return;
            let formData = new FormData();
            for (let i = 0; i < input.files.length; i++) {
                formData.append('file', input.files[i]);
            }
            
            input.disabled = true;
            try {
                let res = await fetch('/api/upload', { method: 'POST', body: formData });
                let data = await res.json();
                if (data.success) {
                    if (parentId) {
                        let targetNode = findItemInTree(parentId);
                        if (targetNode) {
                            if (!targetNode.items || !Array.isArray(targetNode.items)) targetNode.items = [];
                            for (let i = data.items.length - 1; i >= 0; i--) {
                                targetNode.items.unshift(data.items[i]);
                            }
                            targetNode.collapsed = false; // Auto expand so user sees upload
                        } else {
                            let unassigned = getActiveUnassigned();
                            if(!unassigned) unassigned = [];
                            for (let i = data.items.length - 1; i >= 0; i--) {
                                unassigned.unshift(data.items[i]);
                            }
                            appData.unassigned = unassigned;
                        }
                    } else {
                        let unassigned = getActiveUnassigned();
                        if(!unassigned) unassigned = [];
                        for (let i = data.items.length - 1; i >= 0; i--) {
                            unassigned.unshift(data.items[i]);
                        }
                        appData.unassigned = unassigned;
                    }
                    saveStateToServer();
                    renderPlaylist();
                } else {
                    alert('Lá»—i upload: ' + data.error);
                }
            } catch (e) {
                alert('Có lỗi xảy ra khi upload');
            }
            input.disabled = false;
            input.value = ''; 
        }

        function promptDelete(id) {
            itemToDelete = id;
            let item = findItemInTree(id);
            let blockContainer = document.getElementById('block-video-container');
            let blockCheckbox = document.getElementById('block-video-checkbox');
            if (item && item.type === 'video' && item.yt_id) {
                blockContainer.style.display = 'block';
                blockCheckbox.checked = false;
            } else {
                blockContainer.style.display = 'none';
                blockCheckbox.checked = false;
            }
            deleteModal.show();
        }

        function removeNode(id, list) {
            for (let i = 0; i < list.length; i++) {
                if (list[i].id === id) {
                    list.splice(i, 1);
                    return true;
                }
                if (list[i].items && removeNode(id, list[i].items)) {
                    return true;
                }
            }
            return false;
        }

        document.getElementById('confirmDeleteBtn').onclick = function() {
            if (!itemToDelete) return;
            
            let item = findItemInTree(itemToDelete);
            let blockCheckbox = document.getElementById('block-video-checkbox');
            
            if (item && item.type === 'video' && item.yt_id && blockCheckbox && blockCheckbox.checked) {
                if (!appData.blocked_vids) appData.blocked_vids = [];
                if (!appData.blocked_vids.includes(item.yt_id)) {
                    appData.blocked_vids.push(item.yt_id);
                }
            }

            let chapters = getActiveChapters() || [];
            let unassigned = getActiveUnassigned() || [];

            if (!removeNode(itemToDelete, chapters)) {
                removeNode(itemToDelete, unassigned);
            }
            deleteModal.hide();
            itemToDelete = null;
            saveStateToServer();
            renderPlaylist();
        };

        function viewItem(id) {
            let item = findItemInTree(id);
            if (!item || item.type === 'folder') return;
            currentItem = item;
            
            document.querySelectorAll('.item-row').forEach(r => r.classList.remove('active-item'));
            let activeRow = document.getElementById(`item-row-${id}`);
            if (activeRow) activeRow.classList.add('active-item');

            let placeholder = document.getElementById('viewer-placeholder');
            if (placeholder) {
                placeholder.classList.remove('d-flex');
                placeholder.classList.add('d-none');
                placeholder.style.setProperty('display', 'none', 'important');
            }
            let vc = document.getElementById('viewer-container');
            vc.style.display = 'block';
            vc.classList.add('h-100');
            
            let titleSource = item.source ? ` <span class="badge bg-secondary ms-2">${item.source}</span>` : '';
            document.getElementById('viewer-title').innerHTML = (item.title || "Bài giảng") + titleSource;
            
            let dlBtn = document.getElementById('viewer-download-btn');
            let fsBtn = document.getElementById('fullscreen-btn');
            if(fsBtn) fsBtn.style.display = 'inline-block';

            if (item.type === 'video' && item.yt_id) {
                if(dlBtn) dlBtn.style.display = 'none';
                vc.innerHTML = `
                    <div style="position: relative; width: 100%; height: 100%; overflow: hidden;">
                        <iframe referrerpolicy="strict-origin-when-cross-origin" src="https://www.youtube-nocookie.com/embed/${item.yt_id}?autoplay=1&modestbranding=1&rel=0" class="w-100 h-100 border-0" allow="autoplay; fullscreen" allowfullscreen></iframe>
                    </div>
                `;
            } else if (item.type === 'file' && item.url) {
                if(dlBtn) {
                     dlBtn.href = item.url;
                     dlBtn.download = item.title || 'download';
                     dlBtn.style.display = 'inline-block';
                }

                if (item.url.toLowerCase().endsWith('.pdf')) {
                    vc.innerHTML = `<iframe src="${item.url}" class="w-100 h-100 border-0" allowfullscreen></iframe>`;
                } else if (item.url.match(/\.(jpeg|jpg|gif|png)$/i)) {
                     vc.innerHTML = `<div class="w-100 h-100 d-flex justify-content-center align-items-center bg-dark"><img src="${item.url}" style="max-height: 100%; max-width: 100%;"></div>`;
                } else if (item.url.match(/\.(mp4|webm)$/i)) {
                     vc.innerHTML = `<video src="${item.url}" controls autoplay class="w-100 h-100 bg-dark" allowfullscreen></video>`;
                } else {
                    vc.innerHTML = `
                        <div class="h-100 d-flex flex-column justify-content-center align-items-center bg-white text-dark rounded">
                            <i class="bi bi-file-earmark-arrow-down text-primary mb-3" style="font-size: 4rem;"></i>
                            <h5>Định dạng file không hỗ trợ xem trực tiếp</h5>
                            <a href="${item.url}" target="_blank" class="btn btn-primary mt-3"><i class="bi bi-download me-2"></i>Tải file xuống</a>
                        </div>
                    `;
                }
            }
        }

        function toggleTheaterMode() {
            let sidebar = document.querySelector('.sidebar');
            let mainContent = document.querySelector('.main-content');
            let body = document.querySelector('body');
            
            if (sidebar) {
                if (sidebar.classList.contains('d-none')) {
                    // Exit Theater Mode
                    sidebar.classList.remove('d-none');
                    sidebar.classList.add('d-flex');
                    mainContent.classList.remove('col-12', 'theater-mode');
                    mainContent.classList.add('col-md-9');
                    body.classList.remove('theater-mode-active');
                    
                    if (document.exitFullscreen && document.fullscreenElement) {
                        document.exitFullscreen().catch(err => console.log(err));
                    }
                    if (screen.orientation && screen.orientation.unlock) {
                       screen.orientation.unlock();
                    }
                } else {
                    // Enter Theater Mode
                    sidebar.classList.remove('d-flex');
                    sidebar.classList.add('d-none');
                    mainContent.classList.remove('col-md-9');
                    mainContent.classList.add('col-12', 'theater-mode');
                    body.classList.add('theater-mode-active');
                    
                    // Request Fullscreen and landscape orientation on mobile
                    let elem = mainContent;
                    if (elem.requestFullscreen) {
                        elem.requestFullscreen().then(() => {
                            if (screen.orientation && screen.orientation.lock) {
                                screen.orientation.lock("landscape").catch(err => console.log(err));
                            }
                        }).catch(err => console.log(err));
                    }
                }
            }
        }

        function switchMainTab(tabId, el) {
            document.querySelectorAll('.navbar-nav .nav-link').forEach(link => {
                link.classList.remove('active', 'text-white', 'fw-bold');
                link.classList.add('text-white-50');
            });
            el.classList.add('active', 'text-white', 'fw-bold');
            el.classList.remove('text-white-50');
            
            // Save state before changing tabs
            saveState();

            currentMode = tabId;
            selectedIds.clear();
            clipboardNodes = [];
            updateSelectionUI();
            
            document.getElementById('cancel-cut-btn').classList.add('d-none');
            
            // Reset player area
            let placeholder = document.getElementById('viewer-placeholder');
            if (placeholder) {
                placeholder.classList.remove('d-none');
                placeholder.classList.add('d-flex');
                placeholder.style.display = 'flex';
            }
            document.getElementById('viewer-container').style.display = 'none';
            document.getElementById('viewer-title').innerHTML = "Chọn một bài/tài liệu để xem";
            
            renderPlaylist();
        }
    </script>
</body>
</html>
"""

def normalize_data(data):
    source = data if isinstance(data, dict) else {}
    normalized = {
        "settings": dict(source.get("settings", {})) if isinstance(source.get("settings"), dict) else {},
        "chapters": list(source.get("chapters", [])) if isinstance(source.get("chapters"), list) else [],
        "unassigned": list(source.get("unassigned", [])) if isinstance(source.get("unassigned"), list) else [],
        "blocked_vids": list(source.get("blocked_vids", [])) if isinstance(source.get("blocked_vids"), list) else [],
        "exercises_chapters": list(source.get("exercises_chapters", [])) if isinstance(source.get("exercises_chapters"), list) else [],
        "exercises_unassigned": list(source.get("exercises_unassigned", [])) if isinstance(source.get("exercises_unassigned"), list) else []
    }

    normalized["connected_id"] = source.get("connected_id")
    return normalized


def get_data_revision():
    if not os.path.exists(DATA_FILE):
        return "0"
    # Use a combination of mtime and file size for a more robust revision
    stat = os.stat(DATA_FILE)
    return f"{stat.st_mtime_ns}_{stat.st_size}"


def get_data_modified_time():
    if not os.path.exists(DATA_FILE):
        return 0
    return os.path.getmtime(DATA_FILE)


def make_backup_snapshot():
    if not os.path.exists(DATA_FILE):
        return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_name = f"data_{timestamp}.json"
    backup_path = os.path.join(BACKUP_FOLDER, backup_name)
    shutil.copy2(DATA_FILE, backup_path)

    history_files = sorted(
        [name for name in os.listdir(BACKUP_FOLDER) if name.lower().endswith('.json')],
        reverse=True
    )
    for old_name in history_files[MAX_HISTORY_FILES:]:
        old_path = os.path.join(BACKUP_FOLDER, old_name)
        if os.path.isfile(old_path):
            os.remove(old_path)

    return backup_name


def validate_node_list(nodes, field_name, errors, path_label=None):
    if not isinstance(nodes, list):
        errors.append(f"{field_name} must be a list")
        return

    for idx, node in enumerate(nodes):
        node_path = f"{path_label or field_name}[{idx}]"
        if not isinstance(node, dict):
            errors.append(f"{node_path} must be an object")
            continue

        node_id = node.get("id")
        node_type = node.get("type")
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"{node_path}.id is required")
        if node_type not in ("folder", "video", "file"):
            errors.append(f"{node_path}.type is invalid")
            continue

        if node_type == "folder":
            if not isinstance(node.get("title", ""), str):
                errors.append(f"{node_path}.title must be a string")
            validate_node_list(node.get("items", []), field_name, errors, f"{node_path}.items")
        else:
            if "title" in node and not isinstance(node.get("title"), str):
                errors.append(f"{node_path}.title must be a string")
            if node_type == "video":
                yt_id = node.get("yt_id")
                if yt_id is not None and not isinstance(yt_id, str):
                    errors.append(f"{node_path}.yt_id must be a string")
            if node_type == "file":
                url = node.get("url")
                if url is not None and not isinstance(url, str):
                    errors.append(f"{node_path}.url must be a string")


def validate_payload(data):
    if not isinstance(data, dict):
        return False, ["payload must be an object"]

    required_lists = ["chapters", "unassigned", "blocked_vids", "exercises_chapters", "exercises_unassigned"]
    errors = []

    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        errors.append("settings must be an object")

    for field in required_lists:
        if field not in data:
            errors.append(f"missing field: {field}")

    if errors:
        return False, errors

    validate_node_list(data.get("chapters", []), "chapters", errors)
    validate_node_list(data.get("unassigned", []), "unassigned", errors)
    validate_node_list(data.get("exercises_chapters", []), "exercises_chapters", errors)
    validate_node_list(data.get("exercises_unassigned", []), "exercises_unassigned", errors)

    if not isinstance(data.get("blocked_vids", []), list):
        errors.append("blocked_vids must be a list")
    elif not all(isinstance(item, str) for item in data.get("blocked_vids", [])):
        errors.append("blocked_vids entries must be strings")

    connected_id = data.get("connected_id")
    if connected_id is not None and not isinstance(connected_id, str):
        errors.append("connected_id must be a string or null")

    return len(errors) == 0, errors


def load_data():
    with data_lock:
        if not os.path.exists(DATA_FILE):
            return normalize_data(DEFAULT_DATA)
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                return normalize_data(data)
            except json.JSONDecodeError:
                return normalize_data(DEFAULT_DATA)


def save_data(data, create_backup=True):
    with data_lock:
        normalized = normalize_data(data)
        temp_file = DATA_FILE + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, ensure_ascii=False, indent=4)

        if os.path.exists(DATA_FILE):
            if create_backup:
                # Call make_backup_snapshot while holding the lock. 
                # Note: it will try to read DATA_FILE. Since we are in an RLock and 
                # we haven't overwritten DATA_FILE yet, it's safe.
                make_backup_snapshot()
            if os.path.exists(DATA_FILE + ".bak"):
                os.remove(DATA_FILE + ".bak")
            os.replace(DATA_FILE, DATA_FILE + ".bak")
        os.replace(temp_file, DATA_FILE)

def get_folder_map(data):
    """Creates a flat map of folder_id -> folder_object for O(1) lookup"""
    folder_map = {}
    def walk(lst):
        for item in lst:
            if item.get("type") == "folder":
                folder_map[item["id"]] = item
                if item.get("items"):
                    walk(item["items"])
    walk(data.get("chapters", []))
    walk(data.get("unassigned", []))
    walk(data.get("exercises_chapters", []))
    walk(data.get("exercises_unassigned", []))
    return folder_map

def sync_logs():
    """Sync videos from logs into unassigned items if they don't exist yet"""
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) < 50: # Skip if empty/header only
        return

    with data_lock:
        data = load_data()
        existing_yt_ids = set()
        blocked_vids = set(data.get("blocked_vids", []))
        
        # Recursive search for existing yt_ids
        def find_vids(lst):
            for i in lst:
                if i.get("type") == "video" and i.get("yt_id"):
                    existing_yt_ids.add(i["yt_id"])
                if i.get("items"):
                    find_vids(i["items"])
                    
        find_vids(data.get("chapters", []))
        find_vids(data.get("unassigned", []))
        find_vids(data.get("exercises_chapters", []))
        find_vids(data.get("exercises_unassigned", []))
                
        added = False
        log_lines = []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            log_lines = f.readlines()

        if not log_lines:
            return

        folder_map = get_folder_map(data)
        conn_id = data.get("connected_id")
        target_f = folder_map.get(conn_id) if conn_id else None

        for line in log_lines:
            # Support new format: [time] link | Bài: lesson_name (Nguồn: source)
            # and old format: [time] link (Nguồn: source)
            match_new = re.match(r"\[(.*?)\] (.*?) \| Bài: (.*?) \(Nguồn: (.*?)\)", line)
            match_old = re.match(r"\[(.*?)\] (.*?) \(Nguồn: (.*?)\)", line)
            
            if match_new:
                time_str, yt_url, lesson_name, source_url = match_new.groups()
            elif match_old:
                time_str, yt_url, source_url = match_old.groups()
                lesson_name = source_url.strip().split('/')[-1]
                if not lesson_name: lesson_name = source_url.strip()
            else:
                continue
            
            # Improved YouTube ID extraction
            vid_id = None
            yt_match = re.search(r"(?:v=|\/embed\/|\/v\/|youtu\.be\/|\/watch\?v=|\/shorts\/|^)([a-zA-Z0-9_-]{11})", yt_url)
            if "youtube.com" in yt_url or "youtu.be" in yt_url:
                if yt_match:
                    vid_id = yt_match.group(1)
            
            # If not a YT video, use URL as ID (or a hash if URL is too long)
            if not vid_id:
                vid_id = uuid.uuid5(uuid.NAMESPACE_URL, yt_url).hex[:12]
            
            if vid_id:
                if vid_id not in blocked_vids and vid_id not in existing_yt_ids:
                    new_item = {
                        "id": f"vid_{vid_id}",
                        "type": "video",
                        "title": f"{lesson_name} - Video",
                        "yt_id": vid_id,
                        "time": time_str,
                        "yt_url": yt_url,
                        "source": source_url.strip()
                    }
                    
                    if target_f:
                        target_f.setdefault("items", []).append(new_item)
                    else:
                        data.setdefault("unassigned", []).append(new_item)
                    
                    existing_yt_ids.add(vid_id)
                    added = True

        if added:
            save_data(data)
            # Clear logs after successful sync to keep processing O(new_lines)
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("--- LIST VIDEO CAPTURED (SYNCED) ---\n")

@app.route('/')
def index():
    sync_logs()
    return render_template_string(BASE_HTML)

@app.route('/api/data', methods=['GET'])
def get_data():
    sync_logs()
    data = load_data()
    revision = get_data_revision()
    return jsonify({
        "data": data,
        "revision": revision,
        "modified_time": get_data_modified_time()
    })

@app.route('/api/check_update', methods=['GET'])
def check_update():
    try:
        revision = get_data_revision()
        log_mtime = os.path.getmtime(LOG_FILE) if os.path.exists(LOG_FILE) else 0
        return jsonify({
            "modified_time": get_data_modified_time() + log_mtime,
            "revision": revision
        })
    except Exception:
        return jsonify({"modified_time": 0, "revision": "0"})

@app.route('/api/save', methods=['POST'])
def update_data():
    new_data = request.json or {}
    client_revision = str(new_data.pop("revision", "0"))
    is_valid, errors = validate_payload(new_data)
    if not is_valid:
        return jsonify({"success": False, "error": "; ".join(errors[:5])}), 400

    current_revision = get_data_revision()
    if current_revision != client_revision:
        return jsonify({
            "success": False,
            "error": "Data changed in another save session",
            "code": "revision_conflict",
            "revision": current_revision,
            "modified_time": get_data_modified_time(),
            "data": load_data()
        }), 409

    save_data(new_data)
    new_revision = get_data_revision()
    return jsonify({
        "success": True,
        "revision": new_revision,
        "modified_time": get_data_modified_time(),
        "history_dir": BACKUP_FOLDER
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    files = request.files.getlist('file')
    if not files:
        return jsonify({"success": False, "error": "No file part"})
    
    processed_items = []
    
    for file in files:
        if file.filename == '': continue
        if file:
            filename = secure_filename(file.filename)
            base, ext = os.path.splitext(filename)
            counter = 1
            final_filename = filename
            while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], final_filename)):
                final_filename = f"{base}_{counter}{ext}"
                counter += 1
                
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], final_filename))
            
            item_id = f"file_{uuid.uuid4().hex[:8]}"
            processed_items.append({
                "id": item_id,
                "type": "file",
                "title": file.filename,
                "url": f"/static/uploads/{final_filename}"
            })
            
    if not processed_items:
        return jsonify({"success": False, "error": "No selected file"})
        
    return jsonify({"success": True, "items": processed_items})
        
@app.route('/api/export_zip', methods=['POST'])
def export_zip():
    req_data = request.json
    try:
        json_data = json.dumps(req_data, ensure_ascii=False)
        final_html = STATIC_HTML.replace("___REPLACE_ME_DATA___", json_data)
        
        # Tạo file ZIP trong memory
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('index.html', final_html.encode('utf-8'))
            
            # Pack static/uploads if exists
            uploads_dir = app.config['UPLOAD_FOLDER']
            allowed_extensions = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.mp4', '.webm'}
            if os.path.exists(uploads_dir):
                for file in os.listdir(uploads_dir):
                    file_path = os.path.join(uploads_dir, file)
                    ext = os.path.splitext(file)[1].lower()
                    if os.path.isfile(file_path) and ext in allowed_extensions:
                        zf.write(file_path, arcname=f'static/uploads/{file}')
                        
        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name='StaticWeb_With_Uploads.zip'
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/export', methods=['POST'])
def export_web():
    req_data = request.json
    try:
        json_data = json.dumps(req_data, ensure_ascii=False)
        final_html = STATIC_HTML.replace("___REPLACE_ME_DATA___", json_data)
        return jsonify({"success": True, "html": final_html})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/capture', methods=['POST'])
@require_client_token
def capture():
    data = request.json
    page_url = data.get('page_url', 'Unknown')
    lesson_name = data.get('lesson_name', 'Unknown Lesson')
    video_links = data.get('video_links', [])

    if video_links:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                for link in video_links:
                    f.write(f"[{timestamp}] {link} | Bài: {lesson_name} (Nguồn: {page_url})\n")
            
            # Remove from blacklist if recaptured
            app_data = load_data()
            updated_blacklist = False
            for link in video_links:
                vid_match = re.search(r"v=([a-zA-Z0-9_-]{11})", link)
                if vid_match:
                    vid_id = vid_match.group(1)
                    if "blocked_vids" in app_data and vid_id in app_data["blocked_vids"]:
                        app_data["blocked_vids"].remove(vid_id)
                        updated_blacklist = True
                        
            if updated_blacklist:
                save_data(app_data)
            
            # Force immediate sync so it appears in the connected folder right away
            sync_logs()
            
            print(f"\033[92m[+] Done: {lesson_name}\033[0m")
            return jsonify({"status": "success"}), 200
        except OSError:
            return jsonify({"status": "error", "message": "Disk full"}), 507
            
    return jsonify({"status": "empty"}), 400

@app.route('/capture_file', methods=['POST'])
@require_client_token
def capture_file():
    data = request.json
    page_url = data.get('page_url', 'Unknown')
    file_data = data.get('file_data', [])

    if file_data:
        app_data = load_data()
        
        for fd in file_data:
            link = fd.get('url')
            file_name = fd.get('name', 'Unknown Document')
            if not link: continue
            try:
                base, ext = os.path.splitext(link)
                # handle URLs like .pdf?x=....
                if '?' in ext: ext = ext.split('?')[0]
                if not ext or ext.lower() not in ['.pdf', '.doc', '.docx', '.jpg', '.png']: ext = ".pdf"
                
                # Sanitize filename (lower to fix Vercel Case Sensitivity 404s)
                safe_name = secure_filename(file_name).lower()
                if not safe_name or safe_name in ['.', '..']: 
                    safe_name = f"file_{uuid.uuid4().hex[:8]}"
                
                final_filename = safe_name + ext
                counter = 1
                while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], final_filename)):
                    final_filename = f"{safe_name}_{counter}{ext}"
                    counter += 1
                
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
                
                print(f"[*] Downloading {link} -> {filepath}")
                req = urllib.request.Request(link, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response, open(filepath, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
                
                item_id = f"file_{uuid.uuid4().hex[:8]}"
                new_item = {
                    "id": item_id,
                    "type": "file",
                    "title": file_name,
                    "url": f"/static/uploads/{final_filename}",
                    "source": page_url
                }
                
                folder_map = get_folder_map(app_data)
                conn_id = app_data.get("connected_id")
                target_f = folder_map.get(conn_id) if conn_id else None
                
                if target_f:
                    target_f.setdefault("items", []).append(new_item)
                else:
                    app_data.setdefault("unassigned", []).append(new_item)
            except Exception as e:
                print(f"[!] Lá»—i download file: {e}")
                
        save_data(app_data)
        return jsonify({"status": "success"}), 200
        
    return jsonify({"status": "empty"}), 400

if __name__ == '__main__':
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f: f.write("--- LIST VIDEO CAPTURED ---\n")
    print("\n[*] Trinh quan ly Playlist va Capture Listener dang chay: http://127.0.0.1:5001")
    app.run(port=5001, debug=True, use_reloader=False)









