from flask import Flask, render_template, request
import requests
import google.generativeai as genai
import json
import re
from collections import OrderedDict

app = Flask(__name__)

genai.configure(api_key="AIzaSyBBGllnIZdo11cUjURk7d3V46xqgYmjIWc")

SUMMARIZER_GENERATE_API = "http://127.0.0.1:5002/"
SUMMARIZER_LATEST_API = "http://127.0.0.1:5002/latest_summary"

@app.route("/", methods=["GET", "POST"])
def quiz_home():
    if request.method == "POST":
        try:
            requests.post(SUMMARIZER_GENERATE_API)
            res = requests.get(SUMMARIZER_LATEST_API)

            if res.status_code != 200:
                return f"<h3>Error fetching summary: {res.text}</h3>"

            summary = res.json().get("summary")
            if not summary:
                return "<h3>No summary received from summarizer.</h3>"

            prompt = f"""
            Based on the following summary, generate 20 multiple choice questions.
            Each should include:
            - question (string)
            - options (list of 4 strings)
            - answer (correct option as text)
            - explanation (why this answer is correct)
            Format response as JSON list.

            Summary:
            {summary}
            """

            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            response = model.generate_content(prompt)

            raw_text = response.text.strip()
            cleaned_text = re.sub(r"^```json\s*|```$", "", raw_text, flags=re.DOTALL).strip()

            try:
                quiz_raw = json.loads(cleaned_text)
            except json.JSONDecodeError:
                # Try to extract the JSON from the text manually
                json_match = re.search(r"\[.*\]", cleaned_text, re.DOTALL)
                if json_match:
                    quiz_raw = json.loads(json_match.group(0))
                else:
                    return f"<h3>Invalid JSON received from Gemini: <pre>{cleaned_text}</pre></h3>"

            quiz_data = []
            for q in quiz_raw:
                quiz_data.append({
                    "question": q.get("question"),
                    "options": q.get("options"),
                    "answer": q.get("answer"),
                    "explanation": q.get("explanation")
                })

            app.config["QUIZ_DATA"] = quiz_data
            return render_template("quiz.html", quiz=quiz_data)

        except Exception as e:
            return f"<h3>Error generating quiz: {str(e)}</h3>"

    return render_template("quiz.html", quiz=None)

@app.route("/submit", methods=["POST"])
def submit_quiz():
    quiz_data = app.config.get("QUIZ_DATA", [])
    total = len(quiz_data)
    score = 0
    analysis = []

    for i in range(total):
        q = quiz_data[i]
        user_answer = request.form.get(f"q{i}")
        is_correct = user_answer == q["answer"]
        if is_correct:
            score += 1
        analysis.append({
            "question": q["question"],
            "selected": user_answer,
            "correct": q["answer"],
            "is_correct": is_correct,
            "explanation": q["explanation"]
        })

    return render_template("result.html", score=score, total=total, analysis=analysis)

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5003, debug=True)
