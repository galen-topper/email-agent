let currentFilter = null;
let allEmails = [];
let currentPage = 0;
let pageSize = 20;
let totalEmails = 0;
let isSpamView = false;
let backgroundCheckInterval = null;

// Initialize
loadStats();
loadInbox();
checkBackgroundProcessing();

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
        const needsReply = email.needs_reply || false;  // Use computed needs_reply from backend
        const isRead = email.is_read || false;
        const isReplied = email.replied_at !== null;
        const timeAgo = formatTimeAgo(email.received_at);
        const unreadClass = isRead ? '' : 'unread';
        
        return `
            <div class="email-item ${unreadClass}" onclick="viewEmail(${email.id})">
                <div class="priority-indicator ${priority}"></div>
                <div class="email-header">
                    <div class="email-from">
                        ${!isRead ? '<span class="unread-dot">●</span> ' : ''}
                        ${isReplied ? '<span class="replied-badge">↩</span> ' : ''}
                        ${escapeHtml(email.from)}
                    </div>
                    <div class="email-time">${timeAgo}</div>
                </div>
                <div class="email-subject">${escapeHtml(email.subject)}</div>
                <div class="email-snippet">${escapeHtml(email.snippet)}</div>
                ${email.classification ? `
                    <div class="email-badges">
                        <span class="badge badge-${priority}">${priority}</span>
                        ${isSpam ? '<span class="badge badge-spam">spam</span>' : ''}
                        ${needsReply ? '<span class="badge badge-needs-reply">needs reply</span>' : ''}
                    </div>
                ` : ''}
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
        
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.onclick = (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        };
        
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <div class="modal-title">${escapeHtml(email.subject)}</div>
                    <button class="modal-close" onclick="document.body.removeChild(this.closest('.modal-overlay'))">✕</button>
                </div>
                <div class="modal-body">
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
                    
                    <div class="section">
                        <div class="section-title">Actions</div>
                        <div class="email-actions-grid">
                            <button class="btn btn-primary" onclick='showComposeModal(${JSON.stringify(email).replace(/'/g, "&apos;")}, false)'>
                                Reply
                            </button>
                            <button class="btn" onclick='showComposeModal(${JSON.stringify(email).replace(/'/g, "&apos;")}, true)'>
                                Forward
                            </button>
                            <button class="btn" onclick="archiveEmail(${email.id})">
                                Archive
                            </button>
                            <button class="btn" onclick="deleteEmail(${email.id})">
                                Delete
                            </button>
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
                                            <button class="btn btn-primary" onclick="approveDraft(${draft.id})">
                                                Send Reply
                                            </button>
                                            <button class="btn">Edit</button>
                                        </div>
                                    </div>
                                `).join('')}
                            ` : `
                                <div class="no-drafts">
                                    <p>No draft replies generated yet.</p>
                                    <button class="btn btn-primary" onclick="generateDrafts(${email.id})">
                                        Generate Draft Replies
                                    </button>
                                </div>
                            `}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
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
        
        if (data.fetched === 0 && data.processed === 0) {
            // Check for configuration issues
            const errorMsg = data.error || 'No new emails found';
            showNotification('info', `No new emails: ${errorMsg}`);
        } else {
            if (data.background_processing) {
                showNotification('success', `Syncing ${data.fetched} emails in background...`);
                // Start checking for background completion
                startBackgroundPolling();
            } else {
                showNotification('success', `Synced ${data.fetched} emails successfully`);
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
            if (status.is_processing) {
                console.log(`Background processing: ${status.processed}/${status.total} emails`);
                showBackgroundStatus(status);
                startBackgroundPolling();
            }
        }
    } catch (error) {
        console.log('Background status check failed (may not be authenticated yet)');
    }
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
        document.body.appendChild(indicator);
    }
    
    const percent = Math.round((status.processed / status.total) * 100);
    
    // Compact view (always visible) - circular progress ring
    indicator.innerHTML = `
        <svg class="progress-ring" width="32" height="32">
            <circle class="progress-ring-circle-bg" cx="16" cy="16" r="14"></circle>
            <circle class="progress-ring-circle" cx="16" cy="16" r="14" 
                    style="stroke-dashoffset: ${88 - (88 * percent) / 100}"></circle>
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
        // Update with current status
        checkBackgroundProcessing().then(() => {
            // Status will be updated by the check
        });
    }
}

