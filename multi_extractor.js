/**
 * 🎬 & 📑 Multi Extractor - Standalone v2.7 (Universal Edition)
 * [ADDED] Support for both Main Site (Ant Design) and Exported Web (Bootstrap).
 * [FIXED] Sequence numbering for both platforms.
 * [FIXED] Mobile Layout - Smaller icon when collapsed to avoid blocking nav.
 */
(function () {
    'use strict';

    /* ─────────────────────────────────────────────
       CONFIG
    ───────────────────────────────────────────── */
    const BACKEND_URL_VID = 'http://127.0.0.1:5001/capture';
    const BACKEND_URL_FILE = 'http://127.0.0.1:5001/capture_file';
    const CLIENT_TOKEN = 'hai_auto_vip_pro_2026';
    
    const CHECK_INTERVAL = 5000;
    const INIT_DELAY = 1000;
    const STORAGE_KEY = 'multi_extractor_captured_ids';
    const MAX_CACHE_SIZE = 500;

    /* ─────────────────────────────────────────────
       STATE
    ───────────────────────────────────────────── */
    const safeGet = (key, def) => localStorage.getItem(key) || def;
    const safeSet = (key, val) => localStorage.setItem(key, val);

    let capturedIDs = new Set(JSON.parse(safeGet(STORAGE_KEY, '[]')));
    let processingIDs = new Set();
    
    let isEnabled = true;
    let mainInterval = null;
    let mutationObserver = null;
    let debounceTimer = null;
    
    let totalSentVid = 0;
    let totalSentFile = 0;

    /* ─────────────────────────────────────────────
       UTILS
    ───────────────────────────────────────────── */
    function saveCapturedIDs() {
        let list = [...capturedIDs];
        if (list.length > MAX_CACHE_SIZE) {
            list = list.slice(-MAX_CACHE_SIZE);
            capturedIDs = new Set(list);
        }
        safeSet(STORAGE_KEY, JSON.stringify(list));
    }

    function extractVideoID(url) {
        if (!url) return null;
        const m = url.match(/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?|shorts|live)\/|.*[?&]v=)|youtu\.be\/|youtube-nocookie\.com\/embed\/)([^"&?\/\s]{11})/);
        return m ? m[1] : null;
    }

    function log(msg, type = 'info') {
        const icons = { info: '📋', ok: '✅', warn: '⏸', err: '❌', send: '🚀', clear: '🗑' };
        console.log(`${icons[type] || '▸'} [Multi-Extractor] ${msg}`);
        appendLog(msg, type);
    }

    async function postData(url, data) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Client-Token': CLIENT_TOKEN },
                mode: 'cors',
                body: JSON.stringify(data)
            });
            return response;
        } catch (error) {
            return { status: 0, statusText: error.message };
        }
    }

    /* ─────────────────────────────────────────────
       EXTRACTION LOGIC (Universal 2.7)
    ───────────────────────────────────────────── */
    function runExtraction() {
        if (!isEnabled) return;

        // 1. CHÈN SỐ THỨ TỰ (Dành cho web chính & web export)
        const items = document.querySelectorAll('.ant-list-item, .item-row');
        items.forEach((item, index) => {
            const seq = (index + 1).toString().padStart(2, '0');
            const target = item.querySelector('.document-name, .item-title') || item;
            
            if (target && !target.hasAttribute('data-me-marked')) {
                const mark = document.createElement('span');
                mark.style.cssText = 'color: #22c55e; font-weight: bold; margin-right: 5px;';
                mark.textContent = `(${seq})`;
                target.prepend(mark);
                target.setAttribute('data-me-marked', 'true');
            }
        });

        // 2. LẤY TÊN BÀI ĐANG CHỌN
        const activeItem = document.querySelector('.ant-list-item.active, .item-row.active-item, .document-name.active');
        const lessonName = (activeItem?.innerText || document.title || 'Unknown')
                            .replace(/^\(\d+\)\s*/, '').replace(/\s+/g, ' ').trim();

        // 3. QUÉT VIDEO / IFRAME QUAN TRỌNG
        const iframes = document.querySelectorAll('iframe');
        const videos = document.querySelectorAll('video, video source');
        processVideos(iframes, videos, lessonName);
        processFiles(iframes, [], lessonName);

        // 4. QUÉT LINK TRONG CÁC DÒNG (Nếu click sẵn hoặc có link ẩn)
        items.forEach(item => {
            const rowText = item.innerText.replace(/\s+/g, ' ').trim();
            const links = item.querySelectorAll('a');
            processFiles(null, links, rowText);
        });
    }

    async function processVideos(iframes, videos, chapterName) {
        const discovered = [];
        const scan = (el, attr) => {
            const src = el[attr] || el.getAttribute(attr) || '';
            const id = extractVideoID(src);
            if (id) {
                const key = 'vid:' + id;
                if (!capturedIDs.has(key) && !processingIDs.has(key)) {
                    discovered.push({ id: key, raw: id });
                    processingIDs.add(key);
                }
            } else if (src.includes('.mp4') || src.includes('.m3u8')) {
                const key = 'mp4:' + src;
                if (!capturedIDs.has(key) && !processingIDs.has(key)) {
                    discovered.push({ id: key, raw: src });
                    processingIDs.add(key);
                }
            }
        };

        iframes.forEach(i => scan(i, 'src'));
        videos.forEach(v => scan(v, 'src'));

        if (discovered.length === 0) return;

        const finalLinks = discovered.map(d => (/^[a-zA-Z0-9_-]{11}$/.test(d.raw)) ? `https://www.youtube.com/watch?v=${d.raw}` : d.raw);

        const res = await postData(BACKEND_URL_VID, {
            page_url: window.location.href, 
            lesson_name: chapterName, 
            video_links: finalLinks 
        });

        if (res.status === 200) {
            discovered.forEach(d => { capturedIDs.add(d.id); processingIDs.delete(d.id); });
            saveCapturedIDs();
            totalSentVid += finalLinks.length;
            log(`[Video] Đã gửi ${finalLinks.length} mục (${chapterName})`, 'ok');
        } else {
            discovered.forEach(d => processingIDs.delete(d.id));
        }
    }

    async function processFiles(iframes, links, chapterName) {
        const filePayload = [];
        const discoveredIds = [];
        const batchUrls = new Set();

        if (iframes) {
            iframes.forEach(iframe => {
                const src = iframe.src || '';
                let targetUrl = null;
                if (src.includes('viewer.html')) {
                    try { targetUrl = new URL(src, window.location.href).searchParams.get('file'); } catch (e) { }
                } else if (src.toLowerCase().includes('.pdf')) {
                    targetUrl = src;
                }
                if (targetUrl) addFile(targetUrl, chapterName);
            });
        }

        links.forEach(a => {
            const href = a.href || '';
            if (/\.(pdf|docx?|jpg|png|xlsx)(\?.*)?$/i.test(href)) {
                addFile(href, a.innerText.trim() || chapterName);
            }
        });

        function addFile(url, name) {
            const key = 'file:' + url;
            if (!capturedIDs.has(key) && !processingIDs.has(key) && !batchUrls.has(url)) {
                filePayload.push({ url, name });
                discoveredIds.push(key);
                processingIDs.add(key);
                batchUrls.add(url);
            }
        }

        if (filePayload.length === 0) return;

        const res = await postData(BACKEND_URL_FILE, { 
            page_url: window.location.href, 
            file_data: filePayload 
        });

        if (res.status === 200) {
            discoveredIds.forEach(id => { capturedIDs.add(id); processingIDs.delete(id); });
            saveCapturedIDs();
            totalSentFile += filePayload.length;
            log(`[File] Đã gửi ${filePayload.length} tài liệu`, 'ok');
        } else {
            discoveredIds.forEach(id => processingIDs.delete(id));
        }
    }

    /* ─────────────────────────────────────────────
       SYSTEM & UI (v2.7 Mobile Fix)
    ───────────────────────────────────────────── */
    function startTracking() {
        stopTracking();
        mainInterval = setInterval(runExtraction, CHECK_INTERVAL);
        mutationObserver = new MutationObserver((mutations) => {
            let relevant = false;
            for (const m of mutations) {
                if (m.addedNodes.length > 0) { relevant = true; break; }
            }
            if (relevant) { clearTimeout(debounceTimer); debounceTimer = setTimeout(runExtraction, 500); }
        });
        mutationObserver.observe(document.body, { childList: true, subtree: true });
        log('Auto-run v2.7 Universal Online', 'ok');
    }

    function stopTracking() {
        if (mainInterval) clearInterval(mainInterval);
        if (mutationObserver) mutationObserver.disconnect();
    }

    function toggle() {
        isEnabled = !isEnabled;
        if (isEnabled) { startTracking(); updateToggleBtn(true); updateStatus('idle', 'Đang theo dõi…'); } 
        else { stopTracking(); updateToggleBtn(false); updateStatus('warn', 'Đã tạm dừng'); }
    }
    
    function resetCache() {
        capturedIDs.clear(); processingIDs.clear(); saveCapturedIDs();
        document.querySelectorAll('[data-me-marked]').forEach(el => el.removeAttribute('data-me-marked'));
        log('Đã xoá bộ nhớ Cache.', 'clear');
        runExtraction();
    }

    const UI_ID = '__multi_extractor_panel__';
    function buildUI() {
        if (document.getElementById(UI_ID)) return;
        const panel = document.createElement('div');
        panel.id = UI_ID;
        panel.innerHTML = `
<style>
  #${UI_ID} {
    position: fixed; bottom: 80px; right: 10px; z-index: 2147483647;
    font-family: system-ui, -apple-system, sans-serif; font-size: 11px; width: 260px; 
    background: rgba(10,10,10,0.95); backdrop-filter: blur(15px);
    border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.8);
    color: #fff; text-align: left; overflow: hidden; transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  }
  #${UI_ID}.me-collapsed { width: 38px; height: 38px; border-radius: 19px; bottom: 85px; right: 10px; opacity: 0.7; }
  #${UI_ID}.me-collapsed:hover { opacity: 1; }
  #${UI_ID}.me-collapsed .me-body { display: none; }
  #${UI_ID}.me-collapsed .me-title { display: none; }
  #${UI_ID}.me-collapsed .me-header { padding: 0; width: 100%; height: 100%; justify-content: center; background: #22c55e; border: none; }
  #${UI_ID}.me-collapsed .me-dot { background: #000; box-shadow: none; width: 12px; height: 12px; }
  
  #${UI_ID} .me-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: rgba(255,255,255,0.05); cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.05); }
  #${UI_ID} .me-title { flex: 1; font-weight: 800; font-size: 9px; text-transform: uppercase; letter-spacing: 1px; color: #777; }
  #${UI_ID} .me-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 10px #22c55e; flex-shrink: 0; transition: 0.3s; }
  #${UI_ID} .me-dot.off { background: #ef4444; box-shadow: 0 0 10px #ef4444; }
  
  #${UI_ID} .me-body { padding: 12px; }
  #${UI_ID} .me-stats { display: flex; gap: 6px; margin-bottom: 10px; }
  #${UI_ID} .me-stat { flex: 1; background: rgba(255,255,255,0.02); border-radius: 8px; padding: 6px 0; text-align: center; border: 1px solid rgba(255,255,255,0.04); }
  #${UI_ID} .me-stat-val { display: block; font-size: 14px; font-weight: 800; }
  #${UI_ID} .me-stat-lbl { font-size: 7px; text-transform: uppercase; color: #444; }
  #${UI_ID} .me-btn { width: 100%; padding: 8px; border: none; border-radius: 8px; cursor: pointer; font-weight: 700; margin-bottom: 5px; font-size: 10px; }
  #${UI_ID} .me-btn-toggle { background: #22c55e; color: #000; }
  #${UI_ID} .me-btn-toggle.off { background: #222; color: #555; }
  #${UI_ID} .me-btn-reset { background: transparent; color: #ef4444; border: 1px solid rgba(239,68,68,0.2); }
  #${UI_ID} .me-log { background: #000; border-radius: 8px; height: 80px; overflow-y: auto; padding: 6px; border: 1px solid rgba(255,255,255,0.05); }
  #${UI_ID} .me-log-entry { font-size: 9px; color: #555; padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.03); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  
  @media (max-width: 600px) {
    #${UI_ID} { width: 220px; }
  }
</style>
<div class="me-header" id="me-hdr">
  <div id="me-dot" class="me-dot"></div>
  <div class="me-title">Universal Extractor v2.7</div>
</div>
<div class="me-body">
  <div class="me-stats">
    <div class="me-stat"><span class="me-stat-val" id="me-cnt-sd">0</span><span class="me-stat-lbl">Gửi</span></div>
    <div class="me-stat"><span class="me-stat-val" id="me-cnt-ca">0</span><span class="me-stat-lbl">Nhớ</span></div>
  </div>
  <button class="me-btn me-btn-toggle" id="me-tgl">⏸ Tạm dừng</button>
  <button class="me-btn me-btn-reset" id="me-rst">Xóa Cache</button>
  <div class="me-log" id="me-log"></div>
</div>`;
        document.body.appendChild(panel);
        
        const hdr = document.getElementById('me-hdr');
        hdr.onclick = () => { panel.classList.toggle('me-collapsed'); };
        document.getElementById('me-tgl').onclick = (e) => { e.stopPropagation(); toggle(); };
        document.getElementById('me-rst').onclick = (e) => { e.stopPropagation(); if(confirm('Clear storage?')) resetCache(); };
    }

    function updateStatus(type, msg) {
        document.getElementById('me-dot').className = 'me-dot' + (type === 'warn' ? ' off' : '');
    }

    function updateToggleBtn(on) {
        const btn = document.getElementById('me-tgl');
        if (btn) {
            btn.textContent = on ? '⏸ TẠM DỪNG' : '▶ TIẾP TỤC';
            btn.className = 'me-btn me-btn-toggle' + (on ? '' : ' off');
        }
    }

    function updateCounter() {
        const sd = document.getElementById('me-cnt-sd');
        const ca = document.getElementById('me-cnt-ca');
        if (sd) sd.textContent = totalSentVid + totalSentFile;
        if (ca) ca.textContent = capturedIDs.size;
    }

    function appendLog(msg, type = 'info') {
        const box = document.getElementById('me-log');
        if (!box) return;
        const entry = document.createElement('div');
        entry.className = `me-log-entry ${type === 'ok' ? 'ok' : ''}`;
        if (type === 'ok') entry.style.color = '#22c55e';
        entry.textContent = `[${new Date().toLocaleTimeString('vi-VN')}] ${msg}`;
        box.prepend(entry);
        updateCounter();
    }

    /* ─────────────────────────────────────────────
       INITIALIZE
    ───────────────────────────────────────────── */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => setTimeout(buildUI, INIT_DELAY));
    } else {
        setTimeout(buildUI, INIT_DELAY);
    }
    setTimeout(startTracking, INIT_DELAY + 500);

})();
