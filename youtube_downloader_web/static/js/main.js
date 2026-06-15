const formatSelect = document.getElementById('format');
const qualitySelect = document.getElementById('quality');
const downloadBtn = document.getElementById('downloadBtn');
const urlInput = document.getElementById('url');
const progressSection = document.getElementById('progressSection');
const progressBar = document.getElementById('progressBar');
const statusText = document.getElementById('statusText');
const percentText = document.getElementById('percentText');
const speedText = document.getElementById('speedText');
const sizeText = document.getElementById('sizeText');
const etaText = document.getElementById('etaText');
const actionArea = document.getElementById('actionArea');
const saveFileBtn = document.getElementById('saveFileBtn');

let currentPollInterval = null;

// Populate quality based on format and system FFmpeg capabilities
function updateQualityOptions() {
    const isAudio = formatSelect.value === "Audio Only (MP3)";
    const hasFFmpeg = window.APP_CONFIG.hasFFmpeg;
    
    qualitySelect.innerHTML = '';
    
    let options = [];
    
    if (isAudio) {
        options = [
            { text: "Standard (128kbps)", value: "Standard (128kbps)" },
            { text: "High (192kbps)", value: "High (192kbps)" },
            { text: "Best (320kbps)", value: "Best (320kbps)" }
        ];
    } else {
        if (hasFFmpeg) {
            // Allows splitting and merging formats for ultra HD
            options = [
                { text: "Best Available (4K/8K)", value: "Best Available (4K/8K)" },
                { text: "1440p (2K)", value: "1440p (2K)" },
                { text: "1080p (Full HD)", value: "1080p (Full HD)" },
                { text: "720p (HD)", value: "720p (HD)" },
                { text: "480p (SD)", value: "480p (SD)" },
                { text: "360p (Data Saver)", value: "360p (Data Saver)" }
            ];
        } else {
            // Without FFmpeg, capped at streams with direct audio merged
            options = [
                { text: "720p (HD) [Limit]", value: "720p (HD) [Limit]" },
                { text: "480p (SD)", value: "480p (SD)" },
                { text: "360p (Data Saver)", value: "360p (Data Saver)" }
            ];
        }
    }
    
    options.forEach(opt => {
        const el = document.createElement('option');
        el.value = opt.value;
        el.textContent = opt.text;
        qualitySelect.appendChild(el);
    });
    
    if (isAudio && options.length > 1) {
        qualitySelect.selectedIndex = 1; // Default to High (192)
    } else {
        qualitySelect.selectedIndex = 0; // Default to Best Available
    }
}

// Re-generate dropdown upon format switch
formatSelect.addEventListener('change', updateQualityOptions);
updateQualityOptions(); 

// Utility functions for stats mapping
function formatBytes(bytes) {
    if (bytes === 0 || !bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatTime(seconds) {
    if (!seconds) return '--:--';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
}

// Download Button Click Handler
downloadBtn.addEventListener('click', async () => {
    const url = urlInput.value.trim();
    if (!url) {
        alert("Please enter a valid YouTube URL");
        urlInput.focus();
        return;
    }

    // Prepare Interface For Downloading
    progressSection.classList.remove('hidden');
    actionArea.classList.add('hidden');
    downloadBtn.disabled = true;
    urlInput.disabled = true;
    formatSelect.disabled = true;
    qualitySelect.disabled = true;
    
    statusText.textContent = "Initializing backend task...";
    statusText.className = "status-text";
    percentText.textContent = "0%";
    progressBar.style.width = "0%";
    progressBar.classList.remove('processing-pulse');
    speedText.textContent = "--";
    sizeText.textContent = "--";
    etaText.textContent = "--";
    
    try {
        // Send async request to start the download
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                format: formatSelect.value,
                quality: qualitySelect.value
            })
        });
        
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        
        const downloadId = data.download_id;
        startPolling(downloadId);
        
    } catch (err) {
        handleError(err.message);
    }
});

// Periodic fetching to visualize progression over UI
function startPolling(downloadId) {
    if (currentPollInterval) clearInterval(currentPollInterval);
    
    currentPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/progress/${downloadId}`);
            if (!res.ok) throw new Error("Failed to fetch progress updates");
            
            const data = await res.json();
            
            if (data.status === 'error') {
                clearInterval(currentPollInterval);
                handleError(data.error);
                return;
            }
            
            if (data.status === 'done') {
                clearInterval(currentPollInterval);
                handleSuccess(downloadId, data);
                return;
            }
            
            if (data.status === 'processing') {
                statusText.textContent = "Processing & Merging Files (Please Wait)...";
                progressBar.classList.add('processing-pulse');
                progressBar.style.width = "100%";
                percentText.textContent = "";
                
                speedText.textContent = "--/s";
                etaText.textContent = "Processing...";
                return;
            }
            
            // Standard downloading case
            if (data.status === 'downloading') {
                statusText.textContent = "Downloading...";
                const pct = (data.percent || 0).toFixed(1);
                percentText.textContent = `${pct}%`;
                progressBar.style.width = `${pct}%`;
                
                speedText.textContent = `${formatBytes(data.speed)}/s`;
                sizeText.textContent = formatBytes(data.size);
                etaText.textContent = formatTime(data.eta);
            }
            
        } catch (err) {
            console.error("Polling blip:", err);
            // Non-fatal, just wait for next iteration
        }
    }, 1000);
}

function handleError(msg) {
    statusText.textContent = `Error: ${msg}`;
    statusText.className = "status-text error";
    resetControls();
    progressBar.classList.remove('processing-pulse');
}

function handleSuccess(downloadId, data) {
    statusText.textContent = "All Done! Ready to Save.";
    progressBar.classList.remove('processing-pulse');
    progressBar.style.width = "100%";
    percentText.textContent = "100%";
    speedText.textContent = "--";
    etaText.textContent = "--";
    saveFileBtn.href = `/api/file/${downloadId}`;
    
    // Inject browser attachment property to filename if requested
    if (data.filename) {
        saveFileBtn.setAttribute('download', data.filename);
    } else {
        saveFileBtn.removeAttribute('download'); 
    }
    
    actionArea.classList.remove('hidden');
    resetControls();
}

function resetControls() {
    downloadBtn.disabled = false;
    urlInput.disabled = false;
    formatSelect.disabled = false;
    qualitySelect.disabled = false;
}
