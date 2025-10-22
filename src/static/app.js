let currentFilter = null;
let allEmails = [];
let currentPage = 0;
let pageSize = 20;
let totalEmails = 0;
let isSpamView = false;
let backgroundCheckInterval = null;
let lastBackgroundStatus = null;

// Auto-sync interval (every 5 minutes)
let autoSyncInterval = null;

// Initialize
loadStats();
loadDailySummary();
loadInbox();

// Check background processing first, then show permanent indicator if idle
checkBackgroundProcessing().then(() => {
    // If no processing is happening, show the permanent gear indicator
    if (!lastBackgroundStatus || !lastBackgroundStatus.is_processing) {
        showPermanentIndicator();
    }
}).catch(() => {
    // On error, show permanent indicator
    showPermanentIndicator();
});

// Start automatic syncing every 5 minutes
startAutoSync();

// Sync when page becomes visible again (user returns to tab)
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        console.log('Page visible again - syncing emails');
        pollEmails();
    }
});

function startAutoSync() {
    // Clear any existing interval
    if (autoSyncInterval) {
        clearInterval(autoSyncInterval);
    }
    
    // Sync every 5 minutes (300000 ms)
    autoSyncInterval = setInterval(() => {
        console.log('Auto-sync: Checking for new emails');
        pollEmails();
    }, 300000); // 5 minutes
    
    console.log('Auto-sync started - checking for new emails every 5 minutes');
}

function stopAutoSync() {
    if (autoSyncInterval) {
        clearInterval(autoSyncInterval);
        autoSyncInterval = null;
        console.log('Auto-sync stopped');
    }
}

