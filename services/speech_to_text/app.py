from flask import Flask, request, jsonify, render_template
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import storage
from werkzeug.utils import secure_filename
import os
import uuid
import json
import subprocess
from pydub.utils import mediainfo 
import concurrent.futures 
import threading
from google.oauth2 import service_account

app = Flask(__name__)
app.config["UPLOAD_EXTENSIONS"] = [".mp3", ".wav", ".flac", ".ogg", ".opus", ".webm", ".mp4", ".m4a"]
app.config["UPLOAD_FOLDER"] = "temp"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


service_account_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

if not service_account_path or not os.path.exists(service_account_path):
    raise RuntimeError(f"Service account file not found: {service_account_path}")

credentials = service_account.Credentials.from_service_account_file(
    service_account_path
)



GCS_BUCKET_NAME = "autoquiz"


MIN_CHUNK_DURATION_SECONDS = 30 * 60 
CHUNK_DURATION_SECONDS = 900 


MAX_CONCURRENT_CHUNK_TRANSCRIPTIONS = 5 

jobs = {} 



def get_audio_duration(file_path):
    if not os.path.exists(file_path):
        print(f"[ERROR] get_audio_duration: File not found at {file_path}")
        return 0.0

    try:
        info = mediainfo(file_path)
        duration = float(info.get('duration', 0.0))
        if duration > 0:
            print(f"[INFO] pydub.mediainfo successfully detected duration for {file_path}: {duration}s")
            return duration
    except Exception as e:
        print(f"[WARNING] pydub.mediainfo failed for {file_path}: {e}. Trying ffprobe...")

   
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        print(f"[DEBUG] Attempting to run ffprobe command: {' '.join(cmd)}") 
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
   
        duration_str = result.stdout.strip()
        if duration_str and duration_str != 'N/A':
            duration = float(duration_str)
            print(f"[INFO] ffprobe successfully detected duration for {file_path}: {duration}s")
            return duration
        else:
            print(f"[WARNING] ffprobe returned '{duration_str}' for duration, treating as 0.0 for {file_path}.")
            print(f"[DEBUG] ffprobe stdout: {result.stdout}")
            print(f"[DEBUG] ffprobe stderr: {result.stderr}")
            return 0.0 

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ffprobe failed for {file_path} (return code {e.returncode}):")
        print(f"[ERROR] ffprobe stdout: {e.stdout}") 
        print(f"[ERROR] ffprobe stderr: {e.stderr}") 
    except FileNotFoundError:
        print("[ERROR] ffprobe command not found. Ensure FFmpeg (which includes ffprobe) is installed and in PATH.")
    except Exception as e:
        print(f"[ERROR] Generic error getting duration with ffprobe for {file_path}: {e}")
    
    return 0.0

def convert_to_flac(input_path, output_path):
    print(f"[CONVERT] Starting conversion of {input_path} to FLAC...")
    try:
        cmd = [
            "ffmpeg", "-i", input_path,
            "-ar", "16000",          
            "-ac", "1",              
            "-c:a", "flac",          
            "-compression_level", "5", 
            output_path,
            "-y"                     
        ]
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        print(f"[CONVERT] Successfully converted to FLAC: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] FFmpeg conversion failed (return code {e.returncode}): {e.stderr}")
        raise Exception(f"Audio conversion failed: {e.stderr}")
    except FileNotFoundError:
        print("[ERROR] FFmpeg command not found. Please ensure FFmpeg is installed and in your system's PATH.")
        raise Exception("FFmpeg not found. Please install it.")
    except Exception as e:
        print(f"[ERROR] Failed to convert audio: {e}")
        raise

