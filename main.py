import os
import requests
import base64
import math
import datetime
import yt_dlp
from pydub import AudioSegment
import anthropic
import gradio as gr

from dotenv import load_dotenv
load_dotenv(override=True)

def download_audio(youtube_url):
    output_path = "./staging/audio.%(ext)s"

    ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': output_path,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        upload_date = info.get("upload_date")  # Format: YYYYMMDD
        title = info.get("title", "")
        ydl.download([youtube_url])

    # Convert to desired format: %Y-%m-%d %H:%M:%S
    if upload_date:
        dt = datetime.datetime.strptime(upload_date, "%Y%m%d")
        upload_date_formatted = dt.strftime("%Y-%m-%d 00:00:00")
    else:
        upload_date_formatted = ""

    return upload_date_formatted, title

def chunk_audio():
    # Replace with your downloaded file name
    input_file = "./staging/audio.mp3"

    audio = AudioSegment.from_mp3(input_file)
    duration_ms = len(audio)
    part_length = math.ceil(duration_ms / 4)

    base_name = os.path.splitext(input_file)[0]

    for i in range(4):
        start = i * part_length
        end = min((i + 1) * part_length, duration_ms)
        part = audio[start:end]
        part.export(f"{base_name}_part{i+1}.mp3", format="mp3")

    print("Audio split into 4 parts.")

def transcribe_audio():
    # Load environment variables
    hf_token = os.getenv("HF_TOKEN")
    namespace = os.getenv("HF_NAMESPACE")
    name = os.getenv("HF_INFERENCE_ENDPOINT_NAME")
    url = os.getenv("HF_INFERENCE_ENDPOINT_URL")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }

    # Resume the endpoint
    resume_url = f"https://api.endpoints.huggingface.cloud/v2/endpoint/{namespace}/{name}/resume"
    print("Resuming the endpoint...")
    resume_response = requests.post(resume_url, headers=headers)

    if resume_response.status_code != 200:
        print(f"Failed to resume endpoint: {resume_response.text}")
        return ""

    # Wait for the endpoint to become active
    status_url = f"https://api.endpoints.huggingface.cloud/v2/endpoint/{namespace}/{name}"
    import time
    for _ in range(60):  # Check for up to 5 minute (60 * 5 seconds)
        status_response = requests.get(status_url, headers=headers)
        if status_response.status_code == 200:
            state = status_response.json().get("status", {}).get("state", "")
            if state == "running":
                print("Endpoint is running.")
                break
        time.sleep(5)
    else:
        print("Endpoint did not become running in time.")
        return ""

    # Transcribe audio
    try:
        transcriptions = []
        audio_files = []
        for i in range(4):
            print(f"Transcribing part {i+1}...")
            audio_file = f"./staging/audio_part{i+1}.mp3"
            audio_files.append(audio_file)
            with open(audio_file, "rb") as f:
                audio_data = f.read()
                audio_base64 = base64.b64encode(audio_data).decode("utf-8")

            data = {
                "inputs": audio_base64,
                "parameters": {}
            }

            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                transcription = response.json().get("text", "")
                transcriptions.append(transcription)
            else:
                transcriptions.append("")
    except Exception as e:
        print(f"Exception occurred while transcribing: {e}")
        transcriptions.append("")

    full_transcription = "\n".join(transcriptions)

    # Pause the endpoint
    pause_url = f"https://api.endpoints.huggingface.cloud/v2/endpoint/{namespace}/{name}/pause"
    print("Pausing the endpoint...")
    pause_response = requests.post(pause_url, headers=headers)
    if pause_response.status_code != 200:
        print(f"Failed to pause endpoint: {pause_response.text}")    

    # Delete all files in the staging folder after transcription
    staging_folder = "./staging"
    try:
        for filename in os.listdir(staging_folder):
            file_path = os.path.join(staging_folder, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
    except Exception as e:
        print(f"Exception occurred while deleting staging folder files: {e}")

    return full_transcription

def summarize_transcription(transcription, upload_date, title):
    claude = anthropic.Anthropic()

    model = os.getenv("CLAUDE_MODEL")

    system_message = """

    You are an assistant that analyzes and summarizes fantasy football podcast transcripts. 
    Your goal is to produce a structured Markdown summary.

    Rules:
    - Always respond in Markdown format. 
    - Include the Date in the top of the summary.
    - Include the Title in the top of the summary.
    - Start with a `## News Section` heading.  
    - Under the news section:
    - Use bullet points (`-`) for each piece of news.  
    - For each item, include:
        - **Player/Team**: Name
        - **News**: Short description
        - **Sentiment**: Positive / Negative / Neutral (from a fantasy football perspective)
    - After the news, create additional sections for the rest of the podcast discussion, such as:
    - `## Matchup Analysis`
    - `## Player Debates`
    - `## Waiver Wire Suggestions`
    - (Other relevant headings depending on content)
    - Within each section, use bullet points to summarize the main points, arguments, or insights.  
    - Keep the tone professional, clear, and concise.

    """

    user_prompt = "Here is a transcript of a fantasy football podcast."
    user_prompt += "Please summarize it using the structure described in the system prompt."
    user_prompt += f"Transcript (Date: {upload_date}, Title: {title}): \n\n{transcription}"

    print("Sending to Claude for summarization...")
    response = claude.messages.create(
        model=model,
        max_tokens=8000,
        system=system_message,
        messages=[{"role": "user", "content": user_prompt}],
    )
    summary = response.content[0].text if response.content else ""

    return summary

def fn_transcribe(youtube_url):
    upload_date, title = download_audio(youtube_url)
    chunk_audio()
    transcription = transcribe_audio()
    return transcription, upload_date, title

def fn_summarize(transcription, upload_date, title):
    return summarize_transcription(transcription, upload_date, title)

if __name__ == "__main__":

    with gr.Blocks() as ui:
        gr.Markdown("## Summarize Footballers Podcast")
        with gr.Row():
            with gr.Column():
                youtube_url_input = gr.Textbox(label="YouTube URL", value="", lines=1)
                youtube_url_date_output = gr.DateTime(label="Upload Date", value="")
                youtube_url_title_output = gr.Textbox(label="Title", value="")
                transcribe_output = gr.Textbox(label="Transcription Output", value="", lines=10)
                transcribe_button = gr.Button("Transcribe Audio")
                summarize_button = gr.Button("Summarize Transcript")
            with gr.Column():
                summarize_output = gr.Markdown(label="Summary")

        transcribe_button.click(fn=fn_transcribe, inputs=[youtube_url_input], outputs=[transcribe_output, youtube_url_date_output, youtube_url_title_output])
        summarize_button.click(fn=fn_summarize, inputs=[transcribe_output, youtube_url_date_output, youtube_url_title_output], outputs=[summarize_output])

    ui.launch(server_name="0.0.0.0", server_port=7860, inbrowser=True)