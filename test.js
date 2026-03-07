
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
            if (isEditingText || isDragging || selectedIds.size > 0 || clipboardNodes.length > 0) return;
            
            fetch('/api/check_update')
                .then(res => res.json())
                .then(data => {
                    if (lastModifiedTime === null) {
                        lastModifiedTime = data.modified_time;
                    } else if (data.modified_time !== lastModifiedTime) {
                        lastModifiedTime = data.modified_time;
                        // Reload data smoothly
                        fetch('/api/data')
                            .then(res => res.json())
                            .then(newData => {
                                appData = newData;
                                if(!appData.settings) appData.settings = {};
                                if(!appData.blocked_vids) appData.blocked_vids = [];
                                if(!appData.exercises_chapters) appData.exercises_chapters = [];
                                if(!appData.exercises_unassigned) appData.exercises_unassigned = [];
                                renderPlaylist();
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
            .then(data => {
                appData = data;
                if(!appData.settings) appData.settings = {};
                if(!appData.blocked_vids) appData.blocked_vids = [];
                if(!appData.exercises_chapters) appData.exercises_chapters = [];
                if(!appData.exercises_unassigned) appData.exercises_unassigned = [];
                
                // Init settings UI
                document.getElementById('setting-title').value = appData.settings.course_title || '';
                document.getElementById('setting-author').value = appData.settings.author_name || '';
                document.getElementById('setting-welcome').value = appData.settings.welcome_message || '';
                updateUIHeaders();

                renderPlaylist();
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
                        alert('Lỗi export: ' + data.error);
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
                    alert('Lỗi export: ' + err.error);
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
            
            let btnHtml = pasteBtn + uploadBtn + `<button class="btn btn-sm text-primary p-0 ms-2" onclick="event.stopPropagation(); addFolder('${folder.id}')" title="Thêm mục con"><i class="bi bi-folder-plus"></i></button>`;
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
                        <span class="chapter-title-input" contenteditable="true" onclick="event.stopPropagation()" onblur="saveState()" onkeydown="if(event.key==='Enter') { this.blur(); event.preventDefault(); }">${folder.title}</span>
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
                         <span class="item-title-input" contenteditable="true" onblur="saveState()" onkeydown="if(event.key==='Enter') { this.blur(); event.preventDefault(); }">${item.title || defaultTitle}</span>
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

        function saveStateToServer() {
            fetch('/api/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    settings: appData.settings, 
                    chapters: appData.chapters, 
                    unassigned: appData.unassigned, 
                    exercises_chapters: appData.exercises_chapters,
                    exercises_unassigned: appData.exercises_unassigned,
                    blocked_vids: appData.blocked_vids 
                })
            });
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
                    alert('Lỗi upload: ' + data.error);
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
    