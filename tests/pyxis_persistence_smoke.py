"""Opt-in live infrastructure smoke; no model calls, datasets or gold claims."""

import json
import sys

from domains.swe_agents.environment.pyxis import PyxisRuntime

runtime = PyxisRuntime(seconds=120)
session = runtime.launch(sys.argv[1], '/')
receipt = {'attestation': session.attestation, 'api_calls': 0}
try:
    session.write_file('/tmp/pcode-persistence-smoke', 'first')
    assert session.read_file('/tmp/pcode-persistence-smoke') == 'first'
    assert session.exec('printf second >> /tmp/pcode-persistence-smoke', 10)[0] == 0
    assert session.read_file('/tmp/pcode-persistence-smoke') == 'firstsecond'
    assert session.exec('exit 7', 10)[0] == 7
    assert session.exec('printf alive', 10) == (0, 'alive', '')
    receipt['persistence_passed'] = True
finally:
    session.stop()
receipt['launcher_exit'] = session.process.returncode
assert session.process.returncode == 0
print(json.dumps(receipt, sort_keys=True))
