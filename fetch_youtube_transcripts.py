from youtube_transcript_api import YouTubeTranscriptApi
import json

# Video IDs from user's message
videos = [
    "sV1toZP3xXU",
    "hLYGIhMYO7M",
    "enDmS5AAlis",
    "5FMYp3TMhvY",
    "9EKL2Th6cdA",
    "XRZAYcHT2EQ",
    "GBU3bJgRMes"
]

results = {}

for vid in videos:
    print(f"Fetching transcript for: {vid}")
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(vid, languages=['en', 'hi'])
        # Combine all text segments
        full_text = " ".join([entry['text'] for entry in transcript_list])
        results[vid] = {
            "status": "success",
            "language": transcript_list[0].get('language', 'unknown') if transcript_list else 'unknown',
            "segments": len(transcript_list),
            "text": full_text[:5000]  # limit length
        }
        print(f"  -> Got {len(transcript_list)} segments")
    except Exception as e:
        results[vid] = {
            "status": "failed",
            "error": str(e)
        }
        print(f"  -> Error: {e}")

# Save to file
with open("youtube_transcripts.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\nTranscripts saved to youtube_transcripts.json")
print("\nSUMMARY:")
for vid, data in results.items():
    status = "✅" if data.get("status") == "success" else "❌"
    print(f"  {status} {vid}: {data.get('status', 'unknown')}")