def convert_webm_to_mp3(input_path, output_path):
    print(f"[CONVERT] Converting WebM {input_path} to MP3 {output_path}...")
    try:
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vn",                   
            "-acodec", "libmp3lame", 
            "-ar", "16000",          
            "-ac", "1",              
            "-b:a", "32k",           
            output_path,
            "-y"
        ]
        
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        print(f"[CONVERT] Successfully converted WebM to MP3: {output_path}")
        print(f"[DEBUG] FFmpeg stdout for MP3 conversion: {result.stdout}")
        print(f"[DEBUG] FFmpeg stderr for MP3 conversion: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        error_output = e.stderr
        print(f"[ERROR] WebM to MP3 conversion failed (return code {e.returncode}):")
        print(f"[ERROR] FFmpeg stdout: {e.stdout}") 
        print(f"[ERROR] FFmpeg stderr: {e.stderr}")
        if "Unknown encoder 'libmp3lame'" in error_output:
            print("[ERROR] FFmpeg error: MP3 encoder (libmp3lame) not found. This usually means FFmpeg was not compiled with LAME support. On Linux, you might need to install `libavcodec-extra` or similar packages.")
            raise Exception("FFmpeg error: MP3 encoder (libmp3lame) not found. See server logs for details.")
        raise Exception(f"WebM to MP3 conversion failed: {error_output}")
    except FileNotFoundError:
        print("[ERROR] FFmpeg command not found. Please ensure FFmpeg is installed and in your system's PATH.")
        raise Exception("FFmpeg not found. Please install it.")
    except Exception as e:
        print(f"[ERROR] Failed to convert WebM to MP3: {e}")
        raise

def split_audio_into_chunks(input_path, output_dir, base_filename, chunk_duration):
    print(f"[SPLIT] Starting audio splitting for {input_path} into {chunk_duration}s chunks...")
    output_chunk_paths = []
    duration = get_audio_duration(input_path) 
    
    if duration == 0:
        raise Exception("Cannot split audio with zero duration.")

    num_chunks = int(duration // chunk_duration) + (1 if duration % chunk_duration > 0 else 0)

    for i in range(num_chunks):
        start_time = i * chunk_duration
        output_chunk_name = f"{base_filename}_chunk_{i:03d}.flac"
        output_chunk_path = os.path.join(output_dir, output_chunk_name)
        
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-ss", str(start_time),
            "-t", str(chunk_duration),
            "-ar", "16000",         
            "-ac", "1",              
            "-c:a", "flac",         
            "-compression_level", "5", 
            output_chunk_path,
            "-y"                     
        ]
        
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            print(f"[SPLIT] Created chunk {i+1}/{num_chunks}: {output_chunk_path}")
            output_chunk_paths.append(output_chunk_path)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] FFmpeg splitting failed for chunk {i} (return code {e.returncode}): {e.stderr}")
            raise Exception(f"Audio splitting failed for chunk {i}: {e.stderr}")
        except FileNotFoundError:
            print("[ERROR] FFmpeg command not found. Please ensure FFmpeg is installed and in your system's PATH.")
            raise Exception("FFmpeg not found. Please install it.")
        except Exception as e:
            print(f"[ERROR] Failed to split audio chunk {i}: {e}")
            raise

    print(f"[SPLIT] Finished splitting {input_path} into {len(output_chunk_paths)} chunks.")
    return output_chunk_paths

def upload_to_gcs(file_path, blob_name):
    print(f"[UPLOAD] Starting upload of {file_path} to GCS bucket {GCS_BUCKET_NAME} as {blob_name}...")
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(file_path, timeout=1200) 
        print(f"[UPLOAD] Successfully uploaded to GCS: gs://{GCS_BUCKET_NAME}/{blob_name}")
        return f"gs://{GCS_BUCKET_NAME}/{blob_name}"
    except Exception as e:
        print(f"[ERROR] GCS upload failed for {file_path}: {e}")
        raise

def delete_from_gcs(blob_name):
    """
    Deletes a blob from Google Cloud Storage.
    Args:
        blob_name (str): The name of the blob to delete.
    """
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        blob.delete()
        print(f"[CLEANUP] Deleted from GCS: {blob_name}")
    except Exception as e:
        print(f"[CLEANUP WARN] Could not delete GCS blob {blob_name}: {e}")

