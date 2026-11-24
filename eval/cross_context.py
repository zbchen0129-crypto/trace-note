"""Two synthetic cases, two views, at most four sequential live requests."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.long_context import read_json, guard_memory, memory_mb
from eval.run import digest
from backend.model import OpenAIModel, validate_output
from backend.core import Problem
from server import load_env

BOOK = {'id': 1, 'labels': [{'id': 'livingStandard', 'name': '生活水平提升',
    'definition': '生活水平提升被讨论为退出公共交通的候选原因。',
    'include': '支持、反对、引用或疑问均记录，并分别判断作者态度。', 'exclude': '无关主题。'}]}
CASES = [
    {'id': 'rebuttal', 'ending': '但本文不认可前述生活水平解释。本次研究发现，人们退出公共交通是因线路取消，而非生活水平提升。', 'expected': 'opposes'},
    {'id': 'endorsement', 'ending': '本文认可前述生活水平解释。本次研究发现，收入提高让人们买得起私家车，生活水平提升确实是他们退出公共交通的原因。', 'expected': 'supports'},
]


def payload_for(case, arm):
    paragraphs = [{'id': 'P001', 'text': '甲研究认为，人们放弃公共交通是因为生活水平的提升。'},
                  {'id': 'P002', 'text': '以下先交代资料整理过程，本文对上述解释的评价见后文。'},
                  {'id': 'P004', 'text': case['ending']}]
    return {'paragraph': paragraphs[0], 'context': paragraphs[1:2] if arm == 'adjacent' else paragraphs[1:],
            'codebookVersion': BOOK, 'researchQuestion': '本文作者是否认可生活水平提升导致退出公共交通这一解释？'}


def score(case, arm, output):
    annotations = output.get('annotations', [])
    expected = ['mentions', 'unclear'] if arm == 'adjacent' else [case['expected']]
    a = annotations[0] if len(annotations) == 1 else {}
    source_ok = a.get('stanceParagraphId') == 'P004' if arm == 'extra' else a.get('stanceParagraphId') in ('P001', 'P002')
    return {'expectedStances': expected, 'observed': a.get('stance'), 'source': a.get('stanceParagraphId'),
            'matched': len(annotations) == 1 and a.get('labelId') == 'livingStandard' and a.get('stance') in expected and source_ok}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    load_env(); model = OpenAIModel()
    manifest = {'casesHash': digest(CASES), 'bookHash': digest(BOOK),
                'adapterHash': digest((ROOT/'backend/model.py').read_bytes()),
                'runnerHash': digest(Path(__file__).read_bytes()), 'model': model.model,
                'maxLiveCalls': 4, 'maxInputChars': 8000, 'memoryBudgetMiB': 256,
                'maxResponseTokens': 2500, 'retries': 0}
    out = ROOT/'eval/results/cross-context-v1'; out.mkdir(parents=True, exist_ok=True)
    path = out/'manifest.json'
    if path.exists() and read_json(path) != manifest:
        raise SystemExit('Inputs changed; preserve old results in this directory.')
    path.write_text(json.dumps(manifest, indent=2))
    rows = []; calls = 0
    for case in CASES:
        for arm in ('adjacent', 'extra'):
            guard_memory()
            payload = payload_for(case, arm)
            if len(json.dumps(payload, ensure_ascii=False)) > 8000:
                raise SystemExit('Input limit exceeded; stopping without truncation.')
            path = out/(case['id']+'-'+arm+'.json')
            if path.exists():
                row = read_json(path)
            elif args.live and calls < 4:
                row = {'case': case['id'], 'arm': arm, 'payload': payload}
                calls += 1
                try:
                    row['output'] = model.generate('annotation', payload)
                    validate_output('annotation', row['output'], payload['paragraph'], BOOK['labels'], payload['context'])
                    row['validation'] = 'accepted'
                except Problem as error:
                    row.update(validation='failed', error=str(error))
                row['peakRssMiB'] = round(memory_mb(), 2)
                path.write_text(json.dumps(row, ensure_ascii=False, indent=2))
                guard_memory()
            else:
                raise SystemExit('Missing result; --live allows at most four sequential requests.')
            if row['validation'] != 'accepted':
                raise SystemExit('Failure saved; stopping without retry.')
            result = {'case': case['id'], 'arm': arm, **score(case, arm, row['output'])}
            rows.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    report = {'manifest': manifest, 'newCalls': calls, 'peakRssMiB': round(guard_memory(), 2), 'results': rows,
              'limitations': 'Assistant-authored synthetic cases; one sample per arm; adjacent inputs intentionally identical. Not independent accuracy evidence. Holder correctness is inspected manually, not scored.'}
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'newCalls': calls, 'peakRssMiB': report['peakRssMiB']}), flush=True)

if __name__ == '__main__':
    main()
