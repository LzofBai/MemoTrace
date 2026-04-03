/**
 * MemoTrace Web 聊天界面 - 带详细日志版本
 * 优化版本：支持头像、图片显示，性能优化
 */

// ==================== 日志模块 ====================
const Logger = {
    logs: [],
    maxLogs: 1000,
    
    log(level, message, data = null) {
        const timestamp = new Date().toISOString();
        const logEntry = {
            timestamp,
            level,
            message,
            data: data ? JSON.stringify(data).substring(0, 500) : null
        };
        
        this.logs.push(logEntry);
        
        // 限制日志数量
        if (this.logs.length > this.maxLogs) {
            this.logs.shift();
        }
        
        // 控制台输出
        const consoleMessage = `[${timestamp}] [${level}] ${message}`;
        switch(level) {
            case 'ERROR':
                console.error(consoleMessage, data || '');
                break;
            case 'WARN':
                console.warn(consoleMessage, data || '');
                break;
            case 'DEBUG':
                console.debug(consoleMessage, data || '');
                break;
            default:
                console.log(consoleMessage, data || '');
        }
        
        // 保存到 localStorage（用于页面刷新后查看）
        this.saveToStorage();
    },
    
    info(message, data) { this.log('INFO', message, data); },
    error(message, data) { this.log('ERROR', message, data); },
    warn(message, data) { this.log('WARN', message, data); },
    debug(message, data) { this.log('DEBUG', message, data); },
    
    saveToStorage() {
        try {
            localStorage.setItem('memotrace_logs', JSON.stringify(this.logs.slice(-200)));
        } catch (e) {
            console.error('日志保存失败:', e);
        }
    },
    
    getLogs() {
        return this.logs;
    },
    
    exportLogs() {
        const logText = this.logs.map(l => 
            `[${l.timestamp}] [${l.level}] ${l.message}${l.data ? ' | DATA: ' + l.data : ''}`
        ).join('\n');
        
        const blob = new Blob([logText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `memotrace_logs_${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    },
    
    clear() {
        this.logs = [];
        localStorage.removeItem('memotrace_logs');
    }
};

// 添加全局错误捕获
window.onerror = function(msg, url, line, col, error) {
    Logger.error('全局错误', { msg, url, line, col, error: error?.stack });
    return false;
};

window.onunhandledrejection = function(event) {
    Logger.error('未处理的Promise拒绝', { reason: event.reason });
};

// ==================== 全局状态 ====================
const state = {
    currentChat: null,      // 当前选中的聊天对象
    currentTab: 'chat',     // 当前标签页
    messages: [],           // 当前聊天记录
    contacts: [],           // 联系人列表
    sessions: [],           // 会话列表
    lastSeq: 0,             // 分页加载用的最后序号
    hasMore: true,          // 是否还有更多消息
    isLoading: false,      // 是否正在加载
    contactsPage: 1,       // 联系人分页
    contactsHasMore: true, // 联系人是否还有更多
    imageCache: new Map(), // 图片缓存
    wechatInfo: null,      // 微信信息
    isKeyVisible: false    // Key是否可见
};

// API 基础地址
const API_BASE = '';

Logger.info('应用初始化开始', { API_BASE, state: JSON.parse(JSON.stringify(state)) });

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', async () => {
    Logger.info('DOM加载完成，开始初始化');
    
    initTabs();
    initSearch();
    initLazyLoad();
    
    // 先测试连接
    Logger.info('测试后端连接...');
    const testResult = await testConnection();
    
    if (testResult && testResult.code === 0) {
        Logger.info('后端连接成功', testResult.data);
        // 并行加载数据
        await Promise.all([
            loadSessions(),
            loadContacts()
        ]);
        Logger.info('初始数据加载完成');
    } else {
        Logger.error('后端连接失败', testResult);
        showError(testResult ? testResult.msg : '无法连接到服务器');
    }
});

// ==================== 测试连接 ====================
async function testConnection() {
    try {
        Logger.debug('发送 /api/test 请求');
        const response = await fetch(`${API_BASE}/api/test`);
        const result = await response.json();
        Logger.info('/api/test 响应', result);
        return result;
    } catch (error) {
        Logger.error('/api/test 请求失败', { error: error.message });
        return null;
    }
}

// ==================== 懒加载初始化 ====================
function initLazyLoad() {
    Logger.debug('初始化图片懒加载');
    
    // 使用 Intersection Observer 实现图片懒加载
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                const src = img.dataset.src;
                if (src) {
                    Logger.debug('懒加载图片', { src: src.substring(0, 50) + '...' });
                    img.src = src;
                    img.removeAttribute('data-src');
                    observer.unobserve(img);
                }
            }
        });
    }, {
        rootMargin: '50px'
    });
    
    window.imageObserver = imageObserver;
    Logger.debug('懒加载初始化完成');
}

// ==================== 标签页切换 ====================
function initTabs() {
    Logger.debug('初始化标签页');
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            Logger.info(`切换标签页: ${tab}`);
            state.currentTab = tab;
            
            // 切换按钮状态
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // 切换内容
            tabContents.forEach(c => c.classList.remove('active'));
            document.getElementById(`${tab}-tab`).classList.add('active');
        });
    });
}

// ==================== 搜索功能 ====================
function initSearch() {
    Logger.debug('初始化搜索功能');
    const searchInput = document.getElementById('search-input');
    let debounceTimer;
    
    searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const keyword = e.target.value.trim();
            Logger.info(`搜索: "${keyword}"`);
            if (keyword) {
                searchContacts(keyword);
            } else {
                state.contactsPage = 1;
                state.contactsHasMore = true;
                loadContacts();
            }
        }, 300);
    });
}

// ==================== 加载会话列表 ====================
async function loadSessions() {
    Logger.info('开始加载会话列表');
    try {
        const response = await fetch(`${API_BASE}/api/session?page_size=100`);
        const result = await response.json();
        
        if (result.code === 0) {
            state.sessions = result.data;
            Logger.info(`会话列表加载成功: ${result.data.length} 个会话`);
            renderChatList(result.data);
        } else {
            Logger.error('会话列表加载失败', result);
        }
    } catch (error) {
        Logger.error('加载会话列表失败', { error: error.message });
        showError('加载会话列表失败');
    }
}

// ==================== 加载联系人列表 ====================
async function loadContacts(append = false) {
    Logger.info(`加载联系人列表: append=${append}, page=${state.contactsPage}`);
    
    if (state.isLoading || (!append && !state.contactsHasMore)) {
        Logger.warn('跳过加载: 正在加载中或无更多数据');
        return;
    }
    
    state.isLoading = true;
    
    try {
        const response = await fetch(`${API_BASE}/api/contacts?page=${state.contactsPage}&page_size=50`);
        const result = await response.json();
        
        if (result.code === 0) {
            Logger.info(`联系人列表加载成功: 本页 ${result.data.length} 个, 总计 ${result.total} 个`);
            
            if (append) {
                state.contacts = [...state.contacts, ...result.data];
            } else {
                state.contacts = result.data;
            }
            
            state.contactsHasMore = result.has_more;
            state.contactsPage = result.page;
            
            renderContacts(state.contacts, append);
        } else {
            Logger.error('联系人列表加载失败', result);
        }
    } catch (error) {
        Logger.error('加载联系人列表失败', { error: error.message });
        showError('加载联系人列表失败');
    } finally {
        state.isLoading = false;
    }
}

// ==================== 加载更多联系人 ====================
function loadMoreContacts() {
    Logger.info('加载更多联系人');
    if (state.contactsHasMore && !state.isLoading) {
        state.contactsPage++;
        loadContacts(true);
    }
}

// ==================== 搜索联系人 ====================
async function searchContacts(keyword) {
    Logger.info(`搜索联系人: "${keyword}"`);
    try {
        const response = await fetch(`${API_BASE}/api/contacts/search?keyword=${encodeURIComponent(keyword)}`);
        const result = await response.json();
        
        if (result.code === 0) {
            Logger.info(`搜索结果: ${result.data.length} 个`);
            if (state.currentTab === 'chat') {
                renderChatList(result.data);
            } else {
                renderContacts(result.data);
            }
        } else {
            Logger.error('搜索失败', result);
        }
    } catch (error) {
        Logger.error('搜索失败', { error: error.message });
    }
}

// ==================== 渲染聊天列表 ====================
function renderChatList(data) {
    Logger.debug(`渲染聊天列表: ${data.length} 个`);
    const chatList = document.getElementById('chat-list');
    
    if (data.length === 0) {
        chatList.innerHTML = '<div class="empty-tip" style="padding: 20px; text-align: center; color: #888;">暂无聊天记录</div>';
        return;
    }
    
    const fragment = document.createDocumentFragment();
    
    data.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = `chat-item ${state.currentChat?.wxid === item.wxid ? 'active' : ''}`;
        div.dataset.wxid = item.wxid;
        div.onclick = () => selectChat(item.wxid, item.remark || item.nickname, item.is_chatroom);
        
        const initial = (item.remark || item.nickname || '?').charAt(0).toUpperCase();
        const avatarUrl = item.avatar_url || '';
        
        div.innerHTML = `
            <img class="avatar lazy-avatar" 
                 data-src="${avatarUrl}" 
                 src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                 alt="${initial}"
                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>${initial}</text></svg>'">
            <div class="info">
                <div class="name">${escapeHtml(item.remark || item.nickname || '未知')}</div>
                <div class="last-message">${escapeHtml(item.last_message || '').substring(0, 30)}</div>
            </div>
            <div class="meta">
                <div class="time">${formatTime(item.last_time) || ''}</div>
                ${item.unread_count > 0 ? `<span class="badge">${item.unread_count}</span>` : ''}
            </div>
        `;
        
        fragment.appendChild(div);
    });
    
    chatList.innerHTML = '';
    chatList.appendChild(fragment);
    
    // 懒加载头像
    document.querySelectorAll('.lazy-avatar').forEach(img => {
        window.imageObserver.observe(img);
    });
    
    Logger.debug('聊天列表渲染完成');
}

// ==================== 渲染联系人列表 ====================
function renderContacts(data, append = false) {
    Logger.debug(`渲染联系人列表: ${data.length} 个, append=${append}`);
    const contactList = document.getElementById('contact-list');
    
    if (data.length === 0 && !append) {
        contactList.innerHTML = '<div class="empty-tip" style="padding: 20px; text-align: center; color: #888;">暂无联系人</div>';
        return;
    }
    
    // 分组：好友和群聊
    const friends = data.filter(c => !c.is_chatroom);
    const groups = data.filter(c => c.is_chatroom);
    
    let html = '';
    
    if (!append) {
        if (friends.length > 0) {
            html += `<div class="group-title" style="padding: 10px 15px; color: #888; font-size: 12px;">好友 (${friends.length})</div>`;
        }
    }
    
    html += friends.map(item => renderContactItem(item)).join('');
    
    if (!append && groups.length > 0) {
        html += `<div class="group-title" style="padding: 10px 15px; color: #888; font-size: 12px;">群聊 (${groups.length})</div>`;
    }
    
    html += groups.map(item => renderContactItem(item)).join('');
    
    // 添加加载更多按钮
    if (state.contactsHasMore) {
        html += `<div class="load-more-contacts" onclick="loadMoreContacts()" style="padding: 15px; text-align: center; color: #07c160; cursor: pointer;">加载更多...</div>`;
    }
    
    if (append) {
        const oldBtn = contactList.querySelector('.load-more-contacts');
        if (oldBtn) oldBtn.remove();
        contactList.insertAdjacentHTML('beforeend', html);
    } else {
        contactList.innerHTML = html;
    }
    
    // 懒加载头像
    document.querySelectorAll('.lazy-avatar').forEach(img => {
        window.imageObserver.observe(img);
    });
    
    Logger.debug('联系人列表渲染完成');
}

function renderContactItem(item) {
    const initial = (item.remark || item.nickname || '?').charAt(0).toUpperCase();
    const avatarUrl = item.avatar_url || '';
    
    return `
        <div class="contact-item ${state.currentChat?.wxid === item.wxid ? 'active' : ''}"
             onclick="selectChat('${item.wxid}', '${escapeHtml(item.remark || item.nickname)}', ${item.is_chatroom})"
             data-wxid="${item.wxid}">
            <img class="avatar lazy-avatar" 
                 data-src="${avatarUrl}" 
                 src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                 alt="${initial}"
                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>${initial}</text></svg>'">
            <div class="info">
                <div class="name">${escapeHtml(item.remark || item.nickname || '未知')}</div>
                <div class="last-message">${item.is_chatroom ? '群聊' : (item.alias || item.wxid)}</div>
            </div>
        </div>
    `;
}

// ==================== 选择聊天对象 ====================
async function selectChat(wxid, name, isChatroom) {
    Logger.info(`选择聊天: wxid=${wxid}, name=${name}, isChatroom=${isChatroom}`);
    
    // 清空当前消息列表（立即反馈，避免显示旧消息）
    document.getElementById('message-list').innerHTML = '<div style="text-align: center; color: #999; padding: 50px;">加载中...</div>';
    
    // 更新当前聊天状态
    const oldChat = state.currentChat;
    state.currentChat = { wxid, name, isChatroom };
    state.messages = [];  // 清空消息数组
    state.lastSeq = 0;    // 重置分页
    state.hasMore = true; // 重置是否有更多
    state.chatroomMembers = null; // 清空群成员缓存
    
    Logger.debug('聊天状态更新', { oldChat, newChat: state.currentChat });
    
    // 更新列表选中状态
    document.querySelectorAll('.chat-item, .contact-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.wxid === wxid) {
            item.classList.add('active');
        }
    });
    
    // 显示聊天界面
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('chat-header').style.display = 'flex';
    document.getElementById('message-list').style.display = 'block';
    document.getElementById('input-area').style.display = 'block';
    document.getElementById('load-more').style.display = 'block';
    
    // 更新聊天头部
    document.getElementById('chat-name').textContent = name;
    document.getElementById('chat-type').textContent = isChatroom ? '群聊' : '';
    
    // 显示/隐藏群成员按钮
    document.getElementById('view-members-btn').style.display = isChatroom ? 'block' : 'none';
    
    // 隐藏群成员侧边栏
    document.getElementById('member-sidebar').style.display = 'none';
    
    // 加载聊天记录
    Logger.info('开始加载聊天记录');
    await loadMessages(wxid, false);
    
    // 如果是群聊，加载群成员
    if (isChatroom) {
        Logger.info('加载群成员');
        loadChatroomMembers(wxid);
    }
}

// ==================== 加载聊天记录 ====================
async function loadMessages(wxid, append = true) {
    Logger.info(`加载聊天记录: wxid=${wxid}, append=${append}, lastSeq=${state.lastSeq}`);
    
    if (state.isLoading || (!append && !state.hasMore)) {
        Logger.warn('跳过加载: 正在加载中或无更多数据');
        return;
    }
    
    state.isLoading = true;
    showLoading(true);
    
    try {
        const url = `${API_BASE}/api/messages?wxid=${encodeURIComponent(wxid)}&page_size=20${state.lastSeq ? `&start_seq=${state.lastSeq}` : ''}`;
        Logger.debug('请求URL', { url });
        
        const response = await fetch(url);
        const result = await response.json();
        
        Logger.info('聊天记录响应', { code: result.code, msgCount: result.data?.length, hasMore: result.has_more });
        
        if (result.code === 0) {
            const newMessages = result.data;
            
            if (newMessages.length === 0) {
                Logger.info('没有更多消息');
                state.hasMore = false;
                document.getElementById('load-more').style.display = 'none';
                if (!append) {
                    document.getElementById('message-list').innerHTML = '<div style="text-align: center; color: #999; padding: 50px;">暂无消息</div>';
                }
            } else {
                if (append) {
                    state.messages = [...state.messages, ...newMessages];
                    Logger.info(`追加 ${newMessages.length} 条消息, 当前共 ${state.messages.length} 条`);
                } else {
                    state.messages = newMessages;
                    Logger.info(`加载 ${newMessages.length} 条新消息`);
                }
                
                state.lastSeq = result.last_seq;
                state.hasMore = result.has_more;
                
                renderMessages(state.messages, append);
            }
        } else {
            Logger.error('加载消息失败', result);
            showError(result.msg || '加载消息失败');
            if (!append) {
                document.getElementById('message-list').innerHTML = '<div style="text-align: center; color: #999; padding: 50px;">加载失败</div>';
            }
        }
    } catch (error) {
        Logger.error('加载消息异常', { error: error.message, stack: error.stack });
        showError('加载消息失败');
        if (!append) {
            document.getElementById('message-list').innerHTML = '<div style="text-align: center; color: #999; padding: 50px;">加载失败</div>';
        }
    } finally {
        state.isLoading = false;
        showLoading(false);
    }
}

// ==================== 显示/隐藏加载状态 ====================
function showLoading(show) {
    let loadingEl = document.getElementById('global-loading');
    if (!loadingEl) {
        loadingEl = document.createElement('div');
        loadingEl.id = 'global-loading';
        loadingEl.innerHTML = '<div class="loading"></div>';
        loadingEl.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 9999;
            display: none;
        `;
        document.body.appendChild(loadingEl);
    }
    loadingEl.style.display = show ? 'block' : 'none';
    Logger.debug(`加载状态: ${show ? '显示' : '隐藏'}`);
}

// ==================== 加载更多消息 ====================
function loadMoreMessages() {
    Logger.info('加载更多消息');
    if (state.currentChat && !state.isLoading) {
        loadMessages(state.currentChat.wxid, true);
    }
}

// ==================== 渲染消息列表 ====================
function renderMessages(messages, append = false) {
    Logger.debug(`渲染消息列表: ${messages.length} 条, append=${append}`);
    const messageList = document.getElementById('message-list');
    
    if (!append) {
        messageList.innerHTML = '';
    }
    
    if (messages.length === 0) {
        messageList.innerHTML = '<div style="text-align: center; color: #999; padding: 50px;">暂无消息</div>';
        return;
    }
    
    // 按时间分组
    let lastDate = null;
    const fragment = document.createDocumentFragment();
    
    messages.forEach((msg, index) => {
        const date = new Date(msg.timestamp * 1000);
        const dateStr = formatDate(date);
        
        if (dateStr !== lastDate) {
            const timeDiv = document.createElement('div');
            timeDiv.className = 'time-divider';
            timeDiv.innerHTML = `<span>${dateStr}</span>`;
            fragment.appendChild(timeDiv);
            lastDate = dateStr;
        }
        
        const isSelf = msg.is_sender;
        const isSystem = msg.type === 10000;
        
        if (isSystem) {
            const systemDiv = document.createElement('div');
            systemDiv.className = 'message system';
            systemDiv.innerHTML = `<div class="message-bubble">${escapeHtml(msg.content)}</div>`;
            fragment.appendChild(systemDiv);
            return;
        }
        
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${isSelf ? 'self' : ''}`;
        msgDiv.dataset.id = msg.server_id;
        
        const bubbleContent = formatMessageContent(msg);
        
        // 确定发送者ID和头像
        let senderId, senderName, avatarUrl;
        if (isSelf) {
            senderId = 'me';
            senderName = '我';
            avatarUrl = '';
        } else {
            senderId = msg.sender_id || msg.talker_id;
            senderName = msg.display_name || '未知';
            avatarUrl = `${API_BASE}/api/avatar/${encodeURIComponent(senderId)}`;
        }
        
        const initial = senderName.charAt(0).toUpperCase();
        const avatarBg = isSelf ? '#07c160' : stringToColor(senderId);
        
        // 构建头像HTML
        const avatarHtml = isSelf 
            ? `<div class="message-avatar" style="background: ${avatarBg}; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px;">我</div>`
            : `<img class="message-avatar lazy-avatar" data-src="${avatarUrl}" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="${initial}" onerror="this.style.background='${avatarBg}'; this.style.display='flex'; this.style.alignItems='center'; this.style.justifyContent='center'; this.outerHTML='<div class=\\'message-avatar\\' style=\\'background: ${avatarBg}; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 14px;\\'>${initial}</div>'">`;
        
        msgDiv.innerHTML = `
            ${!isSelf ? avatarHtml : ''}
            <div class="message-content">
                ${!isSelf ? `<div class="message-sender">${escapeHtml(senderName)}</div>` : ''}
                <div class="message-bubble ${msg.type === 3 ? 'image' : ''}">
                    ${bubbleContent}
                </div>
            </div>
            ${isSelf ? avatarHtml : ''}
        `;
        
        fragment.appendChild(msgDiv);
    });
    
    if (append && messageList.firstChild) {
        messageList.insertBefore(fragment, messageList.firstChild);
    } else {
        messageList.appendChild(fragment);
        if (!append) {
            messageList.scrollTop = messageList.scrollHeight;
        }
    }
    
    // 懒加载头像和图片
    document.querySelectorAll('.lazy-image, .lazy-avatar').forEach(img => {
        window.imageObserver.observe(img);
    });
    
    Logger.debug('消息列表渲染完成');
}

// ==================== 格式化消息内容 ====================
function formatMessageContent(msg) {
    const type = msg.type;
    const content = msg.content || '';
    
    // 文本消息
    if (type === 1 || type === 2) {
        return escapeHtml(content).replace(/\n/g, '<br>');
    }
    
    // 图片消息
    if (type === 3) {
        const thumbUrl = msg.thumb_url || '';
        const fullUrl = msg.image_url || '';
        const filePath = msg.file_path || '';
        
        Logger.debug('格式化图片消息', { 
            server_id: msg.server_id, 
            thumbUrl: thumbUrl ? thumbUrl.substring(0, 50) + '...' : '无', 
            fullUrl: fullUrl ? fullUrl.substring(0, 50) + '...' : '无',
            filePath: filePath ? filePath.substring(0, 50) + '...' : '无'
        });
        
        if (thumbUrl || fullUrl) {
            const imageUrl = fullUrl || thumbUrl;
            // 添加时间戳防止缓存
            const cacheBuster = `&_t=${Date.now()}`;
            const finalUrl = imageUrl.includes('?') ? imageUrl + cacheBuster : imageUrl + '?' + cacheBuster.substring(1);
            
            return `
                <div class="image-wrapper" style="position: relative; display: inline-block;">
                    <img class="lazy-image chat-image" 
                         data-src="${imageUrl}" 
                         src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                         alt="图片" 
                         onclick="previewImage('${imageUrl}')"
                         onload="Logger.debug('图片加载成功', {server_id: '${msg.server_id}'})"
                         onerror="Logger.error('图片加载失败', {server_id: '${msg.server_id}', url: '${imageUrl}'}); this.outerHTML='<div class=\\'image-error\\' style=\\'padding: 10px; background: #f5f5f5; border-radius: 4px; color: #999; font-size: 12px;\\'><span class=\\'msg-type-badge\\'>图片</span> 加载失败<br><small>${filePath ? escapeHtml(filePath).substring(0, 30) + '...' : '无路径'}</small></div>'"
                         style="max-width: 200px; max-height: 200px; border-radius: 4px; cursor: pointer; display: block;">
                </div>
            `;
        }
        return '<span class="msg-type-badge">图片</span> [图片路径缺失]';
    }
    
    // 语音消息
    if (type === 34) {
        const duration = msg.duration || 0;
        const text = msg.audio_text || '';
        return `
            <span class="msg-type-badge">语音</span>
            <div class="voice-message" style="display: flex; align-items: center; gap: 8px; min-width: 80px;">
                <i class="fas fa-play-circle" style="font-size: 18px;"></i>
                <span>${duration}"</span>
                ${text ? `<div style="font-size: 12px; color: #666; margin-top: 4px; margin-left: 8px;">${escapeHtml(text)}</div>` : ''}
            </div>
        `;
    }
    
    // 视频消息
    if (type === 43) {
        return '<span class="msg-type-badge">视频</span> [视频]';
    }
    
    // 文件消息
    if (type === 25769803825 || content.includes('文件')) {
        const fileName = msg.file_name || '未知文件';
        const fileSize = msg.file_size ? formatFileSize(msg.file_size) : '';
        return `
            <span class="msg-type-badge">文件</span>
            <div class="file-message" style="display: flex; align-items: center; gap: 10px; min-width: 200px;">
                <i class="far fa-file" style="font-size: 40px; color: #999;"></i>
                <div class="file-info">
                    <div class="file-name" style="font-size: 14px; margin-bottom: 4px;">${escapeHtml(fileName)}</div>
                    <div class="file-size" style="font-size: 12px; color: #999;">${fileSize}</div>
                </div>
            </div>
        `;
    }
    
    // 链接消息
    if (type === 21474836529 || type === 292057776177) {
        return `<span class="msg-type-badge">链接</span> ${escapeHtml(content.substring(0, 100))}`;
    }
    
    // 红包
    if (type === 8594229559345) {
        return '<span class="msg-type-badge">红包</span> [红包]';
    }
    
    // 转账
    if (type === 8589934592049) {
        return '<span class="msg-type-badge">转账</span> [转账]';
    }
    
    // 名片
    if (type === 42) {
        return '<span class="msg-type-badge">名片</span> [名片]';
    }
    
    // 位置
    if (type === 48) {
        return '<span class="msg-type-badge">位置</span> [位置]';
    }
    
    // 默认
    return `<span class="msg-type-badge">${msg.type_name}</span> ${escapeHtml(content.substring(0, 200))}`;
}

// ==================== 加载群成员 ====================
async function loadChatroomMembers(roomId) {
    Logger.info(`加载群成员: roomId=${roomId}`);
    try {
        const response = await fetch(`${API_BASE}/api/chatroom/members?room_id=${encodeURIComponent(roomId)}`);
        const result = await response.json();
        
        if (result.code === 0) {
            state.chatroomMembers = result.data;
            Logger.info(`群成员加载成功: ${result.data.length} 人`);
        } else {
            Logger.error('群成员加载失败', result);
        }
    } catch (error) {
        Logger.error('加载群成员失败', { error: error.message });
    }
}

// ==================== 显示/隐藏群成员侧边栏 ====================
document.getElementById('view-members-btn')?.addEventListener('click', () => {
    Logger.info('切换群成员侧边栏');
    const sidebar = document.getElementById('member-sidebar');
    sidebar.style.display = sidebar.style.display === 'none' ? 'block' : 'none';
    
    if (state.chatroomMembers) {
        const memberList = document.getElementById('member-list');
        memberList.innerHTML = state.chatroomMembers.map(member => {
            const initial = (member.remark || member.nickname || '?').charAt(0).toUpperCase();
            const avatarUrl = member.avatar_url || '';
            
            return `
                <div class="member-item">
                    <img class="avatar lazy-avatar" 
                         data-src="${avatarUrl}" 
                         src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
                         alt="${initial}"
                         style="width: 35px; height: 35px; border-radius: 4px; margin-right: 10px; background: #ddd;"
                         onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>${initial}</text></svg>'">
                    <span>${escapeHtml(member.remark || member.nickname || '未知')}</span>
                </div>
            `;
        }).join('');
        
        document.querySelectorAll('.lazy-avatar').forEach(img => {
            window.imageObserver.observe(img);
        });
    }
});

function closeMemberSidebar() {
    Logger.debug('关闭群成员侧边栏');
    document.getElementById('member-sidebar').style.display = 'none';
}

// ==================== 工具函数 ====================

// HTML 转义
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 字符串转颜色
function stringToColor(str) {
    if (!str) return '#999';
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const colors = ['#07c160', '#1890ff', '#722ed1', '#eb2f96', '#fa541c', '#faad14', '#52c41a', '#13c2c2'];
    return colors[Math.abs(hash) % colors.length];
}

// 格式化时间
function formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 86400000 && date.getDate() === now.getDate()) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }
    if (diff < 172800000 && date.getDate() === now.getDate() - 1) {
        return '昨天';
    }
    if (diff < 604800000) {
        const days = ['日', '一', '二', '三', '四', '五', '六'];
        return `星期${days[date.getDay()]}`;
    }
    return `${date.getMonth() + 1}/${date.getDate()}`;
}

// 格式化日期
function formatDate(date) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today - 86400000);
    const dateOnly = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    
    if (dateOnly.getTime() === today.getTime()) {
        return '今天';
    }
    if (dateOnly.getTime() === yesterday.getTime()) {
        return '昨天';
    }
    
    return date.toLocaleDateString('zh-CN', { 
        month: 'long', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 显示错误
function showError(message) {
    Logger.error('显示错误提示', { message });
    
    let errorDiv = document.getElementById('error-toast');
    if (!errorDiv) {
        errorDiv = document.createElement('div');
        errorDiv.id = 'error-toast';
        errorDiv.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #fa5151;
            color: white;
            padding: 12px 24px;
            border-radius: 4px;
            z-index: 9999;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;
        document.body.appendChild(errorDiv);
    }
    
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

// 图片预览
function previewImage(url) {
    Logger.info('预览图片', { url });
    if (url) {
        window.open(url, '_blank');
    }
}

// ==================== 监听滚动加载更多 ====================
document.getElementById('message-list')?.addEventListener('scroll', (e) => {
    if (e.target.scrollTop === 0 && state.hasMore && !state.isLoading) {
        Logger.debug('滚动到顶部，触发加载更多');
        loadMoreMessages();
    }
});

// 联系人列表滚动加载
document.getElementById('contact-list')?.addEventListener('scroll', (e) => {
    const el = e.target;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 50) {
        Logger.debug('联系人列表滚动到底部，触发加载更多');
        loadMoreContacts();
    }
});

// ==================== 日志导出功能 ====================
// 添加键盘快捷键 Ctrl+Shift+L 导出日志
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'L') {
        Logger.info('用户导出日志');
        Logger.exportLogs();
        alert('日志已导出！');
    }
});

Logger.info('应用初始化脚本加载完成');

// ==================== 微信信息获取功能 ====================

/**
 * 从运行的微信进程中获取信息（包括Key）
 */
async function fetchWechatInfo() {
    Logger.info('开始获取微信信息...');
    
    const btn = document.getElementById('btn-get-info');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 获取中...';
    btn.disabled = true;
    
    updateParseStatus('正在获取微信信息...', 10);
    
    try {
        const response = await fetch(`${API_BASE}/api/wechat/info`);
        const result = await response.json();
        
        Logger.info('微信信息获取结果', result);
        
        if (result.code === 0 && result.data && result.data.length > 0) {
            // 获取第一个微信账号的信息
            const info = result.data[0];
            state.wechatInfo = info;
            
            // 填充表单
            document.getElementById('wx-version').value = info.type === 'v4' ? '4' : '3';
            document.getElementById('wx-mobile').value = info.mobile || '';
            document.getElementById('wx-name').value = info.name || '';
            document.getElementById('wx-wxid').value = info.wxid || '';
            document.getElementById('wx-key').value = info.key || '';
            document.getElementById('wx-path').value = info.wx_dir || '';
            
            // 检查是否有Key
            if (info.key && info.key !== 'None' && info.key !== '') {
                updateParseStatus('已获取Key，可以解析数据', 50, true);
                enableParseButtons(true);
                Logger.info('成功获取微信信息和Key', { wxid: info.wxid, name: info.name });
            } else {
                updateParseStatus('未获取到Key，请重启微信后重试', 30, false, true);
                enableParseButtons(false);
                Logger.warn('获取微信信息成功，但未获取到Key');
            }
        } else {
            const msg = result.msg || '未找到登录的微信';
            updateParseStatus(msg, 0, false, true);
            enableParseButtons(false);
            Logger.error('获取微信信息失败', result);
            showError(msg);
        }
    } catch (error) {
        Logger.error('获取微信信息异常', { error: error.message });
        updateParseStatus('获取失败: ' + error.message, 0, false, true);
        enableParseButtons(false);
        showError('获取微信信息失败: ' + error.message);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

/**
 * 切换Key显示/隐藏
 */
function toggleKeyVisibility() {
    const keyInput = document.getElementById('wx-key');
    const icon = document.getElementById('key-toggle-icon');
    
    state.isKeyVisible = !state.isKeyVisible;
    
    if (state.isKeyVisible) {
        keyInput.type = 'text';
        icon.className = 'fas fa-eye-slash';
    } else {
        keyInput.type = 'password';
        icon.className = 'fas fa-eye';
    }
}

/**
 * 选择微信路径（模拟，实际需要通过后端或文件选择器）
 */
async function selectWechatPath() {
    Logger.info('选择微信路径...');
    // 这里可以通过input type="file" webkitdirectory来实现文件夹选择
    // 暂时使用prompt模拟
    const path = prompt('请输入微信数据文件夹路径（包含Msg文件夹的路径）:', 
        document.getElementById('wx-path').value || 'C:\\Users\\YourName\\Documents\\WeChat Files\\wxid_xxx');
    
    if (path) {
        document.getElementById('wx-path').value = path;
        Logger.info('已设置微信路径', { path });
        checkReadyToParse();
    }
}

/**
 * 更新解析状态显示
 */
function updateParseStatus(text, progress, isReady = false, isError = false) {
    const statusEl = document.getElementById('parse-status');
    const progressEl = document.getElementById('parse-progress');
    const progressFill = document.getElementById('progress-fill');
    
    statusEl.textContent = text;
    progressEl.textContent = progress + '%';
    progressFill.style.width = progress + '%';
    
    statusEl.className = 'status-text';
    progressFill.className = 'progress-fill';
    
    if (isReady) {
        statusEl.classList.add('ready');
    } else if (isError) {
        statusEl.classList.add('error');
        progressFill.classList.add('error');
    }
}

/**
 * 启用/禁用解析按钮
 */
function enableParseButtons(enabled) {
    document.getElementById('btn-parse').disabled = !enabled;
    document.getElementById('btn-incremental').disabled = !enabled;
}

/**
 * 检查是否可以解析
 */
function checkReadyToParse() {
    const wxid = document.getElementById('wx-wxid').value.trim();
    const path = document.getElementById('wx-path').value.trim();
    
    if (wxid && path) {
        updateParseStatus('信息完整，可以解析数据', 50, true);
        enableParseButtons(true);
    }
}

/**
 * 解析数据（进入主界面）
 */
async function parseData() {
    Logger.info('开始解析数据...');
    
    const wxid = document.getElementById('wx-wxid').value.trim();
    const path = document.getElementById('wx-path').value.trim();
    const version = document.getElementById('wx-version').value;
    
    if (!wxid || !path) {
        showError('请填写完整信息');
        return;
    }
    
    updateParseStatus('正在解析数据...', 70);
    
    try {
        // 这里可以调用后端API来设置数据库路径和版本
        // 暂时直接关闭登录界面进入主界面
        
        // 更新用户信息显示
        const name = document.getElementById('wx-name').value || wxid;
        document.querySelector('.user-profile .username').textContent = name;
        
        // 隐藏登录界面，显示主界面
        document.getElementById('login-modal').style.display = 'none';
        
        updateParseStatus('解析完成', 100, true);
        Logger.info('数据解析完成，进入主界面');
        
        // 重新加载数据
        await testConnection();
        await Promise.all([
            loadSessions(),
            loadContacts()
        ]);
        
    } catch (error) {
        Logger.error('解析数据失败', { error: error.message });
        updateParseStatus('解析失败: ' + error.message, 0, false, true);
        showError('解析数据失败: ' + error.message);
    }
}

/**
 * 增量解析
 */
async function parseIncremental() {
    Logger.info('开始增量解析...');
    updateParseStatus('正在增量解析...', 75);
    
    // 增量解析逻辑与完整解析类似
    // 实际应用中这里应该调用不同的后端API
    await parseData();
}

// 页面加载时自动尝试获取微信信息
document.addEventListener('DOMContentLoaded', () => {
    // 延迟一点执行，确保其他初始化完成
    setTimeout(() => {
        Logger.info('自动尝试获取微信信息...');
        fetchWechatInfo();
    }, 500);
});
