import cv2
import json
import numpy as np
from pathlib import Path
from sqlalchemy.orm import Session
from datetime import datetime

from app.config import (
    UPLOAD_DIR,
    TASK_DIR,
    VELOCITY_THRESHOLD,
    VELOCITY_WINDOW,
    MOTION_SMOOTHING_LEN,
    POSE_CONF_THRESHOLD,
    DETECTION_CONF_THRESHOLD,
    WRIST_PROXIMITY_THRESHOLD,
    INTERACTION_GAP_BRIDGE,
    DETECTION_MODEL_NAME,
    POSE_MODEL_NAME,
    MIN_TRACK_FRAMES,
    EXCLUDE_CLASSES,
    CUSTOM_CLASSES,
)
from app.models import Task

def compute_euclidean_distance(pt1, pt2):
    """Computes the standard Euclidean distance between two 2D points."""
    return np.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2)

def distance_point_to_box(px, py, box):
    """
    Computes the minimum distance between a point (px, py) and a 
    bounding box [xmin, ymin, xmax, ymax]. Returns 0.0 if the point 
    is inside the box.
    """
    xmin, ymin, xmax, ymax = box
    dx = max(xmin - px, 0, px - xmax)
    dy = max(ymin - py, 0, py - ymax)
    return np.sqrt(dx**2 + dy**2)

def smooth_states(states, window_size=MOTION_SMOOTHING_LEN):
    """
    Applies a temporal majority/smoothing filter to a sequence of 
    binary states (0 = stationary, 1 = moving) to eliminate high-frequency 
    jitter and rapid state-switching.
    """
    n = len(states)
    if n <= window_size:
        return states
        
    smoothed = list(states)
    half_w = window_size // 2
    
    for i in range(n):
        start = max(0, i - half_w)
        end = min(n, i + half_w + 1)
        sub_seq = states[start:end]
        # Set current state to the majority value in its local window
        smoothed[i] = 1 if sum(sub_seq) > len(sub_seq) / 2.0 else 0
        
    return smoothed

def segment_intervals(frames, states):
    """
    Translates a sequence of frames and their states (0=stationary, 1=moving)
    into structured JSON intervals: [{"frame_range": [start, end], "state": "moving"}]
    """
    if not frames:
        return []
        
    intervals = []
    start_idx = 0
    current_state = states[0]
    
    for i in range(1, len(frames)):
        if states[i] != current_state:
            intervals.append({
                "frame_range": [frames[start_idx], frames[i - 1]],
                "state": "moving" if current_state == 1 else "stationary"
            })
            start_idx = i
            current_state = states[i]
            
    # Add final interval
    intervals.append({
        "frame_range": [frames[start_idx], frames[-1]],
        "state": "moving" if current_state == 1 else "stationary"
    })
    
    return intervals