function updateBackgroundDetails(status) {
    const details = document.getElementById('backgroundDetails');
    if (!details) return;
    
    const percent = Math.round((status.processed / status.total) * 100);
    const remaining = status.total - status.processed;
    const estimatedTime = Math.round(remaining * 2 / 60); // ~2 sec per email, convert to minutes
    
    details.innerHTML = `
        <div class="details-header">
            <div class="details-title">Background Processing</div>
            <button class="details-close" onclick="toggleBackgroundDetails()">×</button>
        </div>
        <div class="details-content">
            <div class="details-stat">
                <div class="details-label">Progress</div>
                <div class="details-value">${status.processed} / ${status.total} emails</div>
            </div>
            <div class="details-progress-bar">
                <div class="details-progress-fill" style="width: ${percent}%"></div>
            </div>
            <div class="details-percent">${percent}%</div>
            <div class="details-stat">
                <div class="details-label">Remaining</div>
                <div class="details-value">${remaining} emails (~${estimatedTime} min)</div>
            </div>
            <div class="details-info">
                Your inbox is being processed in the background. New emails will appear automatically as they're ready.
            </div>
            <button class="btn" onclick="cancelBackgroundSync()" style="margin-top: 16px; width: 100%;">
                Cancel Sync
            </button>
        </div>
    `;
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
    
    if (indicator) {
        indicator.style.opacity = '0';
        setTimeout(() => indicator.remove(), 300);
    }
    
    if (details) {
        details.classList.remove('visible');
        setTimeout(() => details.remove(), 300);
    }
}

// Current draft state
let currentDraftId = null;
let draftAutoSaveTimer = null;

// Show compose email modal
async function showComposeModal(replyTo = null, forward = false, draftId = null) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    
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
    
    modal.innerHTML = `
        <div class="modal compose-modal">
            <div class="modal-header">
                <div class="modal-title">${title}<span id="draftStatus" style="margin-left: 12px; font-size: 12px; color: #888;"></span></div>
                <button class="modal-close" onclick="closeDraftModal()">✕</button>
            </div>
            <div class="modal-body">
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
                    <div class="compose-actions">
                        <button type="submit" class="btn btn-primary">Send</button>
                        <button type="button" class="btn" onclick="closeDraftModal()">Cancel</button>
                        ${isReply ? '<button type="button" class="btn" onclick="autoDraftReply(' + replyTo.id + ')">Auto-Draft Reply</button>' : ''}
                    </div>
                </form>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
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
    if (draftAutoSaveTimer) {
        clearTimeout(draftAutoSaveTimer);
        draftAutoSaveTimer = null;
    }
    
    // Close modal
    const modal = document.querySelector('.modal-overlay');
    if (modal) {
        document.body.removeChild(modal);
    }
}

function hasAnyContent() {
    const to = document.getElementById('composeTo')?.value || '';
    const subject = document.getElementById('composeSubject')?.value || '';
    const body = document.getElementById('composeBody')?.value || '';
    return to.trim() || subject.trim() || body.trim();
}

function debounceDraftSave(replyToEmailId, isReply, isForward) {
    // Clear existing timer
    if (draftAutoSaveTimer) {
        clearTimeout(draftAutoSaveTimer);
    }
    
    // Set new timer for 2 seconds
    draftAutoSaveTimer = setTimeout(() => {
        saveDraftNow(replyToEmailId, isReply, isForward);
    }, 2000);
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
                setTimeout(() => {
                    status.textContent = '';
                }, 2000);
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
