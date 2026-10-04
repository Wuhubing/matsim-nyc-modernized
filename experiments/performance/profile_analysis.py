#!/usr/bin/env python3
"""Read JFR execution stacks. Inclusive categories overlap, not wall-time shares."""
import argparse
import collections
import json
from pathlib import Path
import subprocess


def attribute(events):
    categories, custom, callers = collections.Counter(), collections.Counter(), collections.Counter()
    prefixes = {'routing': 'org.matsim.core.router', 'transit_routing': 'ch.sbb.matsim.routing',
                'event_xml': 'org.matsim.core.events.algorithms.EventWriterXML',
                'qsim': 'org.matsim.core.mobsim.qsim', 'nyc_custom': 'org.c2smart'}
    for event in events:
        stack = event['values'].get('stackTrace') or {}
        names = [f['method']['type']['name'].replace('/', '.')+'.'+f['method']['name'] for f in stack.get('frames', [])]
        custom.update(set(n for n in names if n.startswith('org.c2smart')))
        for category, prefix in prefixes.items():
            if any(n.startswith(prefix) for n in names):
                categories[category] += 1
        if names and names[0].startswith(('java.util.ImmutableCollections', 'java.util.BitSet')):
            callers[' > '.join(names[:6])] += 1
    return {'execution_samples': len(events), 'inclusive_categories_may_overlap': dict(categories),
            'custom_inclusive_samples': dict(custom.most_common(20)), 'set_and_bitset_callers': dict(callers.most_common(12)),
            'interpretation': 'Sample counts across whole run; overlapping stacks, not exclusive CPU or wall-time fractions.'}


def analyze(jfr_tool, recording):
    proc = subprocess.run([str(jfr_tool), 'print', '--json', '--events', 'jdk.ExecutionSample', str(recording)],
                          capture_output=True, text=True, check=True)
    result = attribute(json.loads(proc.stdout)['recording']['events'])
    recording.with_name('sample-attribution.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('recording', type=Path); parser.add_argument('--jfr-tool', type=Path, required=True)
    args = parser.parse_args(); print(json.dumps(analyze(args.jfr_tool, args.recording), indent=2))
