import uuid
import json
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pathlib import Path

from app.config import UPLOAD_DIR, STATIC_DIR, APP_DIR
from app.database import engine, Base, SessionLocal, get_db
from app.models import Task
from app.pipeline import process_video_pipeline

# 1. Initialize DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Object Identification & Interaction Detection Service",
    description="Asynchronous processing service for detecting objects, classifying motion, and identifying human interactions in video feeds.",
    version="1.0.0"
)

# 2. Mount Static Files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
def startup_event():
    """Ensure upload and storage directories are set up at boot."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "tasks").mkdir(parents=True, exist_ok=True)

# 3. HTML Frontend Route
@app.get("/")
def read_index():
    """Serves the web dashboard frontend."""
    index_path = APP_DIR / "templates" / "index.html"
    if not index_path.exists():
        return {"error": "Dashboard template not found. Please verify folder structures."}
    return FileResponse(index_path)

# 4. REST API: Create Task & Upload Video
@app.post("/api/tasks", status_code=202)
def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Accepts video files, creates an asynchronous processing task, 
    schedules it to run in the background, and returns tracking status.
    """
    # Verify file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in [".mp4", ".mov", ".avi", ".mkv"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported video format: '{ext}'. Supported: .mp4, .mov, .avi, .mkv"
        )
        
    # Generate unique Task ID
    task_id = str(uuid.uuid4())
    
    # Sanitize and write uploaded file to uploads folder
    safe_filename = f"{task_id}{ext}"
    dest_path = UPLOAD_DIR / safe_filename
    
    try:
        with open(dest_path, "wb") as f:
            content = file.file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")
        
    # Register the task in PENDING state
    new_task = Task(
        id=task_id,
        filename=file.filename, # Keep original filename for UI display
        status="PENDING",
        progress=0
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    
    # Create thread-safe session specifically for the background processing thread
    background_db = SessionLocal()
    
    # Schedule CV pipeline to run asynchronously in background thread
    background_tasks.add_task(
        process_video_pipeline,
        task_id,
        safe_filename,
        background_db
    )
    
    return new_task.to_dict()

# 5. REST API: List All Tasks
@app.get("/api/tasks")
def list_tasks(db: Session = Depends(get_db)):
    """Lists all task items in the database with their current processing status."""
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return [t.to_dict() for t in tasks]

# 6. REST API: Read Task Status & Payload
@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    """
    Returns the processing status, progress, and errors for a specific task.
    If the task has completed successfully, returns the full compliant 
    JSON schema metadata.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found.")
        
    response_data = task.to_dict()
    
    # If processing completed successfully, inject the full serialized metadata JSON
    if task.status == "SUCCESS" and task.metadata_json:
        try:
            metadata = json.loads(task.metadata_json)
            # Inject compliant fields directly into response
            response_data["videoMetadata"] = metadata.get("videoMetadata")
            response_data["objectsDetected"] = metadata.get("objectsDetected")
            response_data["keyFrames"] = metadata.get("keyFrames")
        except Exception as e:
            response_data["error_message"] = f"Failed to parse completed payload: {str(e)}"
            
    return response_data
