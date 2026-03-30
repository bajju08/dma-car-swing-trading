import json

with open('strategy_transcripts.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for vid, info in data.items():
    if info['status'] == 'success':
        print(f"\n{'='*60}")
        print(f"Video: {info['title']} ({vid})")
        print(f"Segments: {info['segments']}")
        print(f"Sample text (first 1000 characters):")
        print(info['text'][:1000])
        print('...')
        break  # just show one

print(f"\nTotal videos: {len(data)}")
successful = sum(1 for v in data.values() if v['status']=='success')
print(f"Successful: {successful}")
