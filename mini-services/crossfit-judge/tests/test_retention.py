import time
from jobs.store import JobStore
from config.settings import UPLOADS_DIR


def test_retention_purges_only_old_finished_jobs(tmp_path):
    st = JobStore()
    old, new, running = (st.create({}, "/x", "/y") for _ in range(3))
    for jid in (old, new, running):
        (UPLOADS_DIR / jid).mkdir(parents=True, exist_ok=True)
        (UPLOADS_DIR / jid / "original.mp4").write_bytes(b"x")
    st._update(old, status="done"); st._update(new, status="done"); st._update(running, status="running")
    st._db.execute("UPDATE jobs SET created_at = ? WHERE id IN (?, ?)",
                   (time.time() - 40 * 86400, old, running)); st._db.commit()
    assert st.purge_older_than(30) == 1
    assert st.get(old) is None and not (UPLOADS_DIR / old).exists()
    assert st.get(new) is not None and (UPLOADS_DIR / new).exists()
    assert st.get(running) is not None          # active jobs are never purged
    assert st.purge_older_than(0) == 0           # 0 = disabled
