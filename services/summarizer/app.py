from flask import Flask, request, jsonify, render_template, send_file
import requests
import google.generativeai as genai
import io

app = Flask(__name__)

genai.configure(api_key="AIzaSyAMqNwjBY9i8N8nkK_0q7d0dNiZSAX-2wk")  
SPEECH_TO_TEXT_API = "http://40.90.194.113:5001/latest_transcript"

latest_summary_text = None

@app.route("/", methods=["GET", "POST"])
def summarize():
    global latest_summary_text
    summary_text = None
    status_message = None
    status_type = "info"

    if request.method == "POST":
        try:
            
            print("Fetching transcript from:", SPEECH_TO_TEXT_API)
            response = requests.get(SPEECH_TO_TEXT_API, timeout=10)
            
            if response.status_code != 200:
                status_message = f"❌ Error fetching transcript: {response.text}"
                status_type = "error"
                return render_template('index.html', 
                                     summary=None, 
                                     status_message=status_message,
                                     status_type=status_type)
            
            transcript_data = response.json()
            transcript = transcript_data.get("transcript", "").strip()
            
            if not transcript:
                status_message = "❌ No transcript found. Please record or upload audio first on the main transcription page."
                status_type = "error"
                return render_template('index.html', 
                                     summary=None, 
                                     status_message=status_message,
                                     status_type=status_type)
            
            
            custom_prompt = request.form.get("custom_prompt", "").strip()
            
            
            if custom_prompt:
                prompt = f"{custom_prompt}\n\nTranscript:\n{transcript}"
            else:
                prompt = f"Summarize the following contents and give an in-depth explanation:\n\n{transcript}"
            
            print(f"Generating summary with prompt length: {len(prompt)} characters")
            
            
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            gemini_response = model.generate_content(prompt)
            summary_text = gemini_response.text.strip()
            latest_summary_text = summary_text
            
            status_message = "✅ Summary generated successfully!"
            status_type = "success"
            
        except requests.RequestException as e:
            status_message = f"❌ Connection error: Unable to fetch transcript. Make sure the transcription service is running on port 5001."
            status_type = "error"
            print(f"Request error: {e}")
        except Exception as e:
            status_message = f"❌ Error generating summary: {str(e)}"
            status_type = "error"
            print(f"Summary generation error: {e}")

    return render_template('index.html', 
                         summary=summary_text,
                         status_message=status_message,
                         status_type=status_type)


@app.route("/latest_summary", methods=["GET"])
def get_latest_summary():
    """API endpoint to get the latest summary as JSON"""
    if latest_summary_text:
        return jsonify({"summary": latest_summary_text})
    return jsonify({"error": "No summary available"}), 404


@app.route("/download_summary", methods=["GET"])
def download_summary():
    """Download the latest summary as a text file"""
    if latest_summary_text:
        file_stream = io.StringIO(latest_summary_text)
        return send_file(
            io.BytesIO(file_stream.getvalue().encode("utf-8")),
            as_attachment=True,
            download_name="summary.txt",
            mimetype="text/plain"
        )
    return jsonify({"error": "No summary available"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
