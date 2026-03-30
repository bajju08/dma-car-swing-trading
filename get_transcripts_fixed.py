from youtube_transcript_api import YouTubeTranscriptApi

videos = [
    "sV1toZP3xXU",
    "hLYGIhMYO7M",
    "enDmS5AAlis",
    "5FMYp3TMhvY",
    "9EKL2Th6cdA",
    "XRZAYcHT2EQ",
    "GBU3bJgRMes"
]

for vid in videos:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(vid)
        # Get the first available transcript (likely English)
        transcript = transcript_list.find_manually_created_transcript(['en', 'hi']) or transcript_list.find_generated_transcript(['en', 'hi'])
        # Fetch the actual transcript
        fetched = transcript.fetch()
        text = " ".join([snippet.text for snippet in fetched])
        print(f"\nVideo {vid}: SUCCESS")
        print(f"First 500 chars: {text[:500]}...")
    except Exception as e:
        print(f"\nVideo {vid}: FAILED - {e}")
