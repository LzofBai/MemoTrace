/**
 * 聊天记录导出功能模块 - 下拉选择框版本
 * 支持多种格式：HTML, TXT, Markdown, Excel, JSON, CSV, DOCX, AI_TXT
 */

// 导出配置缓存
let exportConfig = null;
let chatroomMembers = [];

// 初始化导出功能
document.addEventListener('DOMContentLoaded', () => {
    // 绑定导出按钮事件
    document.getElementById('export-btn')?.addEventListener('click', openExportModal);
    
    // 加载导出配置
    loadExportConfig();
});

/**
 * 加载导出配置
 */
async function loadExportConfig() {
    try {
        const response = await fetch(`${API_BASE}/api/export/config`);
        const result = await response.json();
        
        if (result.code === 0) {
            exportConfig = result.data;
            
            // 检查 exporter 是否可用
            if (!exportConfig.exporter_available) {
                console.warn('导出模块不可用:', exportConfig.exporter_error);
            }
            
            renderExportFormats(exportConfig.formats);
            renderMessageTypes(exportConfig.message_types);
            renderDateRanges(exportConfig.date_ranges);
        }
    } catch (error) {
        Logger.error('加载导出配置失败', { error: error.message });
    }
}

/**
 * 渲染导出格式下拉框
 */
function renderExportFormats(formats) {
    const container = document.getElementById('export-format-select');
    if (!container) return;
    
    // 过滤出可用的格式
    const availableFormats = formats.filter(f => f.available);
    
    if (availableFormats.length === 0) {
        container.innerHTML = '<option value="">无可用的导出格式</option>';
        container.disabled = true;
        return;
    }
    
    container.innerHTML = availableFormats.map(format => `
        <option value="${format.value}" 
                data-icon="${format.icon}"
                data-color="${format.color}"
                title="${format.description}">
            ${format.label} - ${format.description}
        </option>
    `).join('');
    
    container.disabled = false;
}

/**
 * 渲染消息类型复选框列表
 */
function renderMessageTypes(types) {
    const container = document.getElementById('msg-type-checkbox-list');
    if (!container) return;
    
    container.innerHTML = types.map(type => `
        <label class="msg-type-checkbox-item" title="${type.label}">
            <input type="checkbox" name="msg_type" value="${type.value}" checked onchange="updateExportHint()">
            <i class="fas ${type.icon}"></i>
            <span>${type.label}</span>
        </label>
    `).join('');
}

/**
 * 渲染日期范围下拉框
 */
function renderDateRanges(ranges) {
    const container = document.getElementById('export-date-range-select');
    if (!container) return;
    
    container.innerHTML = ranges.map(range => `
        <option value="${range.value}">${range.label}</option>
    `).join('');
    
    // 绑定变化事件
    container.addEventListener('change', handleDateRangeChange);
}

/**
 * 切换所有消息类型选择
 */
window.toggleAllMsgTypes = function(checked) {
    document.querySelectorAll('input[name="msg_type"]').forEach(cb => {
        cb.checked = checked;
    });
    updateExportHint();
};

/**
 * 全选/取消全选选项
 */
window.selectAllOptions = function(selectId, select) {
    const selectEl = document.getElementById(selectId);
    if (!selectEl) return;
    
    Array.from(selectEl.options).forEach(opt => opt.selected = select);
    updateExportHint();
};

/**
 * 打开导出模态框
 */
async function openExportModal() {
    Logger.info('打开导出模态框');
    
    if (!state.currentChat) {
        showError('请先选择一个聊天');
        return;
    }
    
    // 重置表单
    resetExportForm();
    
    // 设置默认日期范围
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('end-date').value = today;
    
    const monthAgo = new Date();
    monthAgo.setMonth(monthAgo.getMonth() - 1);
    document.getElementById('start-date').value = monthAgo.toISOString().split('T')[0];
    
    // 如果是群聊，加载群成员
    if (state.currentChat.isChatroom) {
        await loadChatroomMembersForExport();
    } else {
        document.getElementById('member-select-section').style.display = 'none';
    }
    
    // 显示模态框
    document.getElementById('export-modal').style.display = 'flex';
    
    // 更新提示
    updateExportHint();
}

