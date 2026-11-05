"""A lost HTTP client must stop only its turn and retain the real worker until exit."""
import asyncio
import hashlib
from pathlib import Path
import sys
import threading
import types

import pytest

from services.hermes_api.disconnect_guard import _mochi_run_bound_nonstream
from services.hermes_api import patch


class Transport:
    closed = False

    def is_closing(self):
        return self.closed


class Request:
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.transport = Transport()


class Agent:
    def __init__(self):
        self.construct = threading.Event()
        self.construct.set()
        self.release = threading.Event()
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.interrupts = []
        self.worker_running = False

    def hard_interrupt(self, reason):
        self.interrupts.append(reason)
        self.stopped.set()


class Adapter:
    def __init__(self):
        self.active = 0
        self.background = set()

    def _track_background_task(self, task):
        self.background.add(task)
        task.add_done_callback(self.background.discard)

    async def _run_agent(self, *, agent_ref=None, agent, result):
        self.active += 1

        def worker():
            agent.worker_running = True
            try:
                if not agent.construct.wait(3):
                    raise TimeoutError('Synthetic agent construction was not released')
                if agent_ref is not None:
                    agent_ref[0] = agent
                agent.started.set()
                if not agent.release.wait(3):
                    raise TimeoutError('Synthetic worker was not released')
                return result
            finally:
                agent.worker_running = False

        try:
            return await asyncio.get_running_loop().run_in_executor(None, worker)
        finally:
            self.active -= 1


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.005)


@pytest.fixture
def installed_interrupt_helper(monkeypatch):
    calls = []

    async def abandon(agent_ref, task, reason, *, reap_source, await_cancel=True):
        # The installed helper interrupts agent_ref[0], selectively reaps that
        # agent's process ownership, then cancels its supplied async wrapper.
        agent = agent_ref[0]
        calls.append((agent, reap_source))
        agent.hard_interrupt(reason)
        if not task.done():
            task.cancel()
            if await_cancel:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    module = types.ModuleType('gateway.platforms.api_server')
    module._abandon_agent_task = abandon
    monkeypatch.setitem(sys.modules, 'gateway.platforms.api_server', module)
    return calls


def test_disconnect_interrupts_only_owned_agent_and_keeps_thread_and_wrapper_until_exit(installed_interrupt_helper):
    async def scenario():
        adapter = Adapter()
        first, second = Agent(), Agent()
        first_request, second_request = Request(), Request()
        first_task = asyncio.create_task(_mochi_run_bound_nonstream(
            adapter, first_request, {'agent': first, 'result': ('abandoned', {})}, poll_interval=.005))
        final = ({'final_response': 'happy|Resultado final.', 'completed': True}, {'total_tokens': 2})
        second_task = asyncio.create_task(_mochi_run_bound_nonstream(
            adapter, second_request, {'agent': second, 'result': final}, poll_interval=.005))
        try:
            await until(lambda: first.started.is_set() and second.started.is_set())
            first_request.transport.closed = True
            await until(first.stopped.is_set)
            assert second.interrupts == []
            assert adapter.active == 2 and first.worker_running
            assert not first_task.done(), 'Cleanup lost the still-running executor worker'
            assert len(adapter.background) == 1
            first.release.set()
            with pytest.raises(ConnectionResetError, match='HTTP client disconnected'):
                await first_task
            assert adapter.active == 1 and not first.worker_running
            second.release.set()
            assert await second_task is final
            assert adapter.active == 0
            assert installed_interrupt_helper == [(first, 'api_server_http_disconnect')]
        finally:
            first.construct.set(); first.release.set()
            second.construct.set(); second.release.set()
            await asyncio.gather(first_task, second_task, return_exceptions=True)
    asyncio.run(scenario())


def test_disconnect_during_agent_creation_waits_for_own_reference(installed_interrupt_helper):
    async def scenario():
        adapter, request, agent = Adapter(), Request(), Agent()
        agent.construct.clear()
        task = asyncio.create_task(_mochi_run_bound_nonstream(
            adapter, request, {'agent': agent, 'result': ('unused', {})}, poll_interval=.005))
        try:
            await until(lambda: agent.worker_running)
            request.transport = None
            await asyncio.sleep(.02)
            assert adapter.active == 1 and not task.done()
            assert installed_interrupt_helper == []
            agent.construct.set()
            await until(agent.stopped.is_set)
            assert adapter.active == 1
            agent.release.set()
            with pytest.raises(ConnectionResetError):
                await task
            assert adapter.active == 0 and len(agent.interrupts) == 1
        finally:
            agent.construct.set(); agent.release.set()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_repeated_handler_cancellation_does_not_orphan_cleanup(installed_interrupt_helper):
    async def scenario():
        adapter, request, agent = Adapter(), Request(), Agent()
        task = asyncio.create_task(_mochi_run_bound_nonstream(
            adapter, request, {'agent': agent, 'result': ('unused', {})}, poll_interval=.005))
        try:
            await until(agent.started.is_set)
            task.cancel()
            await until(agent.stopped.is_set)
            assert adapter.active == 1 and len(adapter.background) == 1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert adapter.active == 1 and agent.worker_running and len(adapter.background) == 1
            agent.release.set()
            await until(lambda: adapter.active == 0 and not adapter.background)
            assert len(agent.interrupts) == 1
        finally:
            agent.release.set()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.gather(*adapter.background, return_exceptions=True)
    asyncio.run(scenario())


