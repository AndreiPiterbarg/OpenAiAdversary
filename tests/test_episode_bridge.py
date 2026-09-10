"""Bridge protocol and spending guards using local subprocesses and fake models."""

import json
import sys

import pytest

from adversary.core.model import Completion, CompletionRequest, Message, Usage
from domains.swe_agents.scripts import episode_bridge as bridge


def event(episode='one', call=1, **changes):
    request = CompletionRequest(messages=(Message(role='user', content='Fix it.'),),
                                max_tokens=512).model_dump(mode='json')
    request.update(changes)
    return {'event': 'model_request', 'episode_id': episode, 'call': call, 'request': request}


def controller(events):
    script = ('import json,sys,os\n'
              "assert 'OPENAI_API_KEY' not in os.environ\n"
              f'events=json.loads({json.dumps(events)!r})\n'
              'for value in events:\n'
              ' print(json.dumps(value),flush=True)\n'
              " if value.get('event')=='model_request':\n"
              '  reply=json.loads(sys.stdin.readline())\n'
              "  assert reply['message']['content']=='done'\n"
              "print(json.dumps({'event':'finished'}),flush=True)\n")
    return [sys.executable, '-c', script]


@pytest.fixture
def fake(monkeypatch, tmp_path):
    calls = []
    out = tmp_path / 'ledger'

    class Model:
        def __init__(self, **config):
            assert config == {'model': 'gpt-6-astra', 'reasoning_effort': 'low', 'timeout_seconds': 120}

        def complete(self, request):
            assert len(list(out.glob('call-*-request.json'))) == len(calls) + 1
            calls.append(request)
            return Completion(message=Message(role='assistant', content='done'),
                              usage=Usage(input_tokens=10, output_tokens=3),
                              raw={'usage': {'input_tokens': 10, 'output_tokens': 3}})

    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-bridge-key')
    monkeypatch.setattr(bridge, 'OpenAIModel', Model)
    return out, calls


def test_two_calls_durable_usage_and_other_events(fake, capsys):
    out, calls = fake
    summary = bridge.run_bridge(controller([event(), event(call=2)]), out)
    assert len(calls) == summary['model_calls'] == 2
    assert all(request.reasoning_effort == 'low' for request in calls)
    assert summary['usage'] == {'input_tokens': 20, 'output_tokens': 6}
    assert len(list(out.glob('*completion.json'))) == 2
    assert json.loads(next(out.glob('event-*.json')).read_text()) == {'event': 'finished'}
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('events', [
    [event(call=2)], [event(), event()], [event(), event(episode='two')],
    [event(max_tokens=1025)], [event(max_tokens=True)], [event(reasoning_effort='high')],
    [event(tools=[{'type': 'function', 'function': {'name': 'install'}}])],
    [event(tools=[{'type': 'function', 'function': {
        'name': 'shell', 'type': 'web_search', 'parameters': {},
    }}])],
    [event(messages=[{'role': 'user', 'content': 'x' * 32768}])],
])
def test_invalid_requests_stop_without_an_extra_call(fake, events):
    out, calls = fake
    with pytest.raises(bridge.BridgeError):
        bridge.run_bridge(controller(events), out)
    assert len(calls) == len(events) - 1
    failure = json.loads((out / 'failure.json').read_text())
    assert not failure['billing_unknown']


def test_eight_calls_are_the_episode_limit(fake):
    out, calls = fake
    with pytest.raises(bridge.BridgeError):
        bridge.run_bridge(controller([event(call=i, max_tokens=1024) for i in range(1, 10)]), out)
    assert len(calls) == 8


@pytest.mark.parametrize('exception', [RuntimeError, KeyboardInterrupt])
def test_api_failure_is_not_retried_and_billing_remains_unknown(fake, monkeypatch, exception):
    out, calls = fake

    def fail(self, request):
        calls.append(request)
        raise exception('synthetic-bridge-key')

    monkeypatch.setattr(bridge.OpenAIModel, 'complete', fail)
    with pytest.raises(bridge.BridgeError) as error:
        bridge.run_bridge(controller([event()]), out)
    assert len(calls) == 1 and error.value.__suppress_context__
    assert json.loads((out / 'failure.json').read_text())['billing_unknown']
    assert all('synthetic-bridge-key' not in path.read_text() for path in out.iterdir())


def test_existing_ledger_refused_without_model_call(fake):
    out, calls = fake
    out.mkdir()
    with pytest.raises(FileExistsError):
        bridge.run_bridge(controller([]), out)
    assert not calls


@pytest.mark.parametrize('output', ['{}', '{"event":"done","event":"other"}', 'x' * 2_000_001])
def test_malformed_or_oversized_controller_line_fails_without_call(fake, output):
    out, calls = fake
    argv = [sys.executable, '-c', 'import sys;sys.stdout.write(' + repr(output[:100] + '\n') + ')']
    # Avoid an OS argv-size limit for the oversized case.
    if len(output) > 100:
        argv = [sys.executable, '-c', "print('x'*2000001,flush=True)"]
    with pytest.raises(bridge.BridgeError):
        bridge.run_bridge(argv, out)
    assert not calls


def test_completion_is_saved_before_forwarding(fake, monkeypatch):
    out, calls = fake
    original = bridge._send

    def checked_send(stream, value):
        saved = json.loads(next(out.glob('*completion.json')).read_text())
        assert saved == value
        return original(stream, value)

    monkeypatch.setattr(bridge, '_send', checked_send)
    bridge.run_bridge(controller([event()]), out)
    assert len(calls) == 1


@pytest.mark.parametrize("exited", [True, False])
def test_cleanup_permission_error_only_ignored_after_owned_child_exit(fake, monkeypatch, exited):
    out, calls = fake
    original = bridge.subprocess.Popen
    processes = []

    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    def denied(pid, signum):
        assert pid == processes[0].pid
        if exited:
            processes[0].wait(timeout=5)
        raise PermissionError("simulated process-group race")

    monkeypatch.setattr(bridge.subprocess, "Popen", capture)
    monkeypatch.setattr(bridge.os, "killpg", denied)
    argv = [sys.executable, "-c", 'import time; print("{}", flush=True); time.sleep(0.2)']
    try:
        with pytest.raises(bridge.BridgeError if exited else PermissionError):
            bridge.run_bridge(argv, out)
    finally:
        for process in processes:
            process.wait(timeout=5)
    assert not calls
    assert json.loads((out / "failure.json").read_text())["model_calls"] == 0


def test_explicit_astra_twenty_call_four_episode_bounds(fake):
    out, calls = fake
    events = [event(episode=f'cell-{cell}', call=call, max_tokens=1024)
              for cell in range(4) for call in range(1, 21)]
    result = bridge.run_bridge(controller(events), out, maxepisodes=4, call_limit=20,
                               output_limit=20480, request_byte_limit=65536)
    assert len(calls) == result['model_calls'] == 80
    assert result['episodes'] == 4


def test_explicit_hundred_call_budget_is_opt_in():
    episodes = {}
    for i in range(1, 101):
        bridge._request(event(call=i, max_tokens=1024), episodes, 5,
                        call_limit=100, output_limit=102400, request_byte_limit=262144)
    assert episodes['one'] == (100, 102400)
    with pytest.raises(bridge.BridgeError):
        bridge._request(event(call=101), episodes, 5,
                        call_limit=100, output_limit=102400, request_byte_limit=262144)
    with pytest.raises(bridge.BridgeError):
        bridge._request(event(call=9), {'one': (8, 4096)}, 1)