/**
 * 关闭导出模态框
 */
window.closeExportModal = function() {
    Logger.info('关闭导出模态框');
    document.getElementById('export-modal').style.display = 'none';
};

/**
 * 重置导出表单
 */
function resetExportForm() {
    // 重置日期范围
    const dateRangeSelect = document.getElementById('export-date-range-select');
    if (dateRangeSelect) dateRangeSelect.value = 'month';
    
    // 隐藏自定义日期
    document.getElementById('custom-date-picker').style.display = 'none';
    
    // 重置消息类型为全选
    document.querySelectorAll('input[name="msg_type"]').forEach(cb => cb.checked = true);
    document.getElementById('select-all-msg-types').checked = true;
    
    // 重置成员搜索
    const memberSearch = document.getElementById('member-search-input');
    if (memberSearch) memberSearch.value = '';
}

/**
 * 处理日期范围变化
 */
function handleDateRangeChange(e) {
    const customPicker = document.getElementById('custom-date-picker');
    if (e.target.value === 'custom') {
        customPicker.style.display = 'grid';
    } else {
        customPicker.style.display = 'none';
    }
    updateExportHint();
}

/**
 * 加载群成员（用于导出）
 */
async function loadChatroomMembersForExport() {
    if (!state.currentChat || !state.currentChat.isChatroom) return;
    
    Logger.info('加载群成员用于导出');
    
    try {
        const response = await fetch(`${API_BASE}/api/export/members?wxid=${encodeURIComponent(state.currentChat.wxid)}`);
        const result = await response.json();
        
        if (result.code === 0) {
            chatroomMembers = result.data;
            renderMemberSelect(chatroomMembers);
            document.getElementById('member-select-section').style.display = 'block';
        }
    } catch (error) {
        Logger.error('加载群成员失败', { error: error.message });
        document.getElementById('member-select-section').style.display = 'none';
    }
}

/**
 * 渲染成员选择下拉框（带搜索）
 */
function renderMemberSelect(members) {
    const container = document.getElementById('export-member-select');
    const searchInput = document.getElementById('member-search-input');
    
    if (!container) return;
    
    if (members.length === 0) {
        container.innerHTML = '<option value="">暂无成员数据</option>';
        container.disabled = true;
        return;
    }
    
    // 渲染选项
    const renderOptions = (filterText = '') => {
        const filtered = members.filter(m => 
            m.display_name.toLowerCase().includes(filterText.toLowerCase()) ||
            m.wxid.toLowerCase().includes(filterText.toLowerCase())
        );
        
        container.innerHTML = `
            <option value="__all__" selected>全部成员 (${members.length}人)</option>
            ${filtered.map(member => `
                <option value="${member.wxid}">
                    ${escapeHtml(member.display_name)} (${member.wxid})
                </option>
            `).join('')}
        `;
    };
    
    // 初始渲染
    renderOptions();
    
    // 绑定搜索
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            renderOptions(e.target.value);
        });
    }
    
    container.disabled = false;
}

/**
 * 更新导出提示
 */
function updateExportHint() {
    const dateRangeSelect = document.getElementById('export-date-range-select');
    const formatSelect = document.getElementById('export-format-select');
    
    const dateRange = dateRangeSelect?.value || 'month';
    const selectedMsgTypes = document.querySelectorAll('input[name="msg_type"]:checked').length;
    const totalMsgTypes = document.querySelectorAll('input[name="msg_type"]').length;
    const exportFormat = formatSelect?.value || 'html';
    
    const formatLabel = exportConfig?.formats?.find(f => f.value === exportFormat)?.label || exportFormat.toUpperCase();
    
    let hint = `将导出 ${formatLabel} 格式的`;
    
    // 时间范围
    const dateRangeLabel = exportConfig?.date_ranges?.find(r => r.value === dateRange)?.label || dateRange;
    hint += `${dateRangeLabel}`;
    
    // 消息类型
    hint += `，${selectedMsgTypes}/${totalMsgTypes} 种类型`;
    
    // 成员
    if (state.currentChat?.isChatroom) {
        const memberSelect = document.getElementById('export-member-select');
        const selectedValue = memberSelect?.value;
        if (selectedValue === '__all__') {
            hint += `，全部成员`;
        } else if (selectedValue) {
            const selectedText = memberSelect.selectedOptions[0]?.text || '';
            hint += `，${selectedText.split('(')[0]}`;
        }
    }
    
    hint += '的聊天记录';
    
    const hintEl = document.getElementById('export-hint');
    if (hintEl) hintEl.textContent = hint;
}