def transcribe_single_file_async(job_id, original_audio_path):
    flac_path = None
    blob_name = f"{job_id}.flac" 
    try:
        jobs[job_id]["status"] = "converting"
        print(f"[JOB {job_id}] Status: Converting audio to FLAC...")
        flac_path = os.path.join(app.config["UPLOAD_FOLDER"], blob_name)
        convert_to_flac(original_audio_path, flac_path)
        
        jobs[job_id]["status"] = "uploading"
        print(f"[JOB {job_id}] Status: Uploading to GCS...")
        gcs_uri = upload_to_gcs(flac_path, blob_name)
        
        client = speech.SpeechClient()
        
        audio = speech.RecognitionAudio(uri=gcs_uri)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="video", # Or "latest"
            use_enhanced=True,
            enable_word_time_offsets=True,
            enable_speaker_diarization=True,
            diarization_speaker_count=2,
        )

        jobs[job_id]["status"] = "transcribing"
        print(f"[JOB {job_id}] Status: Starting Google Speech-to-Text long-running recognition with model '{config.model}'...")
        operation = client.long_running_recognize(config=config, audio=audio)
        
        
        print(f"[JOB {job_id}] Waiting for transcription result with a timeout of 10800 seconds...")
        response = operation.result(timeout=10800)

        transcript_parts = []
        for result in response.results:
            if result.alternatives:
                transcript_parts.append(result.alternatives[0].transcript)

        transcript = " ".join(transcript_parts)
        print(f"[JOB {job_id}] Transcription successful. Transcript (first 100 chars): {transcript[:100]}...")

        jobs[job_id]["status"] = "done"
        jobs[job_id]["transcript"] = transcript
        print(f"[JOB {job_id}] Completed successfully.")
        
        
        with open("latest_transcript.json", "w", encoding="utf-8") as f:
            json.dump({"transcript": transcript}, f)

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        print(f"[ERROR] Job {job_id} failed: {e}")
    finally:
        if blob_name:
            delete_from_gcs(blob_name)
        if os.path.exists(original_audio_path):
            os.remove(original_audio_path)
            print(f"[CLEANUP] Deleted original local file: {original_audio_path}")
        if flac_path and os.path.exists(flac_path):
            os.remove(flac_path)
            print(f"[CLEANUP] Deleted FLAC local file: {flac_path}")

def transcribe_mic_direct_async(job_id, mp3_audio_path):
    blob_name = f"{job_id}.mp3" 
    gcs_uri = None
    try:
        jobs[job_id]["status"] = "uploading"
        print(f"[JOB {job_id}] Status: Uploading microphone MP3 to GCS...")
        gcs_uri = upload_to_gcs(mp3_audio_path, blob_name)
        
        client = speech.SpeechClient()
        
        audio = speech.RecognitionAudio(uri=gcs_uri)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.MP3, 
            sample_rate_hertz=16000, 
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="video", 
            use_enhanced=True,
            enable_word_time_offsets=True,
            enable_speaker_diarization=True,
            diarization_speaker_count=2,
        )

        jobs[job_id]["status"] = "transcribing"
        print(f"[JOB {job_id}] Status: Starting Google Speech-to-Text recognition for MP3...")
        operation = client.long_running_recognize(config=config, audio=audio)
        
        print(f"[JOB {job_id}] Waiting for MP3 transcription result with a timeout of 10800 seconds...")
        response = operation.result(timeout=10800)

        transcript_parts = []
        for result in response.results:
            if result.alternatives:
                transcript_parts.append(result.alternatives[0].transcript)

        transcript = " ".join(transcript_parts)
        print(f"[JOB {job_id}] MP3 Transcription successful. Transcript (first 100 chars): {transcript[:100]}...")

        jobs[job_id]["status"] = "done"
        jobs[job_id]["transcript"] = transcript
        print(f"[JOB {job_id}] MP3 transcription completed successfully.")
        
        with open("latest_transcript.json", "w", encoding="utf-8") as f:
            json.dump({"transcript": transcript}, f)

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        print(f"[ERROR] Job {job_id} (MP3) failed: {e}")
    finally:
        if gcs_uri:
            delete_from_gcs(blob_name)
        if os.path.exists(mp3_audio_path):
            os.remove(mp3_audio_path)
            print(f"[CLEANUP] Deleted local MP3 file: {mp3_audio_path}")


