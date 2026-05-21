// State Variables
let activeTaskId = null;
let pollInterval = null;
let currentTaskData = null;

// DOM Elements
const tasksList = document.getElementById("tasks-list");
const refreshBtn = document.getElementById("refresh-tasks");
const fileInput = document.getElementById("video-upload");
const uploadDropzone = document.getElementById("upload-dropzone");

// Main Panel View Sections
const welcomeState = document.getElementById("welcome-state");
const processingState = document.getElementById("processing-state");
const failedState = document.getElementById("failed-state");
const resultsState = document.getElementById("results-state");

// Active Headers
const activeTitle = document.getElementById("active-task-title");
const activeSubtitle = document.getElementById("active-task-subtitle");
const activeStatus = document.getElementById("active-task-status");

// Progress indicators
const processingPercentage = document.getElementById("processing-percentage");
const processingBar = document.getElementById("processing-bar");
const failedReason = document.getElementById("failed-reason");

// Video Panel Elements
const resultsVideo = document.getElementById("results-video");
const metadataGrid = document.getElementById("metadata-grid");

// Objects Catalog
const objectsCount = document.getElementById("objects-count");
const objectsListWrapper = document.getElementById("objects-list-wrapper");

// Timeline container
const timelineContainer = document.getElementById("timeline-container");

// Bottom Elements
const keyframesGallery = document.getElementById("keyframes-gallery");
const jsonBlock = document.getElementById("json-block");
const copyJsonBtn = document.getElementById("copy-json");

// === Initialization ===
document.addEventListener("DOMContentLoaded", () => {
    loadTasksList();
    setupDropzone();
    
    // Refresh button click
    refreshBtn.addEventListener("click", () => {
        loadTasksList();
    });

    // Copy JSON click
    copyJsonBtn.addEventListener("click", () => {
        if (currentTaskData) {
            navigator.clipboard.writeText(JSON.stringify(currentTaskData, null, 2))
                .then(() => {
                    const originalText = copyJsonBtn.innerHTML;
                    copyJsonBtn.innerHTML = `<i class="fa-solid fa-check"></i> Copied!`;
                    setTimeout(() => {
                        copyJsonBtn.innerHTML = originalText;
                    }, 2000);
                });
        }
    });

    // File Input change
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });
});

// === Load sidebar tasks queue ===
function loadTasksList() {
    fetch("/api/tasks")
        .then(res => res.json())
        .then(tasks => {
            if (tasks.length === 0) {
                tasksList.innerHTML = `
                    <div class="empty-state-sidebar">
                        <i class="fa-solid fa-list-check"></i>
                        <p>No video tasks uploaded yet.</p>
                    </div>
                `;
                return;
            }

            tasksList.innerHTML = "";
            tasks.forEach(task => {
                const isSelected = task.id === activeTaskId;
                const taskCard = document.createElement("div");
                taskCard.className = `task-item ${isSelected ? 'active' : ''}`;
                taskCard.setAttribute("data-id", task.id);
                
                // Set appropriate icon
                let iconClass = "fa-solid fa-file-video";
                if (task.status === "PROCESSING") iconClass = "fa-solid fa-circle-notch fa-spin";
                if (task.status === "FAILED") iconClass = "fa-solid fa-circle-xmark";
                if (task.status === "SUCCESS") iconClass = "fa-solid fa-circle-check";
                
                // Format date
                const date = new Date(task.created_at);
                const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                
                taskCard.innerHTML = `
                    <div class="task-icon">
                        <i class="${iconClass}"></i>
                    </div>
                    <div class="task-details">
                        <div class="task-filename" title="${task.filename}">${task.filename}</div>
                        <div class="task-meta">
                            <span class="status-dot ${task.status.toLowerCase()}"></span>
                            <span>${task.status}</span>
                            <span>&bull;</span>
                            <span>${timeStr}</span>
                        </div>
                    </div>
                `;

                taskCard.addEventListener("click", () => {
                    selectTask(task.id);
                });

                tasksList.appendChild(taskCard);
            });
        })
        .catch(err => console.error("Error loading task list:", err));
}

