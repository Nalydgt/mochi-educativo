"""Claim the hosted web's authorized inference jobs over an outbound SQL connection."""

import asyncio
import logging
import time

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


async def serve_queue(dsn, key):
    log = logging.getLogger("uvicorn.error")
    async with httpx.AsyncClient(timeout=160, base_url="http://127.0.0.1:8000") as client:
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    dsn, autocommit=True, prepare_threshold=None, row_factory=dict_row
                ) as connection:
                    log.info("PELUQO hosted inference queue connected")
                    next_cleanup = 0
                    while True:
                        if time.monotonic() >= next_cleanup:
                            await connection.execute("DELETE FROM education.inference_jobs WHERE expires_at <= now()")
                            next_cleanup = time.monotonic() + 30
                        cursor = await connection.execute(
                            """WITH next AS (
                                 SELECT id FROM education.inference_jobs
                                 WHERE status='queued' AND expires_at>now()
                                 ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
                               )
                               UPDATE education.inference_jobs j SET status='running'
                               FROM next WHERE j.id=next.id RETURNING j.id,j.kind,j.payload"""
                        )
                        job = await cursor.fetchone()
                        if job is None:
                            await asyncio.sleep(2)
                            continue
                        status, result = "failed", None
                        try:
                            reply = await client.post(
                                "/" + job["kind"],
                                headers={"Authorization": "Bearer " + key},
                                json=job["payload"],
                            )
                            reply.raise_for_status()
                            result, status = Jsonb(reply.json()), "ready"
                        except (httpx.HTTPError, ValueError) as exc:
                            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 503:
                                try:
                                    if exc.response.json().get("detail") == "education_ai_usage_limit":
                                        result = Jsonb({"error": "education_ai_usage_limit"})
                                except (ValueError, AttributeError):
                                    pass
                            log.warning("Hosted educational job failed: %s", type(exc).__name__)
                        await connection.execute(
                            "UPDATE education.inference_jobs SET status=%s,result=%s,payload=NULL WHERE id=%s AND status='running'",
                            (status, result, job["id"]),
                        )
            except (psycopg.Error, OSError) as exc:
                log.warning("Hosted queue reconnecting: %s", type(exc).__name__)
                await asyncio.sleep(5)
