"""Bind an unkeyed nonstream turn to its HTTP connection, retaining worker ownership."""


async def _mochi_run_bound_nonstream(adapter, request, run_kwargs, *, poll_interval=0.1):
    import asyncio
    from contextlib import suppress

    # A keyed computation can have other subscribers and deliberately survives
    # a lost connection for replay. Preserve Hermes' existing cache/shield policy.
    if request.headers.get("Idempotency-Key"):
        return await adapter._run_agent(**run_kwargs)

    agent_ref = [None]
    agent_task = asyncio.create_task(adapter._run_agent(agent_ref=agent_ref, **run_kwargs))
    cleanup_task = None

    async def interrupt_and_drain(reason):
        from gateway.platforms.api_server import _abandon_agent_task

        # Cancellation may arrive while the executor is still constructing the
        # agent. Keep ownership until it publishes a reference or the turn ends.
        while not agent_task.done() and agent_ref[0] is None:
            await asyncio.wait((agent_task,), timeout=poll_interval)
        if not agent_task.done():
            async def protected_worker():
                return await asyncio.shield(agent_task)

            # Reuse Hermes' exact hard-interrupt and selective process-reaping
            # path. Cancel a shielded waiter, leaving the real wrapper alive so
            # _inflight_agent_runs and the executor's own finally stay truthful.
            waiter = asyncio.create_task(protected_worker())
            await _abandon_agent_task(
                agent_ref, waiter, reason, reap_source="api_server_http_disconnect")
        with suppress(asyncio.CancelledError, Exception):
            await asyncio.shield(agent_task)

    def cleanup(reason):
        nonlocal cleanup_task
        if cleanup_task is None:
            cleanup_task = asyncio.create_task(interrupt_and_drain(reason))
            # A second handler cancellation must not orphan the cleanup task.
            adapter._track_background_task(cleanup_task)
        return cleanup_task

    try:
        while not agent_task.done():
            transport = request.transport
            if transport is None or transport.is_closing():
                await asyncio.shield(cleanup("HTTP client disconnected"))
                raise ConnectionResetError("HTTP client disconnected")
            await asyncio.wait((agent_task,), timeout=poll_interval)
        return agent_task.result()
    except asyncio.CancelledError:
        await asyncio.shield(cleanup("HTTP handler cancelled"))
        raise
