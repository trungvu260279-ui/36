// ==UserScript==
// @name         📑 File Extractor - One Click Capture
// @namespace    http://tampermonkey.net/
// @version      1.3
// @description  Bắt link file PDF từ bất kỳ website nào gửi về Manager local.
// @author       Antigravity
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    console.log('🚀 [File-Extractor] Script started!');

    /* ─────────────────────────────────────────────
       CONFIG
    ───────────────────────────────────────────── */
    const BACKEND_URL = 'http://127.0.0.1:5001/capture_file';
    const CHECK_INTERVAL = 5000;   // ms between auto-run cycles
    const INIT_DELAY = 3000;   // ms before first run

    /* ─────────────────────────────────────────────
       STATE
    ───────────────────────────────────────────── */
    const capturedIDs = new Set();   // IDs already sent — skip these
    let isEnabled = true;
    let intervalID = null;
    let totalSent = 0;

    /* ─────────────────────────────────────────────
       UTILS
    ───────────────────────────────────────────── */
    function log(msg, type = 'info') {
        const icons = { info: '📋', ok: '✅', warn: '⏸', err: '❌', send: '🚀' };
        console.log(`${icons[type] || '▸'} [File-Extractor] ${msg}`);
        appendLog(msg, type);
    }

    /* ─────────────────────────────────────────────
       EXTRACT + SEND
    ───────────────────────────────────────────── */
    function extractFiles() {
        if (!isEnabled) return;

        const filePayloadTemplate = [];

        // Try getting chapter title or current title
        let lessonNameObj = document.querySelector('a.document-name.active');
        let chapterName = lessonNameObj ? lessonNameObj.textContent.replace(/\s+/g, ' ').trim() : (document.title || 'Unknown Document');

        // iframes for pdf viewer
        document.querySelectorAll('iframe').forEach(iframe => {
            const src = iframe.src || '';
            let targetUrl = null;
            if (src.includes('viewer.html?file=')) {
                try {
                    targetUrl = decodeURIComponent(src.split('file=')[1]);
                } catch (e) { }
            } else if (src.includes('.pdf')) {
                 targetUrl = src;
            }
            
            if (targetUrl && !capturedIDs.has(targetUrl)) {
                 try {
                     // Try to extract filename from URL, e.g. "de-hoc-ki-1.pdf" -> "de-hoc-ki-1"
                     let urlPart = targetUrl.split('?')[0]; // remove query params
                     let filenameMatch = urlPart.split('/').pop();
                     let baseName = filenameMatch;
                     if (baseName.includes('.')) {
                         baseName = baseName.substring(0, baseName.lastIndexOf('.'));
                     }
                     // If baseName is just a generic ID or 'file-de', default to chapterName
                     let finalName = baseName.length > 3 && !baseName.startsWith('file-de') ? `${chapterName} - ${baseName}` : chapterName;
                     
                     filePayloadTemplate.push({
                         url: targetUrl,
                         name: finalName
                     });
                 } catch(err) {
                     filePayloadTemplate.push({ url: targetUrl, name: chapterName });
                 }
            }
        });

        if (filePayloadTemplate.length === 0) {
            updateStatus('idle', 'Không có file mới');
            return;
        }

        // Mark as captured immediately to avoid duplicate sends
        filePayloadTemplate.forEach(p => capturedIDs.add(p.url));

        log(`Bóc tách ${filePayloadTemplate.length} file mới, đang gửi…`, 'send');
        updateStatus('sending', `Đang gửi ${filePayloadTemplate.length} file…`);

        GM_xmlhttpRequest({
            method: 'POST',
            url: BACKEND_URL,
            headers: { 'Content-Type': 'application/json' },
            data: JSON.stringify({ 
                page_url: window.location.href, 
                file_data: filePayloadTemplate 
            }),
            onload: function(r) {
                totalSent += filePayloadTemplate.length;
                log(`Đã gửi ${filePayloadTemplate.length} file (tổng: ${totalSent})`, 'ok');
                updateStatus('ok', `Đã gửi ${filePayloadTemplate.length} file · Tổng: ${totalSent}`);
                updateCounter();
            },
            onerror: function(err) {
                log(`Lỗi kết nối Backend (Có chạy manager.py chưa?): ${err.statusText}`, 'err');
                updateStatus('err', 'Lỗi kết nối backend');
            }
        });
    }

    /* ─────────────────────────────────────────────
       AUTO-RUN LOOP
    ───────────────────────────────────────────── */
    function startLoop() {
        stopLoop();
        intervalID = setInterval(extractFiles, CHECK_INTERVAL);
        log('Auto-run đã bật', 'ok');
    }

    function stopLoop() {
        if (intervalID) { clearInterval(intervalID); intervalID = null; }
    }

    function toggle() {
        isEnabled = !isEnabled;
        if (isEnabled) {
            startLoop();
            updateToggleBtn(true);
            updateStatus('idle', 'Đang theo dõi…');
        } else {
            stopLoop();
            updateToggleBtn(false);
            updateStatus('warn', 'Đã tạm dừng');
        }
    }

    /* ─────────────────────────────────────────────
       UI
    ───────────────────────────────────────────── */
    const UI_ID = '__file_extractor_panel__';

    function buildUI() {
        if (document.getElementById(UI_ID)) return;

        const panel = document.createElement('div');
        panel.id = UI_ID;
        panel.innerHTML = `
<style>
  #${UI_ID} {
    position: fixed;
    bottom: 20px;
    left: 20px; /* put on the left side so it doesn't overlap YT */
    z-index: 2147483647;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    width: 280px;
    background: #0d0d0d;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    box-shadow: 0 8px 32px rgba(0,0,0,.6), 0 0 0 1px #1a1a1a inset;
    overflow: hidden;
    transition: height .25s ease;
    user-select: none;
  }
  #${UI_ID} .yt-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: #111;
    border-bottom: 1px solid #1f1f1f;
    cursor: pointer;
  }
  #${UI_ID} .yt-title {
    flex: 1;
    color: #e0e0e0;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: .08em;
    text-transform: uppercase;
  }
  #${UI_ID} .yt-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 6px #22c55e;
    transition: background .3s, box-shadow .3s;
  }
  #${UI_ID} .yt-dot.off { background:#ef4444; box-shadow:0 0 6px #ef4444; }
  #${UI_ID} .yt-dot.warn { background:#f59e0b; box-shadow:0 0 6px #f59e0b; }
  #${UI_ID} .yt-body { padding: 10px 12px; }
  #${UI_ID} .yt-status {
    background: #161616;
    border: 1px solid #222;
    border-radius: 6px;
    padding: 6px 10px;
    color: #9ca3af;
    font-size: 11px;
    min-height: 26px;
    margin-bottom: 8px;
  }
  #${UI_ID} .yt-stats {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
  }
  #${UI_ID} .yt-stat {
    flex: 1;
    background: #161616;
    border: 1px solid #222;
    border-radius: 6px;
    padding: 5px 8px;
    text-align: center;
  }
  #${UI_ID} .yt-stat-val {
    display: block;
    color: #f0f0f0;
    font-size: 16px;
    font-weight: 700;
  }
  #${UI_ID} .yt-stat-lbl {
    color: #555;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: .06em;
  }
  #${UI_ID} .yt-btn-row {
    display: flex;
    gap: 6px;
  }
  #${UI_ID} .yt-btn {
    flex: 1;
    padding: 7px 0;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-family: inherit;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .04em;
    transition: opacity .15s, transform .1s;
  }
  #${UI_ID} .yt-btn:active { transform: scale(.96); }
  #${UI_ID} .yt-btn-toggle {
    background: #22c55e;
    color: #000;
  }
  #${UI_ID} .yt-btn-toggle.off { background: #ef4444; color: #fff; }
  #${UI_ID} .yt-btn-scan {
    background: #2563eb;
    color: #fff;
  }
  #${UI_ID} .yt-log {
    margin-top: 8px;
    background: #0a0a0a;
    border: 1px solid #1a1a1a;
    border-radius: 6px;
    height: 72px;
    overflow-y: auto;
    padding: 4px 8px;
  }
  #${UI_ID} .yt-log-entry {
    color: #4b5563;
    line-height: 1.5;
    font-size: 10px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  #${UI_ID} .yt-log-entry.ok  { color: #22c55e; }
  #${UI_ID} .yt-log-entry.err { color: #ef4444; }
  #${UI_ID} .yt-log-entry.send { color: #60a5fa; }
  #${UI_ID} .yt-log-entry.warn { color: #f59e0b; }
  #${UI_ID} .yt-collapsed .yt-body { display: none; }
</style>
<div class="yt-header" id="file-hdr">
  <span id="file-dot" class="yt-dot"></span>
  <span class="yt-title">📑 File Extractor</span>
  <span id="file-collapse-icon" style="color:#555;font-size:10px">▼</span>
</div>
<div class="yt-body" id="file-body">
  <div class="yt-status" id="file-status">Đang khởi động…</div>
  <div class="yt-stats">
    <div class="yt-stat">
      <span class="yt-stat-val" id="file-cnt-sent">0</span>
      <span class="yt-stat-lbl">Đã gửi</span>
    </div>
    <div class="yt-stat">
      <span class="yt-stat-val" id="file-cnt-captured">0</span>
      <span class="yt-stat-lbl">Đã capture</span>
    </div>
  </div>
  <div class="yt-btn-row">
    <button class="yt-btn yt-btn-toggle" id="file-toggle-btn">⏸ Tạm dừng</button>
    <button class="yt-btn yt-btn-scan" id="file-scan-btn">🔍 Scan ngay</button>
  </div>
  <div class="yt-log" id="file-log"></div>
</div>`;

        document.body.appendChild(panel);

        // Collapse toggle
        let collapsed = false;
        document.getElementById('file-hdr').addEventListener('click', () => {
            collapsed = !collapsed;
            panel.classList.toggle('yt-collapsed', collapsed);
            document.getElementById('file-collapse-icon').textContent = collapsed ? '▲' : '▼';
        });

        document.getElementById('file-toggle-btn').addEventListener('click', e => {
            e.stopPropagation();
            toggle();
        });

        document.getElementById('file-scan-btn').addEventListener('click', e => {
            e.stopPropagation();
            extractFiles();
        });
    }

    function updateStatus(type, msg) {
        const el = document.getElementById('file-status');
        const dot = document.getElementById('file-dot');
        if (!el) return;
        el.textContent = msg;
        dot.className = 'yt-dot' + (type === 'warn' ? ' warn' : type === 'err' ? ' off' : '');
    }

    function updateToggleBtn(on) {
        const btn = document.getElementById('file-toggle-btn');
        if (!btn) return;
        btn.textContent = on ? '⏸ Tạm dừng' : '▶ Bật lại';
        btn.className = 'yt-btn yt-btn-toggle' + (on ? '' : ' off');
    }

    function updateCounter() {
        const s = document.getElementById('file-cnt-sent');
        const c = document.getElementById('file-cnt-captured');
        if (s) s.textContent = totalSent;
        if (c) c.textContent = capturedIDs.size;
    }

    const LOG_MAX = 40;
    function appendLog(msg, type = 'info') {
        const box = document.getElementById('file-log');
        if (!box) return;
        const entry = document.createElement('div');
        entry.className = `yt-log-entry ${type}`;
        const time = new Date().toLocaleTimeString('vi-VN', { hour12: false });
        entry.textContent = `[${time}] ${msg}`;
        box.appendChild(entry);
        while (box.children.length > LOG_MAX) box.removeChild(box.firstChild);
        box.scrollTop = box.scrollHeight;
        updateCounter();
    }

    /* ─────────────────────────────────────────────
       BOOT
    ───────────────────────────────────────────── */
    function init() {
        if (!document.body) {
            setTimeout(init, 100);
            return;
        }
        buildUI();
        updateStatus('idle', 'Đang theo dõi…');
        setTimeout(() => {
            extractFiles();
            startLoop();
        }, INIT_DELAY);
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
