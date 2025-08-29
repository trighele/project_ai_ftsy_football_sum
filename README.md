# Fantasy Football Podcast Summarizer

This application automatically downloads, transcribes, and summarizes fantasy football podcasts using AI. It uses Whisper for transcription and Claude for generating structured summaries.

## Features

- Downloads audio from YouTube URLs
- Splits audio into manageable chunks for processing
- Transcribes audio using Hugging Face's Whisper model
- Generates structured summaries using Claude AI
- Web interface built with Gradio

## Prerequisites

- Python 3.11+
- Poetry for dependency management
- Docker (optional)
- FFmpeg (for audio processing)
- API Keys:
  - Hugging Face API Token
  - Anthropic API Key (for Claude)

## Environment Variables

Create a `.env` file with the following variables:
```env
HF_TOKEN=your_huggingface_token
HF_NAMESPACE=your_namespace
HF_INFERENCE_ENDPOINT_NAME=your_endpoint_name
HF_INFERENCE_ENDPOINT_URL=your_endpoint_url
ANTHROPIC_API_KEY=your_anthropic_key
CLAUDE_MODEL=claude-3-sonnet-20240229
```

## Installation

### Using Poetry (Local Development)

1. Clone the repository:
```bash
git clone https://github.com/yourusername/project_ai_ftsy_football_sum.git
cd project_ai_ftsy_football_sum
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Run the application:
```bash
poetry run python main.py
```

### Using Docker

1. Build and run using Docker Compose:
```bash
docker-compose up --build
```

The application will be available at `http://localhost:7860`

## Usage

1. Open the web interface at `http://localhost:7860`
2. Paste a YouTube URL of a fantasy football podcast
3. Click "Transcribe Audio" to process the audio
4. Click "Summarize Transcript" to generate a structured summary

## Output Format

The summary is generated in Markdown format with the following sections:
- Date and Title
- News Section (with Player/Team, News, and Sentiment)
- Matchup Analysis
- Player Debates
- Waiver Wire Suggestions
- Additional relevant sections based on content

## Project Structure

```
project_ai_ftsy_football_sum/
├── main.py           # Main application code
├── pyproject.toml    # Poetry dependency management
├── requirements.txt  # Docker dependencies
├── Dockerfile       # Docker configuration
├── docker-compose.yml
└── staging/         # Temporary directory for audio processing
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
