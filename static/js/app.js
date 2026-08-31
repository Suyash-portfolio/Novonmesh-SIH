document.addEventListener('DOMContentLoaded', function() {
    const now = new Date();
    const dateEl = document.getElementById('current-date');
    if (dateEl) {
        dateEl.textContent = now.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    }

    loadEngineStatus();
    loadAlertCount();

    setInterval(loadAlertCount, 5000);
});

async function loadEngineStatus() {
    try {
        const status = await API.get('/api/system/status');
        const indicator = document.getElementById('engine-indicator');
        const text = indicator?.querySelector('.status-text');
        const dot = indicator?.querySelector('.pulse-dot');

        const allReady = status.database === 'ONLINE';
        if (text) text.textContent = allReady ? 'System Online' : 'Partial';
        if (dot) {
            dot.className = 'pulse-dot ' + (allReady ? 'online' : 'error');
        }

        const feedsEl = document.getElementById('status-feeds');
        if (feedsEl) feedsEl.textContent = `${status.active_jobs || 0} active`;

        const ocrEl = document.getElementById('status-ocr');
        if (ocrEl) ocrEl.textContent = status.ocr === 'READY' ? 'Ready' : status.ocr === 'MISSING_MODEL' ? 'Missing' : 'Error';

        const gpuEl = document.getElementById('status-gpu');
        if (gpuEl) gpuEl.textContent = status.gpu ? 'CUDA' : 'CPU';
    } catch (e) {
        console.warn('Engine status check failed:', e);
    }
}

async function loadAlertCount() {
    try {
        const data = await API.get('/api/alerts/active-count');
        const badge = document.getElementById('alert-count');
        if (badge) badge.textContent = data.count || 0;
    } catch (e) {
        // Silently fail
    }
}