async function loadStats() {
    try {
        const response = await fetch('/stats');
        const stats = await response.json();
        document.getElementById('stats').innerHTML = `
            <div class="stat">${stats.total_emails} emails</div>
            <div class="stat">${stats.needs_reply} replies</div>
            <div class="stat">${stats.drafts} drafts</div>
        `;
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

async function loadDailySummary() {
    const container = document.getElementById('dailySummaryContainer');
    const content = document.getElementById('dailySummaryContent');
    
    try {
        // Try to get existing digest first
        let response = await fetch('/api/agent/daily-digest');
        
        if (response.status === 404) {
            // No digest exists, create one
            console.log('No existing digest found, creating new one...');
            response = await fetch('/api/agent/daily-digest', { method: 'POST' });
        }
        
        if (response.status === 401) {
            // Not authenticated, hide summary
            container.style.display = 'none';
            return;
        }
        
        if (!response.ok) {
            throw new Error('Failed to load daily summary');
        }
        
        const data = await response.json();
        const digest = typeof data.digest === 'string' ? JSON.parse(data.digest) : data.digest;
        
        // Show container
        container.style.display = 'block';
        
        // Display the two-section summary
        content.innerHTML = `
            ${digest.recent_24h && digest.recent_24h.count > 0 ? `
                <div class="digest-section">
                    <div class="digest-section-header">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        Last 24 Hours (${digest.recent_24h.count})
                    </div>
                    <div class="digest-text">${escapeHtml(digest.recent_24h.overview)}</div>
                    ${digest.recent_24h.items && digest.recent_24h.items.length > 0 ? `
                        <div class="digest-emails">
                            ${digest.recent_24h.items.slice(0, 5).map(item => `
                                <div class="digest-email" onclick="viewEmail(${item.email_id})">
                                    <span class="digest-email-subject">${escapeHtml(item.subject)}</span>
                                    <span class="digest-email-from">${escapeHtml(item.from)}</span>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            ` : ''}
            
            ${digest.needs_reply && digest.needs_reply.count > 0 ? `
                <div class="digest-section digest-needs-reply">
                    <div class="digest-section-header">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                        Needs Reply (${digest.needs_reply.count})
                    </div>
                    <div class="digest-text">${escapeHtml(digest.needs_reply.overview)}</div>
                    ${digest.needs_reply.items && digest.needs_reply.items.length > 0 ? `
                        <div class="digest-emails">
                            ${digest.needs_reply.items.slice(0, 5).map(item => `
                                <div class="digest-email" onclick="viewEmail(${item.email_id})">
                                    <span class="digest-email-subject">${escapeHtml(item.subject)}</span>
                                    <span class="digest-email-from">${escapeHtml(item.from)}</span>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            ` : ''}
            
            ${(!digest.recent_24h || digest.recent_24h.count === 0) && (!digest.needs_reply || digest.needs_reply.count === 0) ? `
                <div class="digest-empty">
                    <div>All caught up! No new emails or pending replies.</div>
                </div>
            ` : ''}
        `;
        
    } catch (error) {
        console.error('Failed to load daily summary:', error);
        container.style.display = 'none';
    }
}

async function refreshDailySummary() {
    const content = document.getElementById('dailySummaryContent');
    const button = event?.target?.closest('.daily-summary-refresh');
    
    if (button) {
        button.classList.add('spinning');
    }
    
    content.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <div>Regenerating summary...</div>
        </div>
    `;
    
    try {
        // Force create a new digest
        const response = await fetch('/api/agent/daily-digest', { method: 'POST' });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        if (!response.ok) {
            throw new Error('Failed to refresh summary');
        }
        
        const data = await response.json();
        const digest = typeof data.digest === 'string' ? JSON.parse(data.digest) : data.digest;
        
        content.innerHTML = `
            ${digest.recent_24h && digest.recent_24h.count > 0 ? `
                <div class="digest-section">
                    <div class="digest-section-header">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        Last 24 Hours (${digest.recent_24h.count})
                    </div>
                    <div class="digest-text">${escapeHtml(digest.recent_24h.overview)}</div>
                    ${digest.recent_24h.items && digest.recent_24h.items.length > 0 ? `
                        <div class="digest-emails">
                            ${digest.recent_24h.items.slice(0, 5).map(item => `
                                <div class="digest-email" onclick="viewEmail(${item.email_id})">
                                    <span class="digest-email-subject">${escapeHtml(item.subject)}</span>
                                    <span class="digest-email-from">${escapeHtml(item.from)}</span>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            ` : ''}
            
            ${digest.needs_reply && digest.needs_reply.count > 0 ? `
                <div class="digest-section digest-needs-reply">
                    <div class="digest-section-header">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                        Needs Reply (${digest.needs_reply.count})
                    </div>
                    <div class="digest-text">${escapeHtml(digest.needs_reply.overview)}</div>
                    ${digest.needs_reply.items && digest.needs_reply.items.length > 0 ? `
                        <div class="digest-emails">
                            ${digest.needs_reply.items.slice(0, 5).map(item => `
                                <div class="digest-email" onclick="viewEmail(${item.email_id})">
                                    <span class="digest-email-subject">${escapeHtml(item.subject)}</span>
                                    <span class="digest-email-from">${escapeHtml(item.from)}</span>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            ` : ''}
            
            ${(!digest.recent_24h || digest.recent_24h.count === 0) && (!digest.needs_reply || digest.needs_reply.count === 0) ? `
                <div class="digest-empty">
                    <div>All caught up! No new emails or pending replies.</div>
                </div>
            ` : ''}
        `;
        
        showNotification('success', 'Daily summary refreshed!');
        
    } catch (error) {
        console.error('Failed to refresh daily summary:', error);
        content.innerHTML = `<div class="summary-error">Failed to refresh summary. Please try again.</div>`;
        showNotification('error', 'Failed to refresh summary');
    } finally {
        if (button) {
            button.classList.remove('spinning');
        }
    }
}

async function loadInbox(filter = null, page = 0) {
    isSpamView = false;
    currentFilter = filter;
    currentPage = page;
    const offset = page * pageSize;
    const url = filter 
        ? `/api/inbox?filter=${filter}&limit=${pageSize}&offset=${offset}` 
        : `/api/inbox?limit=${pageSize}&offset=${offset}`;
    
    console.log('Loading inbox with filter:', filter, 'page:', page);
    
    try {
        const response = await fetch(url);
        
        // Check if user is not authenticated
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        console.log('Loaded emails:', data.count, 'Total:', data.total);
        allEmails = data.emails;
        totalEmails = data.total;
        displayEmails(allEmails);
        updatePagination(data);
        
        // Show message if filter returned no results
        if (filter && data.count === 0) {
            const filterName = filter.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
            document.getElementById('emailList').innerHTML = `
                <div class="empty-state">
                    <div class="empty-title">No ${filterName} emails</div>
                    <div class="empty-description">Try a different filter or sync to fetch more emails</div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Load inbox error:', error);
        document.getElementById('emailList').innerHTML = `
            <div class="empty-state">
                <div class="empty-title">Failed to load emails</div>
                <div class="empty-description">Please try again later</div>
            </div>
        `;
    }
}

// Load essential tab (agent-selected important emails)
async function loadEssential(element) {
    // Update active nav item
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    element.classList.add('active');
    isSpamView = false;
    currentFilter = 'essential';
    try {
        const response = await fetch(`/api/essential?limit=${pageSize}`);
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        const data = await response.json();
        const emails = data.emails || [];
        totalEmails = emails.length;
        allEmails = emails;
        displayEmails(emails);
        renderPagination(0, 1); // simple single page view for essential
    } catch (error) {
        console.error('Failed to load essential emails:', error);
        showNotification('error', 'Failed to load essential emails');
    }
}

async function loadSpam(element) {
    console.log('Loading spam tab...');
    isSpamView = true;
    currentFilter = null;
    currentPage = 0;
    const offset = 0;
    const url = `/api/spam?limit=${pageSize}&offset=${offset}`;
    
    console.log('Fetching spam from:', url);
    
    // Update active nav item
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    element.classList.add('active');
    
    try {
        const response = await fetch(url);
        console.log('Spam response status:', response.status);
        
        // Check if user is not authenticated
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        console.log('Spam data:', data);
        allEmails = data.emails;
        totalEmails = data.total;
        displayEmails(allEmails);
        updatePagination(data);
    } catch (error) {
        console.error('Error loading spam:', error);
        document.getElementById('emailList').innerHTML = `
            <div class="empty-state">
                <div class="empty-title">Failed to load spam emails</div>
                <div class="empty-description">Please try again later</div>
            </div>
        `;
    }
}

function updatePagination(data) {
    const toolbar = document.querySelector('.toolbar');
    let paginationDiv = document.querySelector('.pagination-controls');
    
    if (!paginationDiv) {
        paginationDiv = document.createElement('div');
        paginationDiv.className = 'pagination-controls';
        toolbar.appendChild(paginationDiv);
    }
    
    const totalPages = Math.ceil(data.total / pageSize);
    const currentPageNum = currentPage + 1;
    
    paginationDiv.innerHTML = `
        <div class="page-size-selector">
            <label>Show:</label>
            <select onchange="changePageSize(this.value)">
                <option value="10" ${pageSize === 10 ? 'selected' : ''}>10</option>
                <option value="20" ${pageSize === 20 ? 'selected' : ''}>20</option>
                <option value="50" ${pageSize === 50 ? 'selected' : ''}>50</option>
                <option value="100" ${pageSize === 100 ? 'selected' : ''}>100</option>
            </select>
        </div>
        <div class="pagination-info">
            ${data.offset + 1}-${data.offset + data.count} of ${data.total}
        </div>
        <div class="pagination-buttons">
            <button class="btn" onclick="previousPage()" ${currentPage === 0 ? 'disabled' : ''}>
                ← Previous
            </button>
            <span class="page-indicator">Page ${currentPageNum} of ${totalPages}</span>
            <button class="btn" onclick="nextPage()" ${!data.has_more ? 'disabled' : ''}>
                Next →
            </button>
        </div>
    `;
}

function changePageSize(newSize) {
    pageSize = parseInt(newSize);
    currentPage = 0;
    if (isSpamView) {
        loadSpamPage(0);
    } else {
        loadInbox(currentFilter, 0);
    }
}

function nextPage() {
    if (isSpamView) {
        loadSpamPage(currentPage + 1);
    } else {
        loadInbox(currentFilter, currentPage + 1);
    }
}

function previousPage() {
    if (currentPage > 0) {
        if (isSpamView) {
            loadSpamPage(currentPage - 1);
        } else {
            loadInbox(currentFilter, currentPage - 1);
        }
    }
}

async function loadSpamPage(page) {
    currentPage = page;
    const offset = page * pageSize;
    const url = `/api/spam?limit=${pageSize}&offset=${offset}`;
    
    try {
        const response = await fetch(url);
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        allEmails = data.emails;
        totalEmails = data.total;
        displayEmails(allEmails);
        updatePagination(data);
    } catch (error) {
        console.error('Failed to load spam page:', error);
    }
}

function displayEmails(emails) {
    const container = document.getElementById('emailList');
    
    if (emails.length === 0) {
        // Check if this is spam view or regular inbox
        if (isSpamView) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-title">No spam emails</div>
                    <div class="empty-description">Great! No spam detected in your inbox</div>
                </div>
            `;
            return;
        }
        
        // Check if this is likely a configuration issue
        checkConfiguration().then(isConfigured => {
            if (!isConfigured) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-title">Email Configuration Required</div>
                        <div class="empty-description">
                            AgentMail needs to be configured with your email credentials to fetch emails.
                        </div>
                        <div class="config-steps">
                            <div class="config-step">
                                <div class="config-step-number">1</div>
                                <div class="config-step-content">
                                    <div class="config-step-title">Configure Gmail</div>
                                    <div class="config-step-desc">Enable IMAP and create an App Password in your Gmail settings</div>
                                </div>
                            </div>
                            <div class="config-step">
                                <div class="config-step-number">2</div>
                                <div class="config-step-content">
                                    <div class="config-step-title">Update .env File</div>
                                    <div class="config-step-desc">Add your Gmail credentials and OpenAI API key to <code>.env</code></div>
                                </div>
                            </div>
                            <div class="config-step">
                                <div class="config-step-number">3</div>
                                <div class="config-step-content">
                                    <div class="config-step-title">Restart & Fetch</div>
                                    <div class="config-step-desc">Restart the server and click "Fetch New" to pull emails</div>
                                </div>
                            </div>
                        </div>
                        <div class="config-help">
                            <strong>Need help?</strong> Check the <a href="https://github.com/yourusername/agentmail#setup" target="_blank">setup guide</a> or README.md
                        </div>
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-title">No emails found</div>
                        <div class="empty-description">Your inbox is empty or no emails match your filter</div>
                        <button class="btn btn-primary" onclick="pollEmails()" style="margin-top: 16px;">
                            Fetch New Emails
                        </button>
                    </div>
                `;
            }
        });
        return;
    }
    
    container.innerHTML = emails.map(email => {
        const priority = email.classification?.priority || 'normal';
        const isSpam = email.classification?.is_spam || false;
        const isSent = email.classification?.is_sent || false;
        const needsReply = email.needs_reply || false;  // Use computed needs_reply from backend
        const isRead = email.is_read || false;
        const isReplied = email.replied_at !== null;
        const timeAgo = formatTimeAgo(email.received_at);
        const unreadClass = isRead ? '' : 'unread';
        
        return `
            <div class="email-item-compact ${unreadClass}" onclick="viewEmail(${email.id})">
                <div class="priority-indicator ${isSent ? 'sent' : priority}"></div>
                <div class="email-compact-content">
                    <div class="email-compact-left">
                        <div class="email-from-compact">
                            ${!isRead ? '<span class="unread-dot">●</span> ' : ''}
                            ${isReplied ? '<span class="replied-badge">↩</span> ' : ''}
                            ${isSent ? '<span class="sent-badge">→</span> ' : ''}
                            ${escapeHtml(email.from)}
                        </div>
                        <div class="email-subject-compact">${escapeHtml(email.subject)}</div>
                    </div>
                    <div class="email-compact-right">
                        <div class="email-time">${timeAgo}</div>
                        ${email.classification ? `
                            <div class="email-badges-compact">
                                ${isSent ? '<span class="badge-mini badge-sent">sent</span>' : ''}
                                ${!isSent && needsReply ? '<span class="badge-mini badge-needs-reply">reply</span>' : ''}
                                ${!isSent && priority === 'high' ? '<span class="badge-mini badge-high">high</span>' : ''}
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function filterEmails(filter, element) {
    // Update active nav item
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    element.classList.add('active');
    
    loadInbox(filter);
}

function searchEmails() {
    const query = document.getElementById('searchInput').value.toLowerCase();
    if (!query) {
        displayEmails(allEmails);
        return;
    }
    
    const filtered = allEmails.filter(email => 
        email.subject.toLowerCase().includes(query) ||
        email.from.toLowerCase().includes(query) ||
        email.snippet.toLowerCase().includes(query)
    );
    displayEmails(filtered);
}

function closeRightPanel() {
    const panel = document.getElementById('rightPanel');
    const container = document.querySelector('.container');
    if (panel) panel.classList.remove('active');
    if (container) container.classList.remove('panel-open');
}

async function viewEmail(emailId) {
    try {
        const response = await fetch(`/api/email/${emailId}`);
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        const data = await response.json();
        const email = data.email;
        const drafts = data.drafts;
        const summary = data.summary;

        // Mark email as read when opened
        if (!email.is_read) {
            markAsRead(emailId);
        }

        // Render into right-side panel and push layout
        const panel = document.getElementById('rightPanel');
        const container = document.querySelector('.container');
        if (container && !container.classList.contains('panel-open')) container.classList.add('panel-open');
        if (panel) panel.classList.add('active');

        panel.innerHTML = `
            <div class="panel-header">
                <div class="panel-title">${escapeHtml(email.subject)}</div>
                <button class="panel-close" onclick="closeRightPanel()">✕</button>
            </div>
            <div class="panel-body">
                ${data.thread_count > 0 ? `
                    <div class="thread-indicator">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                        Part of a thread (${data.thread_count + 1} message${data.thread_count > 0 ? 's' : ''})
                    </div>
                ` : ''}
                <div class="email-detail-header">
                    <div class="email-detail-meta">
                        <div class="meta-row">
                            <span class="meta-label">From:</span>
                            <span class="meta-value">${escapeHtml(email.from)}</span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-label">To:</span>
                            <span class="meta-value">${escapeHtml(email.to)}</span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-label">Date:</span>
                            <span class="meta-value">${new Date(email.received_at).toLocaleString()}</span>
                        </div>
                    </div>
                </div>
                ${summary ? `
                    <div class="section">
                        <div class="section-title">AI Summary</div>
                        <div class="summary-box">${escapeHtml(summary.summary)}</div>
                    </div>
                ` : ''}
                <div class="section">
                    <div class="section-title">Email Content</div>
                    <div class="summary-box">${escapeHtml(email.snippet)}</div>
                </div>
                ${data.thread_emails && data.thread_emails.length > 0 ? `
                    <div class="section">
                        <div class="section-title">Thread Messages (${data.thread_emails.length})</div>
                        <div class="thread-emails">
                            ${data.thread_emails.map(threadEmail => `
                                <div class="thread-email" onclick="viewEmail(${threadEmail.id})">
                                    <div class="thread-email-header">
                                        <span class="thread-email-from">${escapeHtml(threadEmail.from)}</span>
                                        <span class="thread-email-time">${formatTimeAgo(threadEmail.received_at)}</span>
                                    </div>
                                    <div class="thread-email-subject">${escapeHtml(threadEmail.subject)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
                <div class="section">
                    <div class="section-title">Actions</div>
                    <div class="email-actions-grid">
                        <button class="btn btn-primary" onclick='openComposePanel(${JSON.stringify(email).replace(/'/g, "&apos;")}, false)'>Reply</button>
                        <button class="btn" onclick='openComposePanel(${JSON.stringify(email).replace(/'/g, "&apos;")}, true)'>Forward</button>
                        <button class="btn" onclick="archiveEmail(${email.id})">Archive</button>
                        <button class="btn" onclick="deleteEmail(${email.id})">Delete</button>
                    </div>
                </div>
                <div class="section">
                    <div class="section-title">Reply Drafts</div>
                    <div id="drafts-section-${email.id}">
                        ${drafts.length > 0 ? `
                            ${drafts.map((draft, idx) => `
                                <div class="draft">
                                    <div class="draft-text">${escapeHtml(draft.draft_text)}</div>
                                    <div class="draft-actions">
                                        <button class="btn btn-primary" onclick="approveDraft(${draft.id})">Send Reply</button>
                                        <button class="btn">Edit</button>
                                    </div>
                                </div>
                            `).join('')}
                        ` : `
                            <div class="no-drafts">
                                <p>No draft replies generated yet.</p>
                                <button class="btn btn-primary" onclick="generateDrafts(${email.id})">Generate Draft Replies</button>
                            </div>
                        `}
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        alert('Failed to load email details');
    }
}

async function generateDrafts(emailId) {
    const button = event?.target;
    const originalText = button?.innerHTML;
    
    if (button) {
        button.disabled = true;
        button.innerHTML = 'Generating...';
    }
    
    try {
        const response = await fetch(`/api/email/${emailId}/generate-drafts`, { method: 'POST' });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        
        if (response.ok) {
            if (data.status === 'exists') {
                showNotification('info', data.message);
            } else {
                showNotification('success', data.message);
            }
            
            // Refresh the email detail view to show the new drafts
            const modal = document.querySelector('.modal-overlay');
            if (modal) {
                modal.remove();
            }
            viewEmail(emailId);
        } else {
            showNotification('error', `Failed to generate drafts: ${data.detail || 'Unknown error'}`);
            if (button) {
                button.disabled = false;
                button.innerHTML = originalText;
            }
        }
    } catch (error) {
        console.error('Generate drafts error:', error);
        showNotification('error', 'Failed to generate drafts. Please try again.');
        if (button) {
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }
}

async function approveDraft(draftId) {
    if (!confirm('Send this reply?')) return;
    
    try {
        const response = await fetch(`/api/drafts/${draftId}/approve`, { method: 'POST' });
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        if (response.ok) {
            alert('Reply sent successfully!');
            document.querySelector('.modal-overlay')?.remove();
            loadInbox(currentFilter);
            loadStats();
        } else {
            alert('Failed to send reply');
        }
    } catch (error) {
        alert('Failed to send reply');
    }
}

async function checkConfiguration() {
    try {
        // Try to get configuration status from backend
        const response = await fetch('/config-status');
        if (response.ok) {
            const data = await response.json();
            return data.is_configured;
        }
    } catch (error) {
        console.error('Failed to check configuration:', error);
    }
    // If endpoint doesn't exist or fails, check if we have any emails in DB
    // If no emails exist, it's likely not configured
    return false;
}

function reclassifyAllEmails() {
    // Show custom confirmation modal
    showConfirmDialog(
        'Reclassify All Emails',
        'This will reclassify ALL emails with updated aggressive spam detection rules. This may take 1-2 minutes.',
        async () => {
            // User confirmed - proceed with reclassification
            await performReclassification();
        }
    );
}

async function performReclassification() {
    const button = event?.target?.closest('.reclassify-button');
    const statusLabel = document.querySelector('.status-label');
    
    if (button) {
        button.disabled = true;
        button.classList.add('reclassifying');
    }
    
    if (statusLabel) {
        statusLabel.textContent = 'Reclassifying...';
    }
    
    showNotification('info', 'Reclassifying all emails... This may take a few minutes.');
    
    try {
        const response = await fetch('/api/reclassify-all', { method: 'POST' });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showNotification('success', `✅ Reclassified ${data.processed} emails! Many spam/promotional emails should now be filtered out. Refreshing...`);
            
            if (statusLabel) {
                statusLabel.textContent = `✅ Done (${data.processed})`;
                setTimeout(() => {
                    statusLabel.textContent = 'Reclassify';
                }, 3000);
            }
            
            // Refresh the inbox after a brief delay
            setTimeout(() => {
                loadInbox(currentFilter);
                loadStats();
            }, 2000);
        } else {
            showNotification('error', `Reclassification failed: ${data.message || 'Unknown error'}`);
            if (statusLabel) {
                statusLabel.textContent = 'Reclassify';
            }
        }
    } catch (error) {
        console.error('Reclassify error:', error);
        showNotification('error', 'Reclassification failed. Please try again.');
        if (statusLabel) {
            statusLabel.textContent = 'Reclassify';
        }
    } finally {
        if (button) {
            button.disabled = false;
            button.classList.remove('reclassifying');
        }
    }
}

async function pollEmails() {
    const button = event?.target?.closest('.sync-button');
    
    if (button) {
        button.disabled = true;
        button.classList.add('syncing');
    }
    
    // Show notification instead of blocking modal
    showNotification('info', 'Syncing emails in background...');
    
    try {
        const response = await fetch('/api/poll', { method: 'POST' });
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        
        if (data.error) {
            showNotification('error', `Sync error: ${data.error}`);
        } else if (data.fetched === 0 && data.processed === 0) {
            // No new emails
            showNotification('info', data.message || 'No new emails');
        } else {
            // New emails found
            if (data.background_processing) {
                showNotification('success', `Processing ${data.fetched} emails in background...`);
                // Start checking for background completion
                startBackgroundPolling();
            } else {
                const msg = data.message || `Synced ${data.fetched} new email${data.fetched > 1 ? 's' : ''}`;
                showNotification('success', msg);
            }
        }
        
        // Refresh inbox immediately to show any processed emails
        loadInbox(currentFilter);
        loadStats();
    } catch (error) {
        console.error('Poll error:', error);
        showNotification('error', 'Sync failed. Check your email configuration.');
    } finally {
        if (button) {
            button.disabled = false;
            button.classList.remove('syncing');
        }
    }
}

function showLoadingModal(message) {
    const modal = document.createElement('div');
    modal.className = 'loading-modal-overlay';
    modal.id = 'loadingModal';
    modal.innerHTML = `
        <div class="loading-modal">
            <div class="loading-spinner-large"></div>
            <div class="loading-message" id="loadingMessage">${message}</div>
            <div class="loading-progress">
                <div class="loading-progress-bar" id="loadingProgressBar"></div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // Animate progress bar
    let progress = 0;
    const progressBar = document.getElementById('loadingProgressBar');
    const interval = setInterval(() => {
        progress += Math.random() * 15;
        if (progress > 95) progress = 95;
        progressBar.style.width = `${progress}%`;
    }, 500);
    
    // Store interval ID for cleanup
    modal.dataset.intervalId = interval;
}

function updateLoadingModal(message) {
    const messageEl = document.getElementById('loadingMessage');
    if (messageEl) {
        messageEl.textContent = message;
    }
}

function hideLoadingModal() {
    const modal = document.getElementById('loadingModal');
    if (modal) {
        // Clear interval
        const intervalId = modal.dataset.intervalId;
        if (intervalId) {
            clearInterval(parseInt(intervalId));
        }
        
        // Animate progress to 100%
        const progressBar = document.getElementById('loadingProgressBar');
        if (progressBar) {
            progressBar.style.width = '100%';
        }
        
        // Fade out and remove
        setTimeout(() => {
            modal.style.opacity = '0';
            setTimeout(() => modal.remove(), 300);
        }, 200);
    }
}

function showNotification(type, message) {
    // Remove any existing notifications
    const existing = document.querySelector('.notification');
    if (existing) {
        existing.remove();
    }
    
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

function formatTimeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    
    return date.toLocaleDateString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Compose new email
function composeEmail() {
    showComposeModal();
}

// Alias for compatibility
function openComposePanel(email = null, isForward = false) {
    showComposeModal(email, isForward);
}

// Load drafts tab
async function loadDrafts(element) {
    // Update active nav item
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    element.classList.add('active');
    
    try {
        const response = await fetch('/api/drafts');
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        const drafts = data.drafts || [];
        
        if (drafts.length === 0) {
            document.getElementById('emailList').innerHTML = `
                <div class="empty-state">
                    <div class="empty-title">No Drafts</div>
                    <div class="empty-description">Compose an email to create a draft</div>
                </div>
            `;
            return;
        }
        
        // Display drafts
        let html = '';
        drafts.forEach(draft => {
            const updated = new Date(draft.updated_at).toLocaleString();
            html += `
                <div class="email-item" onclick="openDraft(${draft.id})">
                    <div class="email-from">${draft.to}</div>
                    <div class="email-subject">${draft.subject || '(No subject)'}</div>
                    <div class="email-snippet">${draft.body.substring(0, 100)}${draft.body.length > 100 ? '...' : ''}</div>
                    <div class="email-date">${updated}</div>
                </div>
            `;
        });
        
        document.getElementById('emailList').innerHTML = html;
        
    } catch (error) {
        console.error('Failed to load drafts:', error);
        document.getElementById('emailList').innerHTML = `
            <div class="empty-state">
                <div class="empty-title">Failed to load drafts</div>
                <div class="empty-description">Please try again later</div>
            </div>
        `;
    }
}

async function openDraft(draftId) {
    await showComposeModal(null, false, draftId);
}

// Load sent tab
async function loadSent(element) {
    // Update active nav item
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    element.classList.add('active');
    
    // TODO: Implement sent emails loading
    document.getElementById('emailList').innerHTML = `
        <div class="empty-state">
            <div class="empty-title">Sent</div>
            <div class="empty-description">Your sent emails will appear here</div>
        </div>
    `;
}

// Load trash tab
async function loadTrash(element) {
    // Update active nav item
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    element.classList.add('active');
    
    // TODO: Implement trash loading
    document.getElementById('emailList').innerHTML = `
        <div class="empty-state">
            <div class="empty-title">Trash</div>
            <div class="empty-description">Deleted emails will appear here</div>
        </div>
    `;
}

async function checkBackgroundProcessing() {
    try {
        const response = await fetch('/api/background-status');
        if (response.ok) {
            const status = await response.json();
            lastBackgroundStatus = status;
            if (status.is_processing) {
                console.log(`Background processing: ${status.processed}/${status.total} emails`);
                showBackgroundStatus(status);
                startBackgroundPolling();
            }
            return status;
        }
    } catch (error) {
        console.log('Background status check failed (may not be authenticated yet)');
    }
    return null;
}

function startBackgroundPolling() {
    // Clear any existing interval
    if (backgroundCheckInterval) {
        clearInterval(backgroundCheckInterval);
    }
    
    // Check every 5 seconds
    backgroundCheckInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/background-status');
            if (response.ok) {
                const status = await response.json();
                
                if (status.is_processing) {
                    console.log(`Background processing: ${status.processed}/${status.total} emails`);
                    showBackgroundStatus(status);
                    
                    // Refresh inbox periodically to show new processed emails
                    if (status.processed % 10 === 0) {
                        loadInbox(currentFilter, currentPage);
                        loadStats();
                    }
                } else {
                    // Processing complete
                    console.log('Background processing complete!');
                    lastBackgroundStatus = null;
                    hideBackgroundStatus();
                    clearInterval(backgroundCheckInterval);
                    backgroundCheckInterval = null;
                    
                    // Final refresh
                    loadInbox(currentFilter, currentPage);
                    loadStats();
                    showNotification('success', `All ${status.total} emails processed!`);
                }
            }
        } catch (error) {
            console.error('Background polling error:', error);
        }
    }, 5000);
}

function showBackgroundStatus(status) {
    let indicator = document.getElementById('backgroundIndicator');
    
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'backgroundIndicator';
        indicator.className = 'background-indicator';
        indicator.onclick = toggleBackgroundDetails;
        indicator.title = 'Processing emails - Click for details';
        document.body.appendChild(indicator);
    }
    
    lastBackgroundStatus = status;
    const total = Math.max(0, Number(status.total || 0));
    const processed = Math.max(0, Math.min(total, Number(status.processed || 0)));
    const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
    const clamped = Math.max(0, Math.min(100, percent));
    
    // Calculate stroke offset for circular progress
    // Circle circumference = 2 * PI * r = 2 * 3.14159 * 14 = 87.96
    const radius = 14;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (circumference * clamped) / 100;
    
    // Update title to show progress
    indicator.title = `Processing: ${processed}/${total} emails (${clamped}%) - Click for details`;
    
    // Compact view (always visible) - clean circular progress ring with grey background and blue fill
    indicator.innerHTML = `
        <svg class="progress-ring" width="36" height="36" viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="${radius}" fill="none" stroke="#2a2a2a" stroke-width="2.5"></circle>
            <circle cx="18" cy="18" r="${radius}" fill="none" stroke="#3b82f6" stroke-width="2.5" 
                    stroke-dasharray="${circumference}" 
                    stroke-dashoffset="${offset}" 
                    stroke-linecap="round"
                    transform="rotate(-90 18 18)"
                    style="transition: stroke-dashoffset 0.5s ease;"></circle>
        </svg>
    `;
    
    // Detailed view (popup on click)
    let details = document.getElementById('backgroundDetails');
    if (details && details.classList.contains('visible')) {
        updateBackgroundDetails(status);
    }
}

function toggleBackgroundDetails() {
    let details = document.getElementById('backgroundDetails');
    
    if (!details) {
        details = document.createElement('div');
        details.id = 'backgroundDetails';
        details.className = 'background-details';
        document.body.appendChild(details);
    }
    
    if (details.classList.contains('visible')) {
        details.classList.remove('visible');
    } else {
        details.classList.add('visible');
        // If we already have a status, render immediately
        if (lastBackgroundStatus && lastBackgroundStatus.is_processing) {
            updateBackgroundDetails(lastBackgroundStatus);
        } else {
            // Try to fetch status, else show idle
            checkBackgroundProcessing().then(() => {
                if (!(lastBackgroundStatus && lastBackgroundStatus.is_processing)) {
                    showIdleBackgroundDetails();
                }
            }).catch(() => {
                showIdleBackgroundDetails();
            });
        }
        
        // Also show idle state immediately if no processing
        const indicator = document.getElementById('backgroundIndicator');
        if (!indicator) {
            showIdleBackgroundDetails();
        }
    }
}

function showPermanentIndicator() {
    let indicator = document.getElementById('backgroundIndicator');
    
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'backgroundIndicator';
        indicator.className = 'background-indicator';
        indicator.onclick = toggleBackgroundDetails;
        indicator.title = 'All synced - Click to control email processing';
        document.body.appendChild(indicator);
    }
    
    // Show a full blue circle when synced (100% complete)
    const radius = 14;
    const circumference = 2 * Math.PI * radius;
    
    indicator.innerHTML = `
        <svg class="progress-ring" width="36" height="36" viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="${radius}" fill="none" stroke="#2a2a2a" stroke-width="2.5"></circle>
            <circle cx="18" cy="18" r="${radius}" fill="none" stroke="#3b82f6" stroke-width="2.5" 
                    stroke-dasharray="${circumference}" 
                    stroke-dashoffset="0" 
                    stroke-linecap="round"
                    transform="rotate(-90 18 18)"
                    style="transition: stroke-dashoffset 0.5s ease;"></circle>
        </svg>
    `;
}

function showIdleBackgroundDetails() {
    const details = document.getElementById('backgroundDetails');
    if (!details) return;
    
    details.innerHTML = `
        <div class="details-header">
            <div class="details-title">Email Processing</div>
            <button class="details-close" onclick="toggleBackgroundDetails()">×</button>
        </div>
        <div class="details-content">
            <div class="details-info" style="margin-bottom: 16px;">
                No processing currently active
            </div>
            <div class="details-progress-bar" style="margin-bottom: 16px;">
                <div class="details-progress-fill" style="width: 0%"></div>
            </div>
            <div style="display: flex; flex-direction: column; gap: 12px;">
                <button class="btn btn-primary" onclick="startProcessing()" style="width: 100%; font-size: 14px; padding: 12px;">
                    🔄 Sync & Process
                </button>
                <button class="btn btn-secondary" onclick="resetProcessing()" style="width: 100%; font-size: 14px; padding: 12px;">
                    ↻ Reset All
                </button>
            </div>
        </div>
    `;
}

function updateBackgroundDetails(status) {
    const details = document.getElementById('backgroundDetails');
    if (!details) return;
    
    const percent = Math.round((status.processed / status.total) * 100);
    const remaining = status.total - status.processed;
    
    details.innerHTML = `
        <div class="details-header">
            <div class="details-title">Email Processing</div>
            <button class="details-close" onclick="toggleBackgroundDetails()">×</button>
        </div>
        <div class="details-content">
            <div class="details-info" style="margin-bottom: 16px;">
                Processing ${status.processed} / ${status.total} emails (${percent}%)
            </div>
            <div class="details-progress-bar" style="margin-bottom: 16px;">
                <div class="details-progress-fill" style="width: ${percent}%"></div>
            </div>
            <div style="display: flex; flex-direction: column; gap: 12px;">
                <button class="btn btn-primary" onclick="stopProcessing()" style="width: 100%; font-size: 14px; padding: 12px;">
                    ⏸ Cancel Sync
                </button>
                <button class="btn btn-secondary" onclick="resetProcessing()" style="width: 100%; font-size: 14px; padding: 12px;">
                    ↻ Reset All
                </button>
            </div>
        </div>
    `;
}

async function startProcessing() {
    try {
        // Start processing by polling for new emails
        showNotification('info', 'Starting email processing...');
        await pollEmails();
        toggleBackgroundDetails(); // Close the details panel
    } catch (error) {
        console.error('Start processing error:', error);
        showNotification('error', 'Failed to start processing');
    }
}

async function stopProcessing() {
    try {
        const response = await fetch('/api/cancel-sync', { method: 'POST' });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        if (response.ok) {
            showNotification('info', 'Processing stopped');
            stopBackgroundPolling();
            toggleBackgroundDetails(); // Close the details panel
        } else {
            showNotification('error', 'Failed to stop processing');
        }
    } catch (error) {
        console.error('Stop processing error:', error);
        showNotification('error', 'Failed to stop processing');
    }
}

async function resetProcessing() {
    // Show confirmation dialog
    showConfirmDialog(
        'Reset & Restart Processing',
        'This will reclassify all emails and restart processing from scratch. This may take several minutes. Continue?',
        async () => {
            try {
                showNotification('info', 'Resetting and restarting processing...');
                
                // First, reclassify all emails
                await performReclassification();
                
                // Then start processing
                setTimeout(async () => {
                    await pollEmails();
                    toggleBackgroundDetails();
                    showNotification('success', 'Processing restarted successfully');
                }, 2000);
            } catch (error) {
                console.error('Reset processing error:', error);
                showNotification('error', 'Failed to reset processing');
            }
        }
    );
}

async function cancelBackgroundSync() {
    try {
        const response = await fetch('/api/cancel-sync', { method: 'POST' });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        if (response.ok) {
            showNotification('info', 'Background sync cancelled');
            hideBackgroundStatus();
            stopBackgroundPolling();
        } else {
            showNotification('error', 'Failed to cancel sync');
        }
    } catch (error) {
        console.error('Cancel sync error:', error);
        showNotification('error', 'Failed to cancel sync');
    }
}

function stopBackgroundPolling() {
    if (backgroundPollingInterval) {
        clearInterval(backgroundPollingInterval);
        backgroundPollingInterval = null;
    }
}

function hideBackgroundStatus() {
    const indicator = document.getElementById('backgroundIndicator');
    const details = document.getElementById('backgroundDetails');
    
    if (details) {
        details.classList.remove('visible');
        setTimeout(() => details.remove(), 300);
    }

    // Smoothly transition to synced state (full blue circle) instead of removing
    setTimeout(() => {
        showPermanentIndicator();
    }, 100);
}

// Current draft state
let currentDraftId = null;
let draftAutoSaveTimer = null;
let currentAttachments = []; // Store selected attachments

// Show compose email modal
async function showComposeModal(replyTo = null, forward = false, draftId = null) {
    // Remove existing compose panel if any
    const existingOverlay = document.querySelector('.compose-overlay');
    const existingPanel = document.querySelector('.compose-modal');
    if (existingOverlay) existingOverlay.remove();
    if (existingPanel) existingPanel.remove();
    
    // Reset attachments for new compose
    currentAttachments = [];
    
    const isReply = replyTo !== null;
    const title = forward ? 'Forward Email' : (isReply ? 'Reply to Email' : 'Compose Email');
    
    // Load existing draft if draftId provided
    let draftData = null;
    if (draftId) {
        try {
            const response = await fetch(`/api/drafts/${draftId}`);
            if (response.ok) {
                draftData = await response.json();
                currentDraftId = draftId;
            }
        } catch (error) {
            console.error('Failed to load draft:', error);
        }
    }
    
    // Create overlay (semi-transparent background)
    const overlay = document.createElement('div');
    overlay.className = 'compose-overlay';
    overlay.onclick = () => closeDraftModal();
    
    // Create sliding panel
    const panel = document.createElement('div');
    panel.className = 'compose-modal';
    
    // Prevent clicks on panel from closing it
    panel.onclick = (e) => e.stopPropagation();
    
    panel.innerHTML = `
        <div class="compose-header">
            <div class="compose-title">${title}<span id="draftStatus" style="margin-left: 12px; font-size: 12px; color: #888;"></span></div>
            <button class="compose-close" onclick="closeDraftModal()">✕</button>
        </div>
        <div class="compose-body">
            <form id="composeForm" onsubmit="sendEmail(event)">
                <div class="compose-field">
                    <label>To:</label>
                    <input type="text" id="composeTo" name="to" value="${draftData ? draftData.to : (isReply && !forward ? replyTo.from_addr : '')}" required autocomplete="off" />
                </div>
                <div class="compose-field">
                    <label>Cc:</label>
                    <input type="text" id="composeCc" name="cc" value="${draftData ? (draftData.cc || '') : ''}" autocomplete="off" />
                </div>
                <div class="compose-field">
                    <label>Bcc:</label>
                    <input type="text" id="composeBcc" name="bcc" value="${draftData ? (draftData.bcc || '') : ''}" autocomplete="off" />
                </div>
                <div class="compose-field">
                    <label>Subject:</label>
                    <input type="text" id="composeSubject" name="subject" value="${draftData ? draftData.subject : (isReply ? 'Re: ' + replyTo.subject : '')}" required />
                </div>
                <div class="compose-field">
                    <label>Message:</label>
                    <textarea id="composeBody" name="body" rows="15" required>${draftData ? draftData.body : ''}</textarea>
                </div>
                <div class="compose-field">
                    <label>Attachments:</label>
                    <div id="attachmentList" style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 8px;"></div>
                    <input type="file" id="attachmentInput" multiple style="display: none;" onchange="handleAttachmentSelect(event)" />
                    <button type="button" class="btn" onclick="document.getElementById('attachmentInput').click()">
                        📎 Add Attachments
                    </button>
                </div>
                <div class="compose-actions">
                    <button type="submit" class="btn btn-primary">Send</button>
                    <button type="button" class="btn" onclick="closeDraftModal()">Cancel</button>
                    ${isReply ? '<button type="button" class="btn" onclick="autoDraftReply(' + replyTo.id + ')">Auto-Draft Reply</button>' : ''}
                </div>
            </form>
        </div>
    `;
    
    document.body.appendChild(overlay);
    document.body.appendChild(panel);
    
    // Trigger animation after a brief delay
    setTimeout(() => {
        overlay.classList.add('active');
        panel.classList.add('active');
    }, 10);
    
    // Initialize autocomplete for email fields
    initializeAutocomplete('composeTo');
    initializeAutocomplete('composeCc');
    initializeAutocomplete('composeBcc');
    
    // Set up auto-save on input changes
    const fields = ['composeTo', 'composeCc', 'composeBcc', 'composeSubject', 'composeBody'];
    fields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', () => {
                debounceDraftSave(isReply ? replyTo?.id : null, isReply, forward);
            });
        }
    });
}

function closeDraftModal() {
    // Save one final time before closing
    if (currentDraftId || hasAnyContent()) {
        saveDraftNow(null, false, false);
    }
    
    // Clear state
    currentDraftId = null;
    currentAttachments = [];
    if (draftAutoSaveTimer) {
        clearTimeout(draftAutoSaveTimer);
        draftAutoSaveTimer = null;
    }
    
    // Close panel with animation
    const overlay = document.querySelector('.compose-overlay');
    const panel = document.querySelector('.compose-modal');
    
    if (overlay) overlay.classList.remove('active');
    if (panel) panel.classList.remove('active');
    
    // Remove elements after animation completes
    setTimeout(() => {
        if (overlay) overlay.remove();
        if (panel) panel.remove();
    }, 300); // Match transition duration
}

function hasAnyContent() {
    const to = document.getElementById('composeTo')?.value || '';
    const subject = document.getElementById('composeSubject')?.value || '';
    const body = document.getElementById('composeBody')?.value || '';
    return to.trim() || subject.trim() || body.trim();
}

function debounceDraftSave(replyToEmailId, isReply, isForward) {
    // Show "Saving..." indicator immediately
    const status = document.getElementById('draftStatus');
    if (status) {
        status.textContent = 'Saving...';
        status.style.color = '#888';
    }
    
    // Clear existing timer
    if (draftAutoSaveTimer) {
        clearTimeout(draftAutoSaveTimer);
    }
    
    // Set new timer for 1 second (faster auto-save)
    draftAutoSaveTimer = setTimeout(() => {
        saveDraftNow(replyToEmailId, isReply, isForward);
    }, 1000);
}

async function saveDraftNow(replyToEmailId, isReply, isForward) {
    const to = document.getElementById('composeTo')?.value || '';
    const cc = document.getElementById('composeCc')?.value || '';
    const bcc = document.getElementById('composeBcc')?.value || '';
    const subject = document.getElementById('composeSubject')?.value || '';
    const body = document.getElementById('composeBody')?.value || '';
    
    // Don't save completely empty drafts
    if (!to.trim() && !subject.trim() && !body.trim()) {
        return;
    }
    
    const draftData = {
        id: currentDraftId,
        to: to,
        cc: cc,
        bcc: bcc,
        subject: subject,
        body: body,
        reply_to_email_id: replyToEmailId,
        is_reply: isReply,
        is_forward: isForward
    };
    
    try {
        const response = await fetch('/api/drafts/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(draftData)
        });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Update current draft ID if this was a new draft
            if (!currentDraftId && data.draft_id) {
                currentDraftId = data.draft_id;
            }
            
            // Show "Saved" indicator
            const status = document.getElementById('draftStatus');
            if (status) {
                status.textContent = '✓ Saved';
                status.style.color = '#10b981'; // Green
                setTimeout(() => {
                    status.textContent = '';
                }, 3000);
            }
        }
    } catch (error) {
        console.error('Failed to save draft:', error);
    }
}

