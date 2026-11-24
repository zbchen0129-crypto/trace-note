"""Sequential, size-bounded context-window experiment; no paid calls by default."""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import load_env
from backend.model import OpenAIModel, validate_output
from backend.core import Problem
from eval.run import digest

MAX_FILE_BYTES = 512_000
MAX_INPUT_CHARS = 32_000
MAX_CASES = 8
MEMORY_MB = 256
ARMS = ('adjacent', 'bounded_full')


def memory_mb():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024 if sys.platform == 'darwin' else 1024)


def guard_memory():
    peak = memory_mb()
    if peak > MEMORY_MB:
        raise ValueError(f'Peak RSS {peak:.1f} MiB exceeds {MEMORY_MB} MiB; stopping.')
    return peak


def read_json(path):
    with Path(path).open('rb') as f:
        data = f.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('Input/cache file exceeds byte budget')
    return json.loads(data)


def payload_for(case, arm, codebook):
    paragraphs = case['paragraphs']
    target = case['targetIndex']
    if not isinstance(target, int) or not 0 <= target < len(paragraphs):
        raise ValueError('Invalid target index')
    indices = range(max(0, target - 1), min(len(paragraphs), target + 2)) if arm == 'adjacent' else range(len(paragraphs))
    if arm not in ARMS:
        raise ValueError('Unknown context arm')
    payload = {'paragraph': paragraphs[target], 'context': [paragraphs[i] for i in indices if i != target],
               'codebookVersion': codebook, 'researchQuestion': '当前为何放弃公共交通？'}
    if 'scope' in codebook:
        payload['researchScope'] = codebook['scope']
    if len(json.dumps(payload, ensure_ascii=False)) > MAX_INPUT_CHARS:
        raise ValueError('Input exceeds character budget; no silent truncation')
    return payload


def summarize(case, arm, value, validation):
    labels = sorted({a['labelId'] for a in value.get('annotations', [])})
    # Adjacent views with hidden disambiguation are assessed for uncertainty,
    # not compared against an answer requiring information they never received.
    reference = case['references'][arm]
    uncertain = bool(value.get('abstainReason', '').strip() or value.get('reviewReasons'))
    return {'labels': labels, 'uncertaintySignaled': uncertain,
            'referenceLabels': reference['labels'], 'reviewExpected': reference['review'],
            'referenceMatched': labels == sorted(reference['labels']) and (uncertain or not reference['review']),
            'validation': validation}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', action='store_true', help='Explicit interviewee/current-time scope')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--max-calls', type=int, default=2)
    parser.add_argument('--output', default='eval/results/long-context-v1')
    args = parser.parse_args()
    if not 0 <= args.max_calls <= 16:
        raise SystemExit('max-calls must be between 0 and 16')
    cases = read_json(ROOT / 'eval/long-cases.json')
    if not 1 <= len(cases) <= MAX_CASES or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Case count or duplicate ID violation')
    book = read_json(ROOT / 'eval/codebook.json')
    if args.scope:
        book['scope'] = {'subject': '受访者本人；排除转述的其他人的经历', 'timeframe': '访谈所述当前退出公共交通的原因；排除已改善且不再影响当前决定的历史问题'}
    for case in cases:
        if not case['id'].isalnum():
            raise ValueError('Unsafe case ID')
        for arm in ARMS:
            payload_for(case, arm, book)
    load_env()
    model = OpenAIModel()
    manifest = {'casesHash': digest(cases), 'codebookHash': digest(book),
                'runnerHash': digest(Path(__file__).read_bytes()),
                'adapterHash': digest((ROOT / 'backend/model.py').read_bytes()),
                'model': model.model, 'arms': ARMS, 'referenceType': 'assistant-authored synthetic; not human gold',
                'maxInputChars': MAX_INPUT_CHARS, 'memoryBudgetMiB': MEMORY_MB}
    # Normalize tuples before comparing with JSON on subsequent invocations.
    manifest = json.loads(json.dumps(manifest))
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    mp = out / 'manifest.json'
    if mp.exists() and read_json(mp) != manifest:
        raise ValueError('Inputs changed; choose a fresh output directory')
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    calls = 0
    summaries = []
    for i, case in enumerate(cases):
        for arm in ARMS if i % 2 == 0 else ARMS[::-1]:
            peak = guard_memory()
            payload = payload_for(case, arm, book)
            path = out / f'{case["id"]}-{arm}.json'
            if path.exists():
                row = read_json(path)
                if row['payloadHash'] != digest(payload):
                    raise ValueError('Cached payload mismatch')
            elif args.live and calls < args.max_calls:
                if not model.configured:
                    raise ValueError('Model configuration missing')
                calls += 1
                started = time.monotonic()
                row = {'caseId': case['id'], 'arm': arm, 'payloadHash': digest(payload), 'payload': payload}
                try:
                    value = model.generate('annotation', payload)
                    row['output'] = value
                    try:
                        validate_output('annotation', value, payload['paragraph'], book['labels'], payload['context'])
                        row['validation'] = 'accepted'
                    except Problem as error:
                        row.update(validation='rejected', error=str(error))
                except Problem as error:
                    row.update(validation='request_failed', error=str(error))
                row.update(seconds=round(time.monotonic() - started, 3), peakRssMiB=round(memory_mb(), 2))
                path.write_text(json.dumps(row, ensure_ascii=False, indent=2))
                guard_memory()
                print(f'{case["id"]} {arm}: {row["validation"]}; peak RSS {memory_mb():.1f} MiB', flush=True)
            else:
                summaries.append({'caseId': case['id'], 'arm': arm, 'status': 'pending',
                                  'inputChars': len(json.dumps(payload, ensure_ascii=False))})
                continue
            if row['validation'] == 'request_failed':
                raise SystemExit('Request failed; cached for inspection. No retries or later calls.')
            summaries.append({'caseId': case['id'], 'arm': arm,
                              **summarize(case, arm, row['output'], row['validation'])})
    result = {'manifest': manifest, 'newCalls': calls, 'peakRssMiB': round(guard_memory(), 2), 'results': summaries}
    (out / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
