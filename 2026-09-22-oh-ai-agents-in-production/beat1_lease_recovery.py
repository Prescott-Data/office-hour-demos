"""
Demo 1 - a worker freezes mid-step. What happens to the step?

No LLM, no keys. Needs Redis on localhost:6379:
    docker compose -f docker-compose.infra.yml up -d redis

Uses the real RedisContextStore (jarviscore/storage/redis_store.py). Each worker
runs the same sequence as Mesh._run_distributed_worker (core/mesh.py): recover
expired claims, claim a pending step, work, commit. Nothing is mocked.

Timeline:
  1. Seed a 3-step chain: fetch -> transform -> publish.
  2. worker-a claims `transform` with a short lease and keeps renewing it.
  3. worker-a is frozen (SIGSTOP): silent, but still believes it owns the step.
  4. The lease runs out. worker-b recovers the step and finishes the workflow.
  5. worker-a is resumed. Its late commit is refused: it no longer owns the lease.

Run:
    python beat1_lease_recovery.py            # orchestrator (what you demo)
    python beat1_lease_recovery.py --cleanup  # also delete this run's keys
"""
import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import uuid

from jarviscore.storage.redis_store import RedisContextStore

LEASE = 6            # seconds a claim lives without renewal
WORK = {"fetch": 1, "transform": 4, "publish": 1}   # seconds of "work" per step
STEPS = [
    {"id": "fetch", "capability": "worker", "task": "fetch inputs", "depends_on": []},
    {"id": "transform", "capability": "worker", "task": "transform", "depends_on": ["fetch"]},
    {"id": "publish", "capability": "worker", "task": "publish", "depends_on": ["transform"]},
]

_TTY = sys.stdout.isatty()


def c(code, text):
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def say(who, msg, colour="0"):
    print(f"{c('90', f'{who:<12}')} {c(colour, msg)}", flush=True)


def all_completed(store, wf):
    return all(store.get_step_status(wf, s["id"]) == "completed" for s in STEPS)


# ---------------------------------------------------------------- worker ----
def run_worker(name, wf):
    store = RedisContextStore()
    while not all_completed(store, wf):
        for step_id in store.get_all_step_ids(wf):
            step = store.get_step_definition(wf, step_id) or {}
            if step.get("status") == "in_progress":
                if store.recover_expired_step_claim(wf, step_id):
                    say(name, f"recovered expired claim on '{step_id}'", "33")
                    step = store.get_step_definition(wf, step_id) or {}
            if step.get("status") != "pending":
                continue
            claim_id = f"{name}:{uuid.uuid4().hex[:6]}"
            if not store.claim_step(wf, step_id, claim_id, lease_seconds=LEASE):
                continue
            say(name, f"claimed '{step_id}' as {claim_id} (lease {LEASE}s)", "36")

            stop = threading.Event()

            def heartbeat(step_id=step_id, claim_id=claim_id, stop=stop):
                while not stop.wait(LEASE / 3):
                    if not store.renew_step_claim(wf, step_id, claim_id, LEASE):
                        return

            threading.Thread(target=heartbeat, daemon=True).start()
            time.sleep(WORK[step_id])
            stop.set()

            ok = store.finish_claimed_step(
                wf, step_id, claim_id,
                {"status": "success", "output": f"{step_id} finished by {name}"},
            )
            if ok:
                say(name, f"committed '{step_id}'", "32")
            else:
                say(name, f"commit of '{step_id}' REFUSED - {claim_id} no longer owns the lease", "31")
        time.sleep(0.5)


# ---------------------------------------------------------- orchestrator ----
def spawn(name, wf):
    return subprocess.Popen(
        [sys.executable, "-u", os.path.abspath(__file__), "--worker", name, "--wf", wf]
    )


def show(store, wf, t0, note=""):
    step = store.get_step_definition(wf, "transform") or {}
    ttl = store._redis.ttl(f"step_lock:{wf}:transform")
    ttl_txt = f"{ttl}s" if ttl and ttl > 0 else "gone"
    who = step.get("claimed_by", "-")
    say(f"t+{int(time.time() - t0):02d}s",
        f"lock TTL {ttl_txt:>5}   transform: {step.get('status', '?'):<11} owner={who:<9} {note}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker")
    ap.add_argument("--wf")
    ap.add_argument("--cleanup", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    if args.worker:
        run_worker(args.worker, args.wf)
        return

    store = RedisContextStore()
    if not store.enabled:
        sys.exit("Redis is not reachable on localhost:6379 - start it first (see docstring).")

    wf = f"demo-lease-{int(time.time())}"
    print(c("1", f"\nworkflow {wf}: fetch -> transform -> publish\n"))
    store.init_workflow_graph(wf, STEPS)

    a = spawn("worker-a", wf)
    deadline = time.time() + 15
    while time.time() < deadline:
        s = store.get_step_definition(wf, "transform") or {}
        if s.get("status") == "in_progress" and s.get("claimed_by") == "worker-a":
            break
        time.sleep(0.2)
    else:
        a.kill()
        sys.exit("worker-a never claimed 'transform' - is Redis healthy?")

    time.sleep(2)
    t0 = time.time()
    say("orchestrator", "FREEZE worker-a (SIGSTOP) mid-step: silent, but it still thinks it owns 'transform'", "1;33")
    os.kill(a.pid, signal.SIGSTOP)
    b = spawn("worker-b", wf)

    while store.get_step_status(wf, "transform") != "completed" and time.time() - t0 < 40:
        show(store, wf, t0)
        time.sleep(1)
    show(store, wf, t0, "<- worker-b took over")

    while not all_completed(store, wf) and time.time() - t0 < 60:
        time.sleep(0.5)

    say("orchestrator", "RESUME worker-a (SIGCONT): it wakes up believing it still owns 'transform'", "1;33")
    os.kill(a.pid, signal.SIGCONT)
    try:
        a.wait(timeout=20)
        b.wait(timeout=20)
    except subprocess.TimeoutExpired:
        a.kill()
        b.kill()

    print(c("1", "\nledger (XRANGE ledgers:<workflow>)"))
    for entry_id, fields in store._redis.xrange(f"ledgers:{wf}"):
        detail = fields.get("claim_id") or fields.get("agent_id") or ""
        print(f"  {entry_id:<18} {fields.get('event', ''):<20} {fields.get('step_id', ''):<10} {detail}")

    done = store.get_step_definition(wf, "transform") or {}
    print(c("1", f"\ntransform completed by: {done.get('completed_by')}   (claim {done.get('claim_id')})"))
    print(c("90", f"\ninspect: redis-cli --scan --pattern '*:{wf}*'   |   redis-cli XRANGE ledgers:{wf} - +"))

    if args.cleanup:
        store.flush_workflow(wf)


if __name__ == "__main__":
    main()