// === Select active task ===
function selectTask(taskId) {
    activeTaskId = taskId;
    
    // Stop any existing pollers
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }

    // Update active highlight classes in sidebar
    document.querySelectorAll(".task-item").forEach(item => {
        if (item.getAttribute("data-id") === taskId) {
            item.classList.add("active");
        } else {
            item.classList.remove("active");
        }
    });

    // Fetch details
    fetchTaskDetails(taskId);
}

// === Fetch detail payload ===
function fetchTaskDetails(taskId) {
    fetch(`/api/tasks/${taskId}`)
        .then(res => res.json())
        .then(task => {
            currentTaskData = task;
            
            // Update Headers
            activeTitle.innerText = task.filename;
            activeSubtitle.innerText = `ID: ${task.id}`;
            activeStatus.innerText = task.status;
            activeStatus.className = `badge ${
                task.status === 'SUCCESS' ? 'badge-green' : 
                task.status === 'FAILED' ? 'badge-orange' : 'badge-indigo'
            }`;
            activeStatus.style.display = "inline-block";

            // Switch to correct view state panel
            switchPanelState(task.status.toLowerCase());

            if (task.status === "PENDING" || task.status === "PROCESSING") {
                // Update loaders
                processingPercentage.innerText = `${task.progress}%`;
                processingBar.style.width = `${task.progress}%`;
                
                // Start background status poller
                pollInterval = setInterval(() => {
                    pollTaskProgress(taskId);
                }, 2000);
            } else if (task.status === "SUCCESS") {
                renderVisualizer(task);
            } else if (task.status === "FAILED") {
                failedReason.innerText = task.error_message || "An unexpected processing error occurred.";
            }
        })
        .catch(err => {
            console.error("Error fetching task details:", err);
            switchPanelState("failed");
            failedReason.innerText = `Network connection error: ${err.message}`;
        });
}

// === Poll active processing progress ===
function pollTaskProgress(taskId) {
    fetch(`/api/tasks/${taskId}`)
        .then(res => res.json())
        .then(task => {
            // Safety break if user selected another task during polling
            if (activeTaskId !== taskId) return;

            processingPercentage.innerText = `${task.progress}%`;
            processingBar.style.width = `${task.progress}%`;
            
            if (task.status !== "PROCESSING" && task.status !== "PENDING") {
                clearInterval(pollInterval);
                pollInterval = null;
                // Reload list to update sidebar statuses
                loadTasksList();
                // Fetch completed detail
                fetchTaskDetails(taskId);
            }
        })
        .catch(err => {
            console.error("Error during polling:", err);
            clearInterval(pollInterval);
        });
}

// === Switch panel view helper ===
function switchPanelState(state) {
    // Hide all
    welcomeState.classList.remove("active");
    processingState.classList.remove("active");
    failedState.classList.remove("active");
    resultsState.classList.remove("active");

    // Show correct
    if (state === "welcome") welcomeState.classList.add("active");
    else if (state === "pending" || state === "processing") processingState.classList.add("active");
    else if (state === "failed") failedState.classList.add("active");
    else if (state === "success") resultsState.classList.add("active");
}

// === Setup Drag-and-drop listeners ===
function setupDropzone() {
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadDropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            uploadDropzone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        uploadDropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            uploadDropzone.classList.remove('dragover');
        }, false);
    });

    uploadDropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });
}

// === Handle direct upload posting ===
function handleFileUpload(file) {
    // Show quick visual processing state immediately
    switchPanelState("pending");
    processingPercentage.innerText = "0%";
    processingBar.style.width = "0%";
    activeTitle.innerText = file.name;
    activeSubtitle.innerText = "Initializing upload...";
    activeStatus.innerText = "UPLOADING";
    activeStatus.style.display = "inline-block";

    const formData = new FormData();
    formData.append("file", file);

    fetch("/api/tasks", {
        method: "POST",
        body: formData
    })
    .then(res => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || "Upload error") });
        return res.json();
    })
    .then(task => {
        // Refresh queue
        loadTasksList();
        // Target uploaded task
        selectTask(task.id);
    })
    .catch(err => {
        console.error("Upload failed:", err);
        switchPanelState("failed");
        failedReason.innerText = `Failed to process upload: ${err.message}`;
    });
}

