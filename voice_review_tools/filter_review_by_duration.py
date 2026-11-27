"""Filter a voice review CSV by actual WAV duration without modifying audio."""
import argparse
import csv
import wave
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('review', type=Path)
    p.add_argument('--base', type=Path, default=Path.cwd(), help='Base directory for relative audio_path values')
    p.add_argument('--output-dir', type=Path, default=Path.cwd())
    args = p.parse_args()
    with args.review.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    if not fields or 'audio_path' not in fields: p.error('review CSV needs an audio_path column')
    outfields = fields + ([] if 'duration_seconds' in fields else ['duration_seconds'])
    measured, failures = [], []
    for row in rows:
        audio = Path(row['audio_path'])
        if not audio.is_absolute(): audio = args.base / audio
        try:
            with wave.open(str(audio), 'rb') as wav:
                duration = wav.getnframes() / wav.getframerate()
            row['duration_seconds'] = f'{duration:.3f}'
            measured.append((duration, row))
        except (OSError, EOFError, wave.Error, ZeroDivisionError) as e:
            failures.append((str(audio), str(e)))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for threshold in (3, 5):
        destination = args.output_dir / f'voice_caption_review_{threshold}s_plus.csv'
        if destination.exists(): raise FileExistsError(f'Output already exists: {destination}')
        selected = [r for d, r in measured if d >= threshold]
        with destination.open('x', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=outfields); w.writeheader(); w.writerows(selected)
        with_candidates = sum(int(r.get('candidate_count') or 0) > 0 for r in selected)
        print(f'{threshold}s+: {len(selected)} files ({with_candidates} with candidates), output: {destination}')
    print(f'Measured: {len(measured)}, shorter than 3s: {sum(d < 3 for d, _ in measured)}, errors: {len(failures)}')
    for path, error in failures: print(f'ERROR: {path}: {error}')

if __name__ == '__main__': main()