def test_keyed_computation_keeps_existing_shared_retry_semantics(installed_interrupt_helper):
    async def scenario():
        adapter, request, agent = Adapter(), Request({'Idempotency-Key': 'synthetic-retry'}), Agent()
        request.transport.closed = True
        final = ({'final_response': 'idle|Hecho.'}, {'total_tokens': 7})
        task = asyncio.create_task(_mochi_run_bound_nonstream(adapter, request, {'agent': agent, 'result': final}))
        try:
            await until(agent.started.is_set)
            assert not agent.interrupts and not adapter.background
            agent.release.set()
            assert await task is final
            assert installed_interrupt_helper == []
        finally:
            agent.release.set()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_success_returns_original_result_and_usage_unchanged(installed_interrupt_helper):
    async def scenario():
        adapter, request, agent = Adapter(), Request(), Agent()
        final = ({'final_response': 'idle|Respuesta original.', 'completed': True}, {'input_tokens': 9})
        agent.release.set()
        assert await _mochi_run_bound_nonstream(adapter, request, {'agent': agent, 'result': final}) is final
        assert not adapter.background and adapter.active == 0
        assert installed_interrupt_helper == []
    asyncio.run(scenario())


def fixture_source():
    return ('''import asyncio
class Adapter:
    async def chat(self, request):
        run_kwargs = {}
'''+patch.CHAT_CONTEXT+'''        return await self._run_idempotent(request, _compute_completion)
    async def responses(self, request):
        run_kwargs = {}
'''+patch.RESPONSES_CONTEXT+'''        return await self._run_idempotent(request, _compute_response)
'''+patch.INSERT_BEFORE+'''    pass
''').encode()


def test_hash_guard_rejects_unknown_code_without_writing(tmp_path):
    source = tmp_path/'upstream.py'; source.write_bytes(b'unknown code')
    with pytest.raises(ValueError, match='hash differs'):
        patch.apply(source, tmp_path/'backup')
    assert source.read_bytes() == b'unknown code'
    assert not (tmp_path/'backup').exists()


def test_prepare_retains_original_and_only_replaces_reviewed_call_sites(tmp_path, monkeypatch):
    raw = fixture_source()
    monkeypatch.setattr(patch, 'SUPPORTED_SOURCE_SHA256', hashlib.sha256(raw).hexdigest())
    source, candidate = tmp_path/'upstream.py', tmp_path/'candidate.py'
    source.write_bytes(raw)
    report = patch.prepare(source, candidate)
    assert source.read_bytes() == raw and report['installed'] is False
    expected = raw.decode().replace(patch.INSERT_BEFORE, patch.guard_source()+patch.INSERT_BEFORE)
    expected = expected.replace('return await self._run_agent(**run_kwargs)',
        'return await _mochi_run_bound_nonstream(self, request, run_kwargs)')
    assert candidate.read_text() == expected
    assert candidate.read_text().count('self._run_idempotent(request,') == 2


def test_context_guard_rejects_ambiguous_call_sites(monkeypatch):
    raw = fixture_source() + patch.CHAT_CONTEXT.encode()
    monkeypatch.setattr(patch, 'SUPPORTED_SOURCE_SHA256', hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match='context is not unique'):
        patch.patched_source(raw)


def test_apply_verifies_backup_preserves_mode_and_refuses_second_mutation(tmp_path, monkeypatch):
    raw = fixture_source()
    monkeypatch.setattr(patch, 'SUPPORTED_SOURCE_SHA256', hashlib.sha256(raw).hexdigest())
    source = tmp_path/'upstream.py'; source.write_bytes(raw); source.chmod(0o640)
    mode = source.stat().st_mode
    report = patch.apply(source, tmp_path/'backup')
    assert report['installed'] is True and report['service_restarted'] is False
    assert (tmp_path/'backup/upstream.py').read_bytes() == raw
    assert source.read_bytes() == patch.patched_source(raw)
    assert source.stat().st_mode == mode
    with pytest.raises(ValueError, match='hash differs'):
        patch.apply(source, tmp_path/'another-backup')