// Contact autocomplete system
let contactsCache = null;
let autocompleteTimeout = null;

async function initializeAutocomplete(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    
    let selectedIndex = -1;
    let currentDropdown = null;
    
    // Show initial contacts on focus (no typing required)
    input.addEventListener('focus', async (e) => {
        const query = getLastEmail(input.value);
        
        // If field is empty or current email is short, show popular contacts
        if (query.length < 2) {
            try {
                const response = await fetch(`/api/contacts`);
                
                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                
                const data = await response.json();
                showAutocomplete(input, data.contacts);
            } catch (error) {
                console.error('Failed to fetch contacts:', error);
            }
        }
    });
    
    input.addEventListener('input', async (e) => {
        clearTimeout(autocompleteTimeout);
        
        const query = getLastEmail(input.value);
        
        if (query.length < 1) {
            // Show all contacts when empty
            try {
                const response = await fetch(`/api/contacts`);
                
                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                
                const data = await response.json();
                showAutocomplete(input, data.contacts);
            } catch (error) {
                console.error('Failed to fetch contacts:', error);
            }
            return;
        }
        
        autocompleteTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/contacts?query=${encodeURIComponent(query)}`);
                
                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                
                const data = await response.json();
                showAutocomplete(input, data.contacts);
            } catch (error) {
                console.error('Failed to fetch contacts:', error);
            }
        }, 300); // Debounce 300ms
    });
    
    input.addEventListener('keydown', (e) => {
        const dropdown = currentDropdown;
        if (!dropdown) return;
        
        const items = dropdown.querySelectorAll('.autocomplete-item');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
            updateSelection(items, selectedIndex);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, 0);
            updateSelection(items, selectedIndex);
        } else if (e.key === 'Enter' && selectedIndex >= 0) {
            e.preventDefault();
            items[selectedIndex].click();
        } else if (e.key === 'Escape') {
            hideAutocomplete();
        }
    });
    
    input.addEventListener('blur', () => {
        // Longer delay to allow click on dropdown items
        setTimeout(() => hideAutocomplete(), 300);
    });
    
    function showAutocomplete(inputElem, contacts) {
        hideAutocomplete();
        
        if (!contacts || contacts.length === 0) {
            return;
        }
        
        const dropdown = document.createElement('div');
        dropdown.className = 'autocomplete-dropdown';
        dropdown.id = `autocomplete-${inputId}`;
        
        // Prevent blur when clicking dropdown
        dropdown.addEventListener('mousedown', (e) => {
            e.preventDefault();
        });
        
        contacts.forEach((contact, index) => {
            const item = document.createElement('div');
            item.className = 'autocomplete-item';
            item.innerHTML = `
                <div class="autocomplete-name">${escapeHtml(contact.name)}</div>
                <div class="autocomplete-email">${escapeHtml(contact.email)}</div>
            `;
            
            item.addEventListener('click', () => {
                selectContact(inputElem, contact.email);
                hideAutocomplete();
                inputElem.focus();
            });
            
            dropdown.appendChild(item);
        });
        
        inputElem.parentElement.appendChild(dropdown);
        currentDropdown = dropdown;
        selectedIndex = -1;
    }
    
    function hideAutocomplete() {
        const dropdown = document.getElementById(`autocomplete-${inputId}`);
        if (dropdown) {
            dropdown.remove();
        }
        currentDropdown = null;
        selectedIndex = -1;
    }
    
    function updateSelection(items, index) {
        items.forEach((item, i) => {
            if (i === index) {
                item.classList.add('selected');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('selected');
            }
        });
    }
}

function getLastEmail(value) {
    // Get the text after the last comma or semicolon
    const parts = value.split(/[,;]/);
    return parts[parts.length - 1].trim();
}

function selectContact(input, email) {
    const value = input.value;
    const parts = value.split(/[,;]/);
    
    // Replace the last part with the selected email
    parts[parts.length - 1] = email;
    
    // Join back with commas and add space for next entry
    input.value = parts.join(', ') + ', ';
    input.focus();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Mark email as read
async function markAsRead(emailId) {
    try {
        const response = await fetch(`/api/email/${emailId}/mark-read`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_read: true })
        });
        
        if (response.ok) {
            // Refresh inbox to update unread indicator
            loadInbox(currentFilter, currentPage);
        }
    } catch (error) {
        console.error('Failed to mark as read:', error);
    }
}

// Auto-draft reply for an email
async function autoDraftReply(emailId) {
    const bodyTextarea = document.getElementById('composeBody');
    const button = event?.target;
    const originalText = button?.innerHTML;
    
    if (button) {
        button.disabled = true;
        button.innerHTML = 'Generating...';
    }
    
    try {
        const response = await fetch(`/api/email/${emailId}/generate-drafts`, { method: 'POST' });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        const data = await response.json();
        
        if (response.ok) {
            // Fetch the generated drafts
            const emailResponse = await fetch(`/api/email/${emailId}`);
            const emailData = await emailResponse.json();
            
            if (emailData.drafts && emailData.drafts.length > 0) {
                // Use the first draft
                bodyTextarea.value = emailData.drafts[0][1];
                showNotification('success', 'Draft reply generated!');
            }
        } else {
            showNotification('error', `Failed to generate draft: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Auto-draft error:', error);
        showNotification('error', 'Failed to generate draft. Please try again.');
    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }
}

// Send email
async function sendEmail(event) {
    event.preventDefault();
    
    const form = event.target;
    const formData = {
        to: form.to.value,
        cc: form.cc.value || '',
        bcc: form.bcc.value || '',
        subject: form.subject.value,
        body: form.body.value,
        draft_id: currentDraftId  // Include draft ID if exists
    };
    
    try {
        const response = await fetch('/api/send-email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });
        
        if (response.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        if (response.ok) {
            showNotification('success', 'Email sent successfully!');
            
            // Clear draft state
            currentDraftId = null;
            if (draftAutoSaveTimer) {
                clearTimeout(draftAutoSaveTimer);
                draftAutoSaveTimer = null;
            }
            
            document.querySelector('.modal-overlay')?.remove();
            loadInbox(currentFilter);
        } else {
            const data = await response.json();
            showNotification('error', `Failed to send email: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Send email error:', error);
        showNotification('error', 'Failed to send email. Please try again.');
    }
}

// Archive email
async function archiveEmail(emailId) {
    // TODO: Implement archive functionality
    showNotification('info', 'Archive functionality coming soon');
}

// Delete email
async function deleteEmail(emailId) {
    if (!confirm('Move this email to trash?')) return;
    
    // TODO: Implement delete functionality
    showNotification('info', 'Delete functionality coming soon');
    document.querySelector('.modal-overlay')?.remove();
}

// Show custom confirmation dialog
function showConfirmDialog(title, message, onConfirm) {
    // Remove any existing confirm dialogs
    const existing = document.querySelector('.confirm-dialog-overlay');
    if (existing) existing.remove();
    
    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'confirm-dialog-overlay';
    overlay.onclick = () => closeConfirmDialog();
    
    // Create dialog
    const dialog = document.createElement('div');
    dialog.className = 'confirm-dialog';
    dialog.onclick = (e) => e.stopPropagation();
    
    dialog.innerHTML = `
        <div class="confirm-dialog-header">
            <div class="confirm-dialog-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
            </div>
            <div class="confirm-dialog-title">${title}</div>
        </div>
        <div class="confirm-dialog-body">
            ${message}
        </div>
        <div class="confirm-dialog-actions">
            <button class="btn-secondary" onclick="closeConfirmDialog()">Cancel</button>
            <button class="btn-primary" onclick="confirmDialogAction()">Continue</button>
        </div>
    `;
    
    // Append to body
    document.body.appendChild(overlay);
    document.body.appendChild(dialog);
    
    // Store the callback
    window._confirmDialogCallback = onConfirm;
    
    // Trigger animation
    setTimeout(() => {
        overlay.classList.add('active');
        dialog.classList.add('active');
    }, 10);
}

function closeConfirmDialog() {
    const overlay = document.querySelector('.confirm-dialog-overlay');
    const dialog = document.querySelector('.confirm-dialog');
    
    if (overlay) overlay.classList.remove('active');
    if (dialog) dialog.classList.remove('active');
    
    setTimeout(() => {
        if (overlay) overlay.remove();
        if (dialog) dialog.remove();
        delete window._confirmDialogCallback;
    }, 300);
}

function confirmDialogAction() {
    const callback = window._confirmDialogCallback;
    closeConfirmDialog();
    if (callback) {
        callback();
    }
}

// Attachment handling functions
function handleAttachmentSelect(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    
    // Add files to currentAttachments array
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        
        // Check file size (max 25MB)
        if (file.size > 25 * 1024 * 1024) {
            showNotification('error', `File ${file.name} is too large (max 25MB)`);
            continue;
        }
        
        currentAttachments.push({
            file: file,
            name: file.name,
            size: file.size,
            type: file.type || 'application/octet-stream'
        });
    }
    
    // Update attachment list UI
    updateAttachmentList();
    
    // Clear file input for next selection
    event.target.value = '';
}

function updateAttachmentList() {
    const listContainer = document.getElementById('attachmentList');
    if (!listContainer) return;
    
    if (currentAttachments.length === 0) {
        listContainer.innerHTML = '';
        return;
    }
    
    listContainer.innerHTML = currentAttachments.map((att, index) => {
        const sizeMB = (att.size / (1024 * 1024)).toFixed(2);
        const icon = getFileIcon(att.type, att.name);
        const isViewable = att.type.startsWith('image/') || att.type.startsWith('video/') || att.type.startsWith('audio/');
        
        return `
            <div class="attachment-item" style="display: flex; align-items: center; gap: 12px; padding: 8px 12px; background: var(--bg-tertiary); border-radius: 6px; border: 1px solid var(--border);" onclick="${isViewable ? `viewAttachment(currentAttachments[${index}])` : ''}">
                <span style="font-size: 20px;">${icon}</span>
                <div style="flex: 1; min-width: 0;">
                    <div style="font-size: 14px; color: var(--text-primary); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        ${escapeHtml(att.name)}
                        ${isViewable ? '<span style="font-size: 11px; color: var(--accent); margin-left: 8px;">Click to preview</span>' : ''}
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary);">
                        ${sizeMB} MB
                    </div>
                </div>
                <button type="button" class="btn" style="padding: 4px 8px; font-size: 12px;" onclick="event.stopPropagation(); removeAttachment(${index})">
                    ✕
                </button>
            </div>
        `;
    }).join('');
}

function removeAttachment(index) {
    currentAttachments.splice(index, 1);
    updateAttachmentList();
}

function getFileIcon(mimeType, filename) {
    // Get file extension
    const ext = filename.split('.').pop().toLowerCase();
    
    // Check MIME type or extension
    if (mimeType.startsWith('image/') || ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(ext)) {
        return '🖼️';
    } else if (mimeType.startsWith('video/') || ['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(ext)) {
        return '🎥';
    } else if (mimeType.startsWith('audio/') || ['mp3', 'wav', 'ogg', 'flac', 'm4a'].includes(ext)) {
        return '🎵';
    } else if (mimeType.includes('pdf') || ext === 'pdf') {
        return '📄';
    } else if (mimeType.includes('word') || ['doc', 'docx'].includes(ext)) {
        return '📝';
    } else if (mimeType.includes('excel') || mimeType.includes('spreadsheet') || ['xls', 'xlsx', 'csv'].includes(ext)) {
        return '📊';
    } else if (mimeType.includes('presentation') || ['ppt', 'pptx'].includes(ext)) {
        return '📽️';
    } else if (mimeType.includes('zip') || mimeType.includes('compressed') || ['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
        return '📦';
    } else if (mimeType.includes('text/') || ['txt', 'md', 'log'].includes(ext)) {
        return '📃';
    }
    
    return '📎'; // Default attachment icon
}

function viewAttachment(attachment) {
    const mimeType = attachment.type;
    const ext = attachment.name.split('.').pop().toLowerCase();
    
    // Check if it's a viewable media type
    const isImage = mimeType.startsWith('image/') || ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(ext);
    const isVideo = mimeType.startsWith('video/') || ['mp4', 'mov', 'webm'].includes(ext);
    const isAudio = mimeType.startsWith('audio/') || ['mp3', 'wav', 'ogg', 'm4a'].includes(ext);
    
    if (!isImage && !isVideo && !isAudio) {
        showNotification('info', 'This file type cannot be previewed. It will be sent as an attachment.');
        return;
    }
    
    // Create viewer modal
    const viewer = document.createElement('div');
    viewer.className = 'attachment-viewer-modal';
    viewer.onclick = (e) => {
        if (e.target === viewer) {
            closeAttachmentViewer();
        }
    };
    
    const content = document.createElement('div');
    content.className = 'attachment-viewer-content';
    
    // Create file URL from File object
    const fileURL = URL.createObjectURL(attachment.file);
    
    if (isImage) {
        content.innerHTML = `<img src="${fileURL}" alt="${escapeHtml(attachment.name)}" />`;
    } else if (isVideo) {
        content.innerHTML = `<video src="${fileURL}" controls autoplay style="max-width: 100%; max-height: 90vh;"></video>`;
    } else if (isAudio) {
        content.innerHTML = `<audio src="${fileURL}" controls autoplay style="width: 500px; max-width: 90vw;"></audio>`;
    }
    
    const closeBtn = document.createElement('button');
    closeBtn.className = 'attachment-viewer-close';
    closeBtn.innerHTML = '×';
    closeBtn.onclick = closeAttachmentViewer;
    
    viewer.appendChild(content);
    viewer.appendChild(closeBtn);
    document.body.appendChild(viewer);
    
    // Trigger animation
    setTimeout(() => {
        viewer.classList.add('active');
    }, 10);
}

function closeAttachmentViewer() {
    const viewer = document.querySelector('.attachment-viewer-modal');
    if (viewer) {
        viewer.classList.remove('active');
        setTimeout(() => {
            // Clean up object URLs to prevent memory leaks
            const media = viewer.querySelector('img, video, audio');
            if (media && media.src) {
                URL.revokeObjectURL(media.src);
            }
            viewer.remove();
        }, 300);
    }
}
