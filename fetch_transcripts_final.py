from youtube_transcript_api import YouTubeTranscriptApi

videos = {
    "sV1toZP3xXU": "DMA-DMA Strategy",
    "hLYGIhMYO7M": "CAR Averaging",
    "enDmS5AAlis": "6.28% Target",
    "5FMYp3TMhvY": "Compounding",
    "9EKL2Th6cdA": "Risk Management",
    "XRZAYcHT2EQ": "Entry/Exit",
    "GBU3bJgRMes": "Advanced Concepts"
}

transcripts = {}

for vid, title in videos.items():
    try:
        # Try English (India) and Hindi
        transcript = YouTubeTranscriptApi().fetch(vid, languages=['en-IN', 'hi', 'en'])
        text = " ".join([snippet.text for snippet in transcript])
        transcripts[vid] = {
            "title": title,
            "status": "success",
            "text": text,
            "segments": len(transcript)
        }
        print(f"[OK] {title} ({vid}) - {len(transcript)} segments")
    except Exception as e:
        transcripts[vid] = {
            "title": title,
            "status": "failed",
            "error": str(e)
        }
        print(f"[FAIL] {title} ({vid}): {e}")

# Save all transcripts
import json
with open("strategy_transcripts.json", "w", encoding="utf-8") as f:
    json.dump(transcripts, f, indent=2, ensure_ascii=False)

print(f"\nSaved {len([v for v in transcripts.values() if v['status']=='success'])} transcripts to strategy_transcripts.json")