// === Render complete results dashboard ===
function renderVisualizer(task) {
    const meta = task.videoMetadata;
    const objects = task.objectsDetected || [];
    const keyframes = task.keyFrames || [];

    // 1. Set Video Player Src
    // Standard format safe-naming maps to tasks table filename mapping
    const fileExtension = task.filename.split('.').pop();
    resultsVideo.src = `/static/uploads/${task.id}.${fileExtension}`;
    resultsVideo.load();

    // 2. Render Metadata Cards
    metadataGrid.innerHTML = `
        <div class="meta-field">
            <span class="meta-label">Duration</span>
            <span class="meta-val">${meta.duration}s</span>
        </div>
        <div class="meta-field">
            <span class="meta-label">Resolution</span>
            <span class="meta-val">${meta.resolution}</span>
        </div>
        <div class="meta-field">
            <span class="meta-label">Framerate</span>
            <span class="meta-val">${meta.fps} fps</span>
        </div>
        <div class="meta-field">
            <span class="meta-label">Total Frames</span>
            <span class="meta-val">${meta.total_frames}</span>
        </div>
    `;

    // 3. Render Object Catalogue List
    objectsCount.innerText = `${objects.length} Detected`;
    
    if (objects.length === 0) {
        objectsListWrapper.innerHTML = `
            <div class="empty-state-sidebar" style="height:100%;">
                <i class="fa-solid fa-box-open"></i>
                <p>No interactive objects tracked.</p>
            </div>
        `;
    } else {
        objectsListWrapper.innerHTML = "";
        objects.forEach(obj => {
            const card = document.createElement("div");
            card.className = "object-card";
            card.setAttribute("data-obj-id", obj.object_id);
            
            // Calculate active frames lifetime
            const firstFrame = obj.motion_history[0].frame_range[0];
            const lastHistory = obj.motion_history[obj.motion_history.length - 1];
            const lastFrame = lastHistory.frame_range[1];
            const durationFrames = lastFrame - firstFrame;
            const durationSec = (durationFrames / meta.fps).toFixed(1);
            
            // Count number of interactions
            const interactionCount = obj.interactions ? obj.interactions.length : 0;
            
            card.innerHTML = `
                <div class="object-card-header">
                    <span class="obj-title">${obj.class} #${obj.object_id}</span>
                    <span class="obj-badge">${obj.motion_history.some(h => h.state === 'moving') ? 'moving' : 'static'}</span>
                </div>
                <div class="object-card-metrics">
                    <span class="metric-item"><i class="fa-solid fa-eye"></i> ${durationSec}s</span>
                    <span class="metric-item"><i class="fa-solid fa-child-reaching"></i> ${interactionCount} int.</span>
                </div>
            `;
            
            card.addEventListener("click", () => {
                highlightObject(obj.object_id);
            });
            
            objectsListWrapper.appendChild(card);
        });
    }

    // 4. Render Interactive Gantt Horizontal Timelines
    renderInteractiveTimeline(objects, meta.total_frames, meta.fps);

    // 5. Render Keyframes Gallery
    if (keyframes.length === 0) {
        keyframesGallery.innerHTML = `
            <div class="empty-keyframes-gallery">
                <i class="fa-solid fa-camera-rotate"></i>
                <p>No transition keyframes extracted.</p>
            </div>
        `;
    } else {
        keyframesGallery.innerHTML = "";
        keyframes.forEach(kf => {
            const card = document.createElement("div");
            card.className = "keyframe-card";
            
            card.innerHTML = `
                <div class="keyframe-img-box">
                    <img src="${kf.image_path}" alt="Keyframe Frame ${kf.frame_number}">
                    <span class="keyframe-timestamp">${kf.timestamp}s</span>
                </div>
                <div class="keyframe-desc">
                    <div class="keyframe-reason">${kf.reason}</div>
                    <div class="keyframe-meta">Frame ${kf.frame_number}</div>
                </div>
            `;
            
            // Click to jump video player to frame
            card.addEventListener("click", () => {
                resultsVideo.currentTime = kf.timestamp;
                resultsVideo.play();
            });
            
            keyframesGallery.appendChild(card);
        });
    }

    // 6. Output JSON payload into inspector code block
    jsonBlock.innerText = JSON.stringify(task, null, 2);
}