def process_video_pipeline(task_id: str, video_filename: str, db: Session):
    """
    Runs the full end-to-end asynchronous video object detection, 
    tracking, and human interaction extraction pipeline.
    """
    # 1. Update task status in database to PROCESSING
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return
        
    task.status = "PROCESSING"
    task.progress = 5
    db.commit()
    
    video_path = str(UPLOAD_DIR / video_filename)
    task_out_dir = TASK_DIR / task_id
    task_out_dir.mkdir(parents=True, exist_ok=True)
    keyframes_dir = task_out_dir / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Import inside the thread to avoid GIL lock delays during startup
        from ultralytics import YOLO
        
        # 2. Load pre-trained models
        det_model = YOLO(DETECTION_MODEL_NAME)
        if "world" in DETECTION_MODEL_NAME.lower():
            det_model.set_classes(CUSTOM_CLASSES)
        pose_model = YOLO(POSE_MODEL_NAME)
        
        # 3. Read video details using OpenCV
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_filename}")
            
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        video_metadata = {
            "filename": video_filename,
            "resolution": f"{width}x{height}",
            "fps": round(fps, 2),
            "total_frames": total_frames,
            "duration": round(duration, 2)
        }
        
        # Accumulators
        # object_tracks[track_id] = {"class": class_name, "frames": [], "boxes": [], "centers": []}
        object_tracks = {}
        # person_tracks[person_id] = {"frames": [], "left_wrists": [], "right_wrists": []}
        person_tracks = {}
        
        # Store absolute frames as JPEGs if needed
        frame_idx = 0
        
        print(f"Starting processing of {video_filename}: {total_frames} frames.")
        
        # 4. Frame-by-Frame Processing Loop
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Run YOLO Object Detection with tracking
            det_results = det_model.track(
                source=frame, 
                persist=True, 
                conf=DETECTION_CONF_THRESHOLD, 
                verbose=False
            )
            
            # Run YOLO Human Pose tracking
            pose_results = pose_model.track(
                source=frame, 
                persist=True, 
                conf=POSE_CONF_THRESHOLD, 
                verbose=False
            )
            
            # Process Object Detections
            if det_results and len(det_results) > 0 and det_results[0].boxes is not None:
                boxes = det_results[0].boxes
                for box in boxes:
                    # Check if tracked
                    if box.id is not None:
                        track_id = int(box.id[0].item())
                        cls_idx = int(box.cls[0].item())
                        cls_name = det_model.names[cls_idx]
                        
                        # We exclude the "person" class from objects-of-interaction
                        if cls_name == "person":
                            continue
                            
                        xyxy = box.xyxy[0].tolist()
                        cx = (xyxy[0] + xyxy[2]) / 2.0
                        cy = (xyxy[1] + xyxy[3]) / 2.0
                        
                        if track_id not in object_tracks:
                            object_tracks[track_id] = {
                                "class": cls_name,
                                "frames": [],
                                "boxes": [],
                                "centers": []
                            }
                            
                        object_tracks[track_id]["frames"].append(frame_idx)
                        object_tracks[track_id]["boxes"].append(xyxy)
                        object_tracks[track_id]["centers"].append((cx, cy))
                        
            # Process Pose Keypoints (Wrists)
            if pose_results and len(pose_results) > 0 and pose_results[0].keypoints is not None:
                pose_boxes = pose_results[0].boxes
                keypoints = pose_results[0].keypoints
                
                # Check if keypoints contains actual points
                if len(keypoints) > 0:
                    for i in range(len(keypoints)):
                        # Get person track ID
                        if pose_boxes is not None and pose_boxes[i].id is not None:
                            person_id = int(pose_boxes[i].id[0].item())
                        else:
                            person_id = i # Fallback to index if tracking drops
                            
                        kps_xy = keypoints.xy[i].tolist()   # 17 keypoints of shape (17, 2)
                        kps_conf = keypoints.conf[i].tolist() # Confidence scores of shape (17,)
                        
                        # Left wrist is index 9, Right wrist is index 10
                        l_wrist = kps_xy[9]
                        r_wrist = kps_xy[10]
                        l_conf = kps_conf[9]
                        r_conf = kps_conf[10]
                        
                        if person_id not in person_tracks:
                            person_tracks[person_id] = {
                                "frames": [],
                                "left_wrists": [],
                                "right_wrists": []
                            }
                            
                        person_tracks[person_id]["frames"].append(frame_idx)
                        # We save wrist coordinates along with their confidence
                        person_tracks[person_id]["left_wrists"].append((l_wrist[0], l_wrist[1], l_conf))
                        person_tracks[person_id]["right_wrists"].append((r_wrist[0], r_wrist[1], r_conf))
                        
            frame_idx += 1
            
            # Periodic Database Progress Update
            if frame_idx % 10 == 0 or frame_idx == total_frames:
                progress_pct = int(5 + (frame_idx / total_frames) * 75) # Scale from 5% to 80%
                task.progress = min(progress_pct, 80)
                db.commit()
                
        cap.release()
        
        # 5. POST-PROCESSING: Analyze Motion & Interaction Detection
        objects_detected_payload = []
        extracted_keyframes = []
        
        # Prepare list for frame writing during keyframe extraction
        cap = cv2.VideoCapture(video_path)
        
        for obj_id, data in object_tracks.items():
            cls_name = data["class"]
            frames = data["frames"]
            
            # Apply stable noise filtering (ignores fleeting or irrelevant classes)
            if cls_name in EXCLUDE_CLASSES:
                continue
            if len(frames) < MIN_TRACK_FRAMES:
                continue
                
            boxes = data["boxes"]
            centers = data["centers"]
            
            if len(frames) < 2:
                # If seen for only one frame, state is stationary
                motion_history = [{"frame_range": [frames[0], frames[0]], "state": "stationary"}]
                interactions = []
            else:
                # Calculate velocities
                velocities = []
                for j in range(1, len(frames)):
                    dt = frames[j] - frames[j-1]
                    dist = compute_euclidean_distance(centers[j], centers[j-1])
                    v = dist / dt if dt > 0 else 0.0
                    velocities.append(v)
                    
                # To align length, pad velocity array
                if velocities:
                    velocities.insert(0, velocities[0])
                else:
                    velocities = [0.0]
                    
                # Smooth velocities using sliding window average
                smoothed_velocities = []
                w = VELOCITY_WINDOW
                for j in range(len(velocities)):
                    start_w = max(0, j - w + 1)
                    sub_v = velocities[start_w : j + 1]
                    smoothed_velocities.append(sum(sub_v) / len(sub_v))
                    
                # Classify frame-by-frame state (1 = moving, 0 = stationary)
                frame_states = []
                for v in smoothed_velocities:
                    state = 1 if v >= VELOCITY_THRESHOLD else 0
                    frame_states.append(state)
                    
                # Temporal filtering
                filtered_states = smooth_states(frame_states)
                
                # Segment into continuous intervals
                motion_history = segment_intervals(frames, filtered_states)
                
                # Track Keyframe Transitions (Stationary -> Moving)
                for j in range(1, len(frames)):
                    if filtered_states[j] == 1 and filtered_states[j-1] == 0:
                        transition_frame = frames[j]
                        # Capture keyframe
                        extracted_keyframes.append({
                            "frame_number": transition_frame,
                            "timestamp": round(transition_frame / fps, 2),
                            "reason": f"Motion Transition (Obj {obj_id} {cls_name} started moving)",
                            "object_id": obj_id
                        })
                
                # Detect interactions
                # Find which frames have human hand overlapping this object's bounding box
                interaction_frames = {} # person_id -> list of frame indices
                interaction_details = {} # person_id -> {frame_idx: distance}
                
                for idx, f in enumerate(frames):
                    box = boxes[idx]
                    
                    # Search all tracked people in this frame
                    for p_id, p_data in person_tracks.items():
                        if f in p_data["frames"]:
                            p_idx = p_data["frames"].index(f)
                            lw_x, lw_y, lw_conf = p_data["left_wrists"][p_idx]
                            rw_x, rw_y, rw_conf = p_data["right_wrists"][p_idx]
                            
                            min_dist = float('inf')
                            
                            if lw_conf >= POSE_CONF_THRESHOLD:
                                d_lw = distance_point_to_box(lw_x, lw_y, box)
                                min_dist = min(min_dist, d_lw)
                                
                            if rw_conf >= POSE_CONF_THRESHOLD:
                                d_rw = distance_point_to_box(rw_x, rw_y, box)
                                min_dist = min(min_dist, d_rw)
                                
                            if min_dist <= WRIST_PROXIMITY_THRESHOLD:
                                if p_id not in interaction_frames:
                                    interaction_frames[p_id] = []
                                    interaction_details[p_id] = {}
                                    
                                interaction_frames[p_id].append(f)
                                interaction_details[p_id][f] = min_dist
                                
                # Segment interaction frames into contiguous intervals.
                # A gap of <= INTERACTION_GAP_BRIDGE frames between two detected
                # interaction frames is bridged (treated as continuous) to handle
                # brief wrist tracking dropouts (e.g. hand occlusion mid-interaction).
                interactions = []
                for p_id, f_list in interaction_frames.items():
                    if not f_list:
                        continue
                        
                    f_list = sorted(f_list)
                    start_f = f_list[0]
                    prev_f = f_list[0]
                    
                    # Track peak proximity (minimum distance) for keyframe
                    peak_frame = start_f
                    min_dist_seen = interaction_details[p_id][start_f]
                    
                    for f in f_list[1:]:
                        if f - prev_f > INTERACTION_GAP_BRIDGE:
                            # End interval
                            interactions.append({
                                "interacted_by_person": p_id,
                                "frame_start": start_f,
                                "frame_end": prev_f
                            })
                            # Capture peak keyframe for completed interval
                            extracted_keyframes.append({
                                "frame_number": peak_frame,
                                "timestamp": round(peak_frame / fps, 2),
                                "reason": f"Peak Interaction (Person {p_id} with Obj {obj_id} {cls_name})",
                                "object_id": obj_id
                            })
                            # Start new interval
                            start_f = f
                            peak_frame = f
                            min_dist_seen = interaction_details[p_id][f]
                        else:
                            # Update peak proximity
                            curr_dist = interaction_details[p_id][f]
                            if curr_dist < min_dist_seen:
                                min_dist_seen = curr_dist
                                peak_frame = f
                                
                        prev_f = f
                        
                    # Add final interval
                    interactions.append({
                        "interacted_by_person": p_id,
                        "frame_start": start_f,
                        "frame_end": prev_f
                    })
                    extracted_keyframes.append({
                        "frame_number": peak_frame,
                        "timestamp": round(peak_frame / fps, 2),
                        "reason": f"Peak Interaction (Person {p_id} with Obj {obj_id} {cls_name})",
                        "object_id": obj_id
                    })
                    
            objects_detected_payload.append({
                "object_id": obj_id,
                "class": cls_name,
                "motion_history": motion_history,
                "interactions": interactions
            })
            
        # 6. Extract and Save Keyframe JPEGs
        # Filter keyframes to remove duplicates/near duplicates
        final_keyframes_payload = []
        saved_frames = set()
        
        # Sort keyframes by frame number
        extracted_keyframes = sorted(extracted_keyframes, key=lambda x: x["frame_number"])
        
        for kf in extracted_keyframes:
            f_num = kf["frame_number"]
            # Prevent extracting the exact same frame index multiple times
            if f_num in saved_frames:
                continue
                
            saved_frames.add(f_num)
            
            # Read frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_num)
            ret, frame = cap.read()
            if ret:
                img_filename = f"frame_{f_num}.jpg"
                img_path = keyframes_dir / img_filename
                cv2.imwrite(str(img_path), frame)
                
                final_keyframes_payload.append({
                    "frame_number": f_num,
                    "timestamp": kf["timestamp"],
                    "reason": kf["reason"],
                    "image_path": f"/static/tasks/{task_id}/keyframes/{img_filename}"
                })
                
        cap.release()
        
        # 7. Package Payload
        final_payload = {
            "videoMetadata": video_metadata,
            "objectsDetected": objects_detected_payload,
            "keyFrames": final_keyframes_payload
        }
        
        # Save output JSON file in task directory as a workspace deliverable
        json_file_path = task_out_dir / "output.json"
        with open(json_file_path, "w") as f:
            json.dump(final_payload, f, indent=2)
            
        # Update database with results and status SUCCESS
        task.status = "SUCCESS"
        task.progress = 100
        task.metadata_json = json.dumps(final_payload)
        db.commit()
        print(f"Finished pipeline for task {task_id} successfully!")
        
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"Error executing pipeline for task {task_id}: {error_msg}")
        
        task.status = "FAILED"
        task.error_message = str(e)
        db.commit()