def transcribe_chunk_async(parent_job_id, chunk_index, chunk_path, chunk_blob_name):
    gcs_uri = None
    try:
        jobs[parent_job_id]["chunks"][chunk_index]["status"] = "uploading_chunk"
        print(f"[JOB {parent_job_id}] Chunk {chunk_index}: Status: Uploading chunk to GCS...")
        gcs_uri = upload_to_gcs(chunk_path, chunk_blob_name)
        
        client = speech.SpeechClient()
        
        audio = speech.RecognitionAudio(uri=gcs_uri)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
            sample_rate_hertz=16000,
            language_code="en-US",
            enable_automatic_punctuation=True,
            model="video", 
            use_enhanced=True,
            enable_word_time_offsets=False, 
            enable_speaker_diarization=False, 
        )

        jobs[parent_job_id]["chunks"][chunk_index]["status"] = "transcribing_chunk"
        print(f"[JOB {parent_job_id}] Chunk {chunk_index}: Status: Starting Google Speech-to-Text recognition...")
        
        operation = client.long_running_recognize(config=config, audio=audio)
        
        
        chunk_timeout = CHUNK_DURATION_SECONDS * 4 
        print(f"[JOB {parent_job_id}] Chunk {chunk_index}: Waiting for transcription result with a timeout of {chunk_timeout} seconds...")
        response = operation.result(timeout=chunk_timeout)

        transcript_parts = []
        for result in response.results:
            if result.alternatives:
                transcript_parts.append(result.alternatives[0].transcript)

        transcript = " ".join(transcript_parts)
        print(f"[JOB {parent_job_id}] Chunk {chunk_index}: Transcription successful. Transcript (first 50 chars): {transcript[:50]}...")

        jobs[parent_job_id]["chunks"][chunk_index]["status"] = "done"
        jobs[parent_job_id]["chunks"][chunk_index]["transcript"] = transcript
        print(f"[JOB {parent_job_id}] Chunk {chunk_index}: Completed successfully.")
        
    except Exception as e:
        jobs[parent_job_id]["chunks"][chunk_index]["status"] = "error"
        jobs[parent_job_id]["chunks"][chunk_index]["error"] = str(e)
        print(f"[ERROR] Job {parent_job_id} Chunk {chunk_index} failed: {e}")
    finally:
        
        if gcs_uri:
            delete_from_gcs(chunk_blob_name)
        if os.path.exists(chunk_path):
            os.remove(chunk_path)
            print(f"[CLEANUP] Deleted local chunk file: {chunk_path}")