// === Highlight visualizer elements on card select ===
function highlightObject(objectId) {
    // Highlight list card
    document.querySelectorAll(".object-card").forEach(c => {
        if (c.getAttribute("data-obj-id") == objectId) {
            c.classList.add("highlighted");
            c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            c.classList.remove("highlighted");
        }
    });

    // Highlight timeline row
    document.querySelectorAll(".timeline-row").forEach(row => {
        if (row.getAttribute("data-row-id") == objectId) {
            row.style.background = "rgba(124, 77, 255, 0.05)";
            row.style.borderRadius = "8px";
            row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            row.style.background = "none";
        }
    });
}

// === Build interactive Gantt tracks ===
function renderInteractiveTimeline(objects, totalFrames, fps) {
    if (objects.length === 0) {
        timelineContainer.innerHTML = `
            <div class="empty-state-sidebar" style="height:120px;">
                <i class="fa-solid fa-chart-line"></i>
                <p>No temporal events to map.</p>
            </div>
        `;
        return;
    }

    timelineContainer.innerHTML = "";
    
    objects.forEach(obj => {
        const row = document.createElement("div");
        row.className = "timeline-row";
        row.setAttribute("data-row-id", obj.object_id);
        
        const label = document.createElement("div");
        label.className = "timeline-row-label";
        label.innerText = `${obj.class} #${obj.object_id}`;
        
        const trackWrapper = document.createElement("div");
        trackWrapper.className = "timeline-track-wrapper";
        
        // 1. Draw Motion History Segments
        obj.motion_history.forEach(segment => {
            const startFrame = segment.frame_range[0];
            const endFrame = segment.frame_range[1];
            
            const leftPct = (startFrame / totalFrames) * 100;
            const widthPct = ((endFrame - startFrame) / totalFrames) * 100;
            
            const segmentDiv = document.createElement("div");
            segmentDiv.className = `timeline-segment ${segment.state.toLowerCase()}`;
            segmentDiv.style.left = `${leftPct}%`;
            segmentDiv.style.width = `${widthPct}%`;
            
            // Tooltip title
            segmentDiv.title = `State: ${segment.state}\nFrames: ${startFrame} - ${endFrame}\nTime: ${(startFrame/fps).toFixed(2)}s - ${(endFrame/fps).toFixed(2)}s`;
            
            // Jump player on click
            segmentDiv.addEventListener("click", (e) => {
                e.stopPropagation();
                resultsVideo.currentTime = startFrame / fps;
                resultsVideo.play();
                highlightObject(obj.object_id);
            });
            
            trackWrapper.appendChild(segmentDiv);
        });

        // 2. Draw Interaction Overlay Segments (thinner amber overlays)
        if (obj.interactions) {
            obj.interactions.forEach(inter => {
                const leftPct = (inter.frame_start / totalFrames) * 100;
                const widthPct = ((inter.frame_end - inter.frame_start) / totalFrames) * 100;
                
                const interDiv = document.createElement("div");
                interDiv.className = "timeline-segment interaction";
                interDiv.style.left = `${leftPct}%`;
                interDiv.style.width = `${widthPct}%`;
                
                interDiv.title = `Interacted by Person #${inter.interacted_by_person}\nFrames: ${inter.frame_start} - ${inter.frame_end}\nTime: ${(inter.frame_start/fps).toFixed(2)}s - ${(inter.frame_end/fps).toFixed(2)}s`;
                
                interDiv.addEventListener("click", (e) => {
                    e.stopPropagation();
                    resultsVideo.currentTime = inter.frame_start / fps;
                    resultsVideo.play();
                    highlightObject(obj.object_id);
                });
                
                trackWrapper.appendChild(interDiv);
            });
        }
        
        row.appendChild(label);
        row.appendChild(trackWrapper);
        timelineContainer.appendChild(row);
    });
}
