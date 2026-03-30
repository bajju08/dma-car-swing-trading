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
        transcript = YouTubeTranscriptApi.get_transcript(vid)
        text = " ".join([t['text'] for t in transcript])
        print(f"\n=== Video: {vid} ===")
        print(f"Duration: {len(transcript)} segments")
        print(f"Text preview: {text[:500]}...")
    except Exception as e:
        print(f"\n=== Video: {vid} ===")
        print(f"Failed: {e}")