def process_full_audio_for_chunking(parent_job_id, original_file_path, duration):
    try:
        jobs[parent_job_id]["status"] = "splitting_audio"
        chunk_paths = split_audio_into_chunks(
            original_file_path,
            app.config["UPLOAD_FOLDER"],
            parent_job_id,
            CHUNK_DURATION_SECONDS
        )

        
        for i, path in enumerate(chunk_paths):
            chunk_id = f"{parent_job_id}_chunk_{i:03d}"
            jobs[parent_job_id]["chunks"][i] = { 
                "index": i,
                "status": "pending",
                "local_path": path,
                "gcs_blob_name": f"{chunk_id}.flac",
                "transcript": None,
                "error": None
            }
        jobs[parent_job_id]["status"] = "processing_chunks"
        print(f"[JOB {parent_job_id}] Status: Initiating transcription for {len(chunk_paths)} chunks.")

        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CHUNK_TRANSCRIPTIONS) as executor:
            future_to_chunk = {
                executor.submit(transcribe_chunk_async, parent_job_id, chunk_info["index"], chunk_info["local_path"], chunk_info["gcs_blob_name"]): chunk_info["index"]
                for chunk_info in jobs[parent_job_id]["chunks"].values()
            }
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_index = future_to_chunk[future]
                try:
                    future.result() 
                except Exception as exc:
                    print(f'[JOB {parent_job_id}] Chunk {chunk_index} generated an exception: {exc}')
                   

    except Exception as e:
        jobs[parent_job_id]["status"] = "error"
        jobs[parent_job_id]["error"] = str(e)
        print(f"[ERROR] Parent job {parent_job_id} failed during splitting or orchestration: {e}")
    finally:
        
        if os.path.exists(original_file_path):
            os.remove(original_file_path)
            print(f"[CLEANUP] Deleted original uploaded file: {original_file_path}")


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/transcribe", methods=["POST"])
def transcribe():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    
    job_id = str(uuid.uuid4())
    
   
    mic_mode_raw = request.form.get("mic_mode")
    print(f"[DEBUG] Received mic_mode: '{mic_mode_raw}' (type: {type(mic_mode_raw)})")
    mic_mode = mic_mode_raw == "true"
    
    if mic_mode:
       
        temp_webm_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{job_id}_temp_mic.webm")
        file.save(temp_webm_path)
        print(f"[API] Saved temporary mic recording (WebM) to: {temp_webm_path}")

        
        mp3_file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{job_id}_mic_recorded.mp3")
        try:
            jobs[job_id] = { 
                "type": "single",
                "status": "converting_mic_audio",
                "estimated_duration_seconds": 0, 
                "transcript": None,
                "error": None
            }
            convert_webm_to_mp3(temp_webm_path, mp3_file_path)
            
           
            if not os.path.exists(mp3_file_path) or os.path.getsize(mp3_file_path) == 0:
                error_msg = f"FFmpeg conversion to MP3 failed or produced an empty file: {mp3_file_path}"
                print(f"[ERROR] {error_msg}")
                raise Exception(error_msg)

            os.remove(temp_webm_path) 
            print(f"[CLEANUP] Deleted temporary webm file: {temp_webm_path}")
        except Exception as e:
            
            if os.path.exists(temp_webm_path): os.remove(temp_webm_path)
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)
            print(f"[ERROR] Failed during microphone audio conversion: {e}")
            return jsonify({"error": f"Failed to convert microphone audio: {e}"}), 500
        
        
        jobs[job_id]["status"] = "processing" 
        print(f"[API] Received microphone transcription request. Job ID: {job_id}. Skipping duration check for direct transcription.")
        threading.Thread(
            target=transcribe_mic_direct_async,
            args=(job_id, mp3_file_path),
            daemon=True
        ).start()

       
        return jsonify({"job_id": job_id, "estimated_duration_minutes": 0})

    else:
        
        ext = os.path.splitext(file.filename)[1].lower() 
        if ext not in app.config["UPLOAD_EXTENSIONS"]:
            return jsonify({"error": f"Unsupported file type: {ext}. Supported types are: {', '.join(app.config['UPLOAD_EXTENSIONS'])}"}), 400
        
        processed_file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{job_id}_original{ext}")
        file.save(processed_file_path)
        print(f"[API] Saved uploaded file to: {processed_file_path}")

        duration = get_audio_duration(processed_file_path)
        if duration == 0.0:
            if os.path.exists(processed_file_path): os.remove(processed_file_path)
            return jsonify({"error": "Could not determine audio duration or audio file is invalid. Ensure FFmpeg (with ffprobe) is installed and the file is not corrupted."}), 400
        
        
        if duration > 8 * 3600:
            if os.path.exists(processed_file_path): os.remove(processed_file_path)
            return jsonify({"error": f"Audio file too long ({duration:.2f} seconds). Maximum supported duration is 8 hours."}), 400

        
        if duration > MIN_CHUNK_DURATION_SECONDS:
            jobs[job_id] = {
                "type": "chunked",
                "status": "splitting_audio",
                "estimated_duration_seconds": duration,
                "chunks": {}
            }
            print(f"[API] Received chunked transcription request. Parent Job ID: {job_id}, Original Duration: {duration:.2f} seconds.")
            threading.Thread(
                target=process_full_audio_for_chunking,
                args=(job_id, processed_file_path, duration),
                daemon=True
            ).start()
        else:
            jobs[job_id] = {
                "type": "single",
                "status": "processing", 
                "estimated_duration_seconds": duration,
                "transcript": None,
                "error": None
            }
            print(f"[API] Received single-file transcription request. Job ID: {job_id}, Duration: {duration:.2f} seconds.")
            threading.Thread(
                target=transcribe_single_file_async,
                args=(job_id, processed_file_path),
                daemon=True
            ).start()

    return jsonify({"job_id": job_id, "estimated_duration_minutes": round(duration / 60, 2)})

