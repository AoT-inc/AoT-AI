/**
 * aot-ai-global.js
 * Global AI Assistant Singleton for AoT
 */

const AoT_AI = (function() {
    let threadId = localStorage.getItem('aot_ai_thread_id') || null;
    let isOpen = false;
    let pageContext = null;
    let currentAbortController = null;

    function _getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function _init() {
        // console.log("AoT AI: Initializing Global Assistant...");

        _renderUI();
        _bindEvents();

        // REQ-3: Always hydrate from the server on mount so that conversation
        // history is restored even if browser storage was cleared.
        _hydrateFromServer();
    }

    /**
     * REQ-3: Hydrate conversation history from server on every page load.
     * If threadId is cached in localStorage, load that thread.
     * Otherwise fetch the user's thread list and restore the most recent one.
     */
    async function _hydrateFromServer() {
        if (threadId) {
            // Thread ID is cached — load its messages from the server (REQ-3)
            _loadHistory(0);
        } else {
            // localStorage was cleared or first visit — recover latest thread from server
            try {
                const resp = await fetch('/api/chat/history');
                if (!resp.ok) return;
                const data = await resp.json();
                if (data.threads && data.threads.length > 0) {
                    threadId = data.threads[0].thread_id;
                    // Repopulate localStorage cache from server data
                    localStorage.setItem('aot_ai_thread_id', threadId);
                    _loadHistory(0);
                }
            } catch (err) {
                console.warn("AoT AI: Could not recover thread list from server", err);
            }
        }
    }

    function _renderUI() {
        // Check if UI elements already exist in HTML (from layout_default.html)
        const existingFab = document.getElementById('ai-fab');
        const existingDrawer = document.getElementById('ai-chat-drawer');
        
        if (existingFab && existingDrawer) {
            // console.log("AoT AI: Using existing UI elements from HTML");
            return; // Use existing HTML elements
        }
        
        // Legacy fallback: Create UI if not found (should not happen with new layout)
        console.warn("AoT AI: HTML elements not found, creating dynamically (legacy mode)");
        
        if (!document.getElementById('aot-ai-fab')) {
            // FAB
            const fab = document.createElement('button');
            fab.id = 'aot-ai-fab';
            fab.innerHTML = '<span class="fab-text">AI</span>';
            document.body.appendChild(fab);
        }

        if (!document.getElementById('aot-ai-drawer')) {
            // Drawer
            const drawer = document.createElement('div');
            drawer.id = 'aot-ai-drawer';
            drawer.innerHTML = `
                <div class="ai-drawer-header">
                    <h5>AI Assistant</h5>
                    <button class="ai-close-btn">&times;</button>
                </div>
                <div class="ai-drawer-body" id="ai-messages-container">
                    <div class="ai-msg ai-msg-bot">안녕하세요! 무엇을 도와드릴까요? AoT 시스템의 설정이나 상태에 대해 무엇이든 물어보세요.</div>
                </div>
                <div class="ai-drawer-footer">
                    <div id="ai-context-indicator"></div>
                    <div class="ai-input-group">
                        <textarea id="ai-global-input" placeholder="메시지를 입력하세요..." rows="1"></textarea>
                        <button class="ai-send-btn">
                            <span class="btn-icon">
                                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                            </span>
                        </button>
                    </div>
                </div>
            `;
            document.body.appendChild(drawer);
        }
    }

    function _bindEvents() {
        // Support both old IDs (legacy) and new IDs (from HTML)
        const fab = document.getElementById('ai-fab') || document.getElementById('aot-ai-fab');
        const closeBtn = document.getElementById('ai-close-btn') || document.querySelector('.ai-close-btn');
        const sendBtn = document.getElementById('ai-send-btn') || document.querySelector('.ai-send-btn');
        const input = document.getElementById('ai-chat-input') || document.getElementById('ai-global-input');

        if (!fab || !closeBtn || !sendBtn || !input) {
            console.error("AoT AI: Required UI elements not found", { fab, closeBtn, sendBtn, input });
            return;
        }

        fab.addEventListener('click', () => AoT_AI.toggleChat());
        closeBtn.addEventListener('click', () => AoT_AI.closeChat());

        // Infinite Scroll Listener
        const container = document.getElementById('ai-chat-messages') || document.getElementById('ai-messages-container');
        if (container) {
            container.addEventListener('scroll', () => {
                if (container.scrollTop === 0 && !container.classList.contains('loading-history')) {
                    const currentCount = container.querySelectorAll('.ai-msg').length;
                    _loadHistory(currentCount);
                }
            });
        }

        sendBtn.addEventListener('click', () => _handleSend());
        
        // Handle textarea auto-height and shortcuts
        input.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });

        input.addEventListener('keydown', (e) => {
            // Handle IME composition (prevents double send on Korean/Japanese input)
            if (e.isComposing || e.keyCode === 229) return;

            // Send on Enter (without Shift)
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                _handleSend();
            }
            
            // Legacy support: Send on Cmd/Ctrl + Enter
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                e.preventDefault();
                _handleSend();
            }
        });

        // Listen for context-specific triggers from other components
        window.addEventListener('open-ai-chat', (e) => {
            const context = e.detail || {};
            AoT_AI.openChat(context);
        });

        // [FIX] Bootstrap Modal Compatibility: Remove ai-drawer-active when modal opens
        $(document).on('show.bs.modal', '.modal', function() {
            // Store drawer state before modal opens
            const wasDrawerOpen = isOpen;
            if (wasDrawerOpen) {
                $(this).data('aot-drawer-was-open', true);
            }
            // Always remove the class to prevent modal issues (both desktop and mobile)
            document.body.classList.remove('ai-drawer-active');
            
            // [MOBILE FIX] Force remove any inline padding styles
            document.body.style.paddingRight = '';
        });

        // [FIX] Bootstrap Modal Compatibility: Restore ai-drawer-active when modal closes
        $(document).on('hidden.bs.modal', '.modal', function() {
            // Restore drawer state after modal closes (desktop only)
            const wasDrawerOpen = $(this).data('aot-drawer-was-open');
            if (wasDrawerOpen && isOpen && window.innerWidth > 480) {
                document.body.classList.add('ai-drawer-active');
            }
            $(this).removeData('aot-drawer-was-open');
            
            // [MOBILE FIX] Ensure no lingering padding on mobile
            if (window.innerWidth <= 480) {
                document.body.style.paddingRight = '';
            }
        });
    }

    async function _handleSend(overrideText = null, isAuto = false) {
        const input = document.getElementById('ai-chat-input') || document.getElementById('ai-global-input');
        const sendBtn = document.getElementById('ai-send-btn') || document.querySelector('.ai-send-btn');
        
        // Check if we are currently waiting for a response
        if (sendBtn && sendBtn.classList.contains('thinking')) {
            if (currentAbortController) {
                currentAbortController.abort();
                currentAbortController = null;
            }
            sendBtn.classList.remove('thinking');
            return;
        }

        const text = overrideText || input.value.trim();
        if (!text) return;

        if (!overrideText) {
            input.value = '';
            input.style.height = 'auto'; // Reset height
        }
        _appendMessage(text, 'user');

        // Set busy state
        if (sendBtn) sendBtn.classList.add('thinking');

        // Capture current context if not already set
        if (!pageContext) {
            pageContext = _capturePageContext();
        }

        currentAbortController = new AbortController();

        // Placeholder message that will be replaced on final response
        const thinkingMsg = document.createElement('div');
        thinkingMsg.className = 'ai-msg ai-msg-bot ai-msg-thinking';
        thinkingMsg.innerText = '생각 중...';
        const container = document.getElementById('ai-chat-messages') || document.getElementById('ai-messages-container');
        if (container) { container.appendChild(thinkingMsg); container.scrollTop = container.scrollHeight; }

        try {
            const response = await fetch('/api/v1/ai/portal/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrfToken() },
                body: JSON.stringify({
                    message: text,
                    thread_id: threadId,
                    stream: true,
                    page_context: pageContext || _capturePageContext(),
                    current_dashboard_id: (pageContext ? pageContext.dashboard_id : null) || _capturePageContext().dashboard_id
                }),
                signal: currentAbortController.signal
            });

            if (!response.ok) {
                const errText = await response.text();
                if (thinkingMsg.parentNode) thinkingMsg.remove();
                _appendMessage("Error: HTTP " + response.status, 'bot');
                return;
            }

            // Read SSE stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let finalData = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const evt = JSON.parse(line.slice(6));
                        if (evt.status === 'planning') {
                            thinkingMsg.innerText = '분석 중...';
                        } else if (evt.status === 'plan_ready' && evt.insight) {
                            thinkingMsg.innerText = evt.insight.slice(0, 60) + '...';
                        } else if (evt.status === 'success' || evt.status === 'error') {
                            finalData = evt;
                        }
                    } catch (_) {}
                }
            }

            if (thinkingMsg.parentNode) thinkingMsg.remove();

            if (finalData) {
                if (finalData.status === 'success') {
                    threadId = finalData.thread_id;
                    localStorage.setItem('aot_ai_thread_id', threadId);
                    _appendMessage(finalData.message, 'bot', finalData.actions || [], finalData.history_id);
                } else {
                    _appendMessage("Error: " + (finalData.message || "오류가 발생했습니다."), 'bot');
                }
            } else {
                _appendMessage("응답을 받지 못했습니다. 다시 시도해주세요.", 'bot');
            }

        } catch (err) {
            if (thinkingMsg.parentNode) thinkingMsg.remove();
            if (err.name === 'AbortError') {
                _appendMessage("요청이 취소되었습니다. (사용자 중단)", 'bot');
            } else {
                console.error('[AoT AI] fetch error:', err.name, err.message);
                _appendMessage("시스템 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", 'bot');
            }
        } finally {
            if (sendBtn) sendBtn.classList.remove('thinking');
            currentAbortController = null;
        }
    }

    function _appendMessage(text, type, actions = [], historyId = null, isPrepend = false) {
        const container = document.getElementById('ai-chat-messages') || document.getElementById('ai-messages-container');
        const msg = document.createElement('div');
        msg.className = `ai-msg ai-msg-${type}`;
        msg.innerText = text;

        if (actions && actions.length > 0 && historyId) {
            const actionsContainer = document.createElement('div');
            actionsContainer.className = 'ai-actions-container';
            
            actions.forEach((action, index) => {
                const actionCard = document.createElement('div');
                actionCard.className = 'ai-action-card';
                actionCard.innerHTML = `
                    <div class="ai-action-info">
                        <div class="ai-action-desc">${action.description || action.display_summary || action.tool_name || 'Approve Action'}</div>
                        <button class="ai-action-btn" data-history-id="${historyId}" data-index="${index}">Approve & Execute</button>
                    </div>
                `;
                actionsContainer.appendChild(actionCard);
                
                const btn = actionCard.querySelector('.ai-action-btn');
                btn.addEventListener('click', () => _executeAction(btn, historyId, index));
            });
            msg.appendChild(actionsContainer);
        }

        if (isPrepend) {
            const oldHeight = container.scrollHeight;
            container.prepend(msg);
            // Maintain scroll position after prepend
            container.scrollTop = container.scrollHeight - oldHeight;
        } else {
            container.appendChild(msg);
            container.scrollTop = container.scrollHeight;
        }
    }

    async function _loadHistory(offset) {
        const container = document.getElementById('ai-chat-messages') || document.getElementById('ai-messages-container');
        if (!container || !threadId) return;

        container.classList.add('loading-history');
        try {
            const response = await fetch(`/api/chat/history?thread_id=${threadId}&offset=${offset}&limit=10`);
            const data = await response.json();
            
            if (data.history && data.history.length > 0) {
                // Return history is in chronological order, so we process it backwards to prepend correctly
                // No, the backend reversed it to be chronological for the batch.
                // So we prepend from the end of the batch to the beginning of the batch?
                // Actually, if we prepend in order: 1, 2, 3 -> result is 3, 2, 1 at top.
                // So we should prepend in REVERSE order of the batch.
                const batch = data.history;
                for (let i = batch.length - 1; i >= 0; i--) {
                    const item = batch[i];
                    _appendMessage(item.content, item.message_type === 'user' ? 'user' : 'bot', item.actions, item.id, true);
                }
            }
        } catch (err) {
            console.error("AoT AI: Failed to load history", err);
        } finally {
            container.classList.remove('loading-history');
        }
    }

    async function _executeAction(button, historyId, index) {
        const originalText = button.innerText;
        button.innerText = 'Executing...';
        button.disabled = true;

        try {
            const response = await fetch('/api/v1/ai/portal/chat/action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrfToken() },
                body: JSON.stringify({
                    history_id: historyId,
                    action_index: index
                })
            });

            const data = await response.json();
            if (data.status === 'success') {
                button.innerText = 'Executed';
                const status = document.createElement('div');
                status.className = 'ai-action-status';
                status.innerText = '✓ Success: ' + (data.result || 'Action completed');
                button.parentNode.appendChild(status);
            } else {
                button.innerText = 'Failed';
                button.disabled = false;
                const errorMsg = data.message || data.error || "Unknown error";
                alert("Action failed: " + errorMsg);
            }
        } catch (err) {
            button.innerText = 'Error';
            button.disabled = false;
            console.error("Action execution error:", err);
        }
    }

    function _capturePageContext() {
        const context = {
            url: window.location.href,
            title: document.title,
            timestamp: new Date().toISOString(),
            dashboard_id: null,
            active_modal: null,
            widget_snapshots: []
        };

        // 1. Detect Dashboard ID from URL path or query
        const pathParts = window.location.pathname.split('/');
        if (pathParts.includes('dashboard')) {
            const idx = pathParts.indexOf('dashboard');
            if (pathParts[idx + 1]) context.dashboard_id = pathParts[idx + 1];
        }
        if (!context.dashboard_id) context.dashboard_id = _getQueryParam('dashboard_id');

        // 2. Detect Active Modal (Bootstrap)
        const activeModal = document.querySelector('.modal.show');
        if (activeModal) {
            // Attempt to find device info from the modal content
            const idInput = activeModal.querySelector('input[name="unique_id"], input[name="input_id"], input[name="output_id"], input[name="function_id"]');
            const nameInput = activeModal.querySelector('input.input-device-name, input[name="name"]');
            
            if (idInput) {
                context.active_modal = {
                    targetId: idInput.value,
                    name: nameInput ? nameInput.value : 'Unknown Device',
                    // Inference type from input name/form action
                    targetType: _inferTypeFromModal(activeModal)
                };
            }
        }

        // 3. Widget DOM Snapshot — extract visible data from dashboard widgets
        try {
            const widgets = document.querySelectorAll('.grid-stack-item');
            widgets.forEach(w => {
                const titleEl = w.querySelector('.widget-title, .panel-title, .card-header, [data-widget-title]');
                if (!titleEl) return;
                
                const title = titleEl.textContent.trim();
                if (!title) return;
                
                const snap = { title: title, values: [] };
                
                // Collect displayed values from common widget patterns
                const valueSelectors = [
                    '.widget-value',
                    '.gauge-value',
                    '.measurement-value',
                    '.live-value',
                    '[data-ai-value]',
                    '.current-value'
                ];
                
                valueSelectors.forEach(sel => {
                    w.querySelectorAll(sel).forEach(v => {
                        const txt = v.textContent.trim();
                        if (txt && txt !== '--' && txt !== 'N/A') {
                            // Try to include label if available
                            const label = v.getAttribute('data-ai-label') || 
                                         v.closest('[data-ai-label]')?.getAttribute('data-ai-label') || '';
                            snap.values.push(label ? `${label}: ${txt}` : txt);
                        }
                    });
                });

                // Only include if there's meaningful data
                if (snap.values.length > 0) {
                    context.widget_snapshots.push(snap);
                }
            });
        } catch(e) {
            // Silently fail — DOM scraping is best-effort
        }

        return context;
    }

    function _inferTypeFromModal(modal) {
        const form = modal.querySelector('form');
        if (!form) return 'unknown';
        const action = form.getAttribute('action') || '';
        if (action.includes('input')) return 'input';
        if (action.includes('output')) return 'output';
        if (action.includes('function')) return 'function';
        if (action.includes('pid')) return 'pid';
        return 'device';
    }

    function _getQueryParam(name) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(name);
    }

    // --- Public Methods ---

    return {
        init: _init,
        toggleChat: function() {
            isOpen ? this.closeChat() : this.openChat();
        },
        openChat: function(context = null) {
            const drawer = document.getElementById('ai-chat-drawer') || document.getElementById('aot-ai-drawer');
            const fab = document.getElementById('ai-fab') || document.getElementById('aot-ai-fab');
            if (!drawer) {
                console.error("AoT AI: Drawer element not found");
                return;
            }
            drawer.classList.add('active');
            if (fab) fab.classList.add('hidden');
            isOpen = true;

            // Side-by-side layout for desktop
            if (window.innerWidth > 480) {
                document.body.classList.add('ai-drawer-active');
            }

            if (context) {
                pageContext = { ..._capturePageContext(), ...context };
                const indicator = document.getElementById('ai-context-indicator');
                if (indicator) {
                    indicator.innerHTML = `<div class="ai-context-chip">Context: ${context.name || 'Device'} Setting</div>`;
                }
                
                // Automatically request advice if context is provided
                const adviceMsg = `현재 설정 중인 '${context.name}' (${context.targetType}) 장치에 대해 분석하고 설정을 위한 조언을 해주세요.`;
                _handleSend(adviceMsg, true); // silent send to avoid double user bubble if preferred, but let's make it visible so user knows what's happening
            } else {
                pageContext = null;
                const indicator = document.getElementById('ai-context-indicator');
                if (indicator) indicator.innerHTML = '';
            }
        },
        closeChat: function() {
            const drawer = document.getElementById('ai-chat-drawer') || document.getElementById('aot-ai-drawer');
            const fab = document.getElementById('ai-fab') || document.getElementById('aot-ai-fab');
            if (drawer) drawer.classList.remove('active');
            if (fab) fab.classList.remove('hidden');
            isOpen = false;

            // [FIX] Always remove side-by-side layout class
            document.body.classList.remove('ai-drawer-active');
            
            // [FIX] Force remove any lingering padding from body (both desktop and mobile)
            document.body.style.paddingRight = '';
            
            // [MOBILE FIX] Remove modal-open class if it exists (Bootstrap leftover)
            document.body.classList.remove('modal-open');
        }
    };
})();

// Auto-initialize on DOM load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => AoT_AI.init());
} else {
    AoT_AI.init();
}