/**
 * 确认导出
 */
window.confirmExport = async function() {
    Logger.info('开始导出聊天记录');
    
    const btn = document.getElementById('confirm-export-btn');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 导出中...';
    
    try {
        // 收集参数
        const dateRangeSelect = document.getElementById('export-date-range-select');
        const formatSelect = document.getElementById('export-format-select');
        
        const dateRange = dateRangeSelect?.value || 'month';
        const msgTypes = Array.from(document.querySelectorAll('input[name="msg_type"]:checked')).map(cb => cb.value);
        const exportFormat = formatSelect?.value || 'html';
        
        // 检查是否有可用的导出格式
        if (!exportFormat) {
            throw new Error('请选择导出格式');
        }
        
        Logger.info('准备导出', { format: exportFormat, dateRange, msgTypesCount: msgTypes.length });
        
        const params = {
            wxid: state.currentChat.wxid,
            contact_name: state.currentChat.name,
            format: exportFormat,
            date_range: dateRange,
            message_types: msgTypes
        };
        
        // 自定义时间
        if (dateRange === 'custom') {
            params.start_date = document.getElementById('start-date').value;
            params.end_date = document.getElementById('end-date').value;
            
            if (!params.start_date || !params.end_date) {
                throw new Error('请选择开始和结束日期');
            }
        }
        
        // 成员筛选（群聊）
        if (state.currentChat.isChatroom) {
            const memberSelect = document.getElementById('export-member-select');
            const selectedValue = memberSelect?.value;
            if (selectedValue && selectedValue !== '__all__') {
                params.sender_ids = [selectedValue];
            }
        }
        
        Logger.info('导出参数', params);
        
        // 发送请求
        const response = await fetch(`${API_BASE}/api/export/file`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.msg || '导出失败');
        }
        
        // 下载文件
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // 从响应头获取文件名
        const contentDisposition = response.headers.get('content-disposition');
        // 确定正确的文件扩展名
        const extMap = {
            'html': 'html', 'txt': 'txt', 'ai_txt': 'txt',
            'markdown': 'md', 'xlsx': 'xlsx', 'json': 'json',
            'csv': 'csv', 'docx': 'docx'
        };
        const correctExt = extMap[exportFormat] || exportFormat;
        const defaultFilename = `聊天记录_${state.currentChat.name}_${exportFormat.toUpperCase()}_${new Date().toISOString().slice(0,10)}.${correctExt}`;
        let filename = defaultFilename;
        if (contentDisposition) {
            // 优先匹配 filename="..." 或 filename=...
            const match = contentDisposition.match(/filename="?([^";]+)"?/);
            if (match && match[1]) {
                filename = match[1].trim();
                console.log('[EXPORT] 从响应头获取文件名:', filename);
            } else {
                console.log('[EXPORT] 无法从响应头解析文件名，使用默认:', defaultFilename);
            }
        } else {
            console.log('[EXPORT] 响应头中没有 Content-Disposition，使用默认文件名');
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        Logger.info('导出成功', { filename, format: exportFormat });
        closeExportModal();
        showError('导出成功！');
        
    } catch (error) {
        Logger.error('导出失败', { error: error.message });
        showError('导出失败: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
};

// 监听选择变化更新提示
document.addEventListener('change', (e) => {
    if (e.target.matches('#export-date-range-select, #export-format-select, #export-member-select, input[name="msg_type"]')) {
        updateExportHint();
    }
});