def get_single_job_status(job_info):
    """Formats status for a single-file transcription job."""
    return {
        "status": job_info["status"],
        "transcript": job_info.get("transcript"),
        "error": job_info.get("error"),
        "progress": 100 if job_info["status"] == "done" else (
            0 if job_info["status"] == "processing" else (
                10 if job_info["status"] == "converting_mic_audio" else ( 
                    25 if job_info["status"] == "converting" else (
                        50 if job_info["status"] == "uploading" else (
                            75 if job_info["status"] == "transcribing" else 0
                        )
                    )
                )
            )
        )
    }

def get_chunked_job_status(job_info):
    total_chunks = len(job_info["chunks"])
    completed_chunks = 0
    errored_chunks = 0
    current_status_messages = []
    partial_transcript_parts = [None] * total_chunks 

    if job_info["status"] == "splitting_audio":
        return {
            "status": "splitting_audio",
            "message": "Splitting audio into chunks...",
            "progress": 0,
            "transcript": None 
        }
    
    if total_chunks == 0: 
        return {
            "status": job_info["status"], 
            "message": job_info.get("error", "No chunks found after splitting."),
            "progress": 0,
            "transcript": None
        }

    for chunk_index in sorted(job_info["chunks"].keys()): 
        chunk_info = job_info["chunks"][chunk_index]
        if chunk_info["status"] == "done":
            completed_chunks += 1
            partial_transcript_parts[chunk_info["index"]] = chunk_info["transcript"]
        elif chunk_info["status"] == "error":
            errored_chunks += 1
            current_status_messages.append(f"Chunk {chunk_info['index']}: Error - {chunk_info['error']}")
        else:
            current_status_messages.append(f"Chunk {chunk_info['index']}: {chunk_info['status'].replace('_', ' ').capitalize()}")

    progress = (completed_chunks / total_chunks) * 100 if total_chunks > 0 else 0
    
    
    current_transcript = " ".join(filter(None, partial_transcript_parts))

    if errored_chunks > 0:
        return {
            "status": "error",
            "error": f"{errored_chunks} chunk(s) failed. Details: {'; '.join(current_status_messages)}",
            "progress": progress,
            "transcript": current_transcript 
        }
    elif completed_chunks == total_chunks:
        
        if job_info["status"] != "done": 
            job_info["status"] = "done"
            job_info["transcript"] = current_transcript
            print(f"[JOB {job_info['job_id']}] All chunks processed. Final transcript assembled.")
            with open("latest_transcript.json", "w", encoding="utf-8") as f:
                json.dump({"transcript": current_transcript}, f)

        return {
            "status": "done",
            "transcript": current_transcript,
            "progress": 100
        }
    else:
        
        return {
            "status": "processing_chunks",
            "message": f"Processing chunks: {completed_chunks}/{total_chunks} completed. Progress: {progress:.1f}%. Current chunk statuses: {', '.join(current_status_messages)}",
            "progress": progress,
            "transcript": current_transcript 
        }

@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Invalid job ID"}), 404
    
    job_info = jobs[job_id]
    job_info["job_id"] = job_id 

    if job_info["type"] == "single":
        return jsonify(get_single_job_status(job_info))
    elif job_info["type"] == "chunked":
        return jsonify(get_chunked_job_status(job_info))
    else:
        return jsonify({"status": "error", "error": "Unknown job type."}), 500


@app.route("/latest_transcript", methods=["GET"])
def latest_transcript():
    try:
        with open("latest_transcript.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "No latest transcript available. Upload an audio file first."}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Error decoding latest_transcript.json. File might be corrupted."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
