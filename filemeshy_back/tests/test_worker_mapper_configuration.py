"""Regresión -- bug real de producción (Ronda 6, revisión adversarial
2026-09-21): antes de este fix, `app.worker.tasks.indexing` tenía su
propio import defensivo de "todos los modelos" para que
`configure_mappers()` no reviente (varias relaciones ORM del proyecto
resuelven 'User'/'Role'/'Session'/etc. como STRING, no como referencia de
clase real -- ver docstring de
`app.worker.celery_app._register_all_orm_models`), pero
`app.worker.tasks.email` NO lo tenía. Si una tarea de email corría PRIMERO
en el mismo proceso de un worker real y disparaba `configure_mappers()`
sin que esas clases estuvieran importadas todavía, el registry de
SQLAlchemy quedaba ROTO PARA SIEMPRE en ese proceso -- ni siquiera el
import correcto de `indexing.py`, que corría DESPUÉS, lo destrababa.
Confirmado en logs reales de `celery_worker`: las tareas de indexación
fallaban con `InvalidRequestError` de forma reproducible y persistente,
no por timing.

Fix: centralizar el import defensivo en
`app.worker.celery_app._register_all_orm_models()`, invocado (a) a nivel
de módulo apenas se importa `app.worker.celery_app` -- cubre el proceso de
backend/API y cualquier import directo de una tarea (tests, incluido este
archivo) -- y (b) vía la señal `worker_process_init` de Celery -- cubre el
proceso hijo real de un worker con pool prefork, el hook recomendado por
la propia documentación de Celery para setup post-fork.

Los dos tests de acá reproducen el escenario EXACTO que rompía las cosas
-- importar SOLO `app.worker.tasks.email` (nunca `indexing.py` ni
`maintenance.py`, que antes tenían el workaround ad-hoc) -- en un
SUBPROCESO Python fresco, no en el mismo proceso de pytest: si corriera
en el proceso de pytest, otros archivos de test ya habrían importado
medio backend durante la colección, enmascarando el bug (el registry ya
estaría bien configurado de casualidad, sin que el fix real importe)."""
import subprocess
import sys


def _run_isolated(script: str) -> subprocess.CompletedProcess:
    """Corre `script` en un proceso Python COMPLETAMENTE fresco (no el de
    pytest) -- imprescindible para que este test reproduzca de verdad el
    orden de imports que rompía las cosas, en vez de heredar lo que otros
    módulos de test ya importaron durante la colección."""
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd="/app",
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_email_task_alone_does_not_break_mapper_configuration():
    """Importar SOLO `app.worker.tasks.email` (el módulo que causó el bug
    real por no tener el workaround ad-hoc) y hacer una query ORM directa a
    `File` (que, vía `Folder`/`Tag`, necesita `User`/`Role` resueltos) no
    debe reventar `configure_mappers()` -- en un proceso fresco, sin que
    nada más haya importado `app.files.models`/`app.users.models` antes."""
    script = (
        "from app.worker.tasks.email import send_notification_email\n"
        "from app.worker.db import get_worker_db\n"
        "from app.files.models import File\n"
        "with get_worker_db() as db:\n"
        "    db.query(File).first()\n"
        "print('OK')\n"
    )
    result = _run_isolated(script)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "OK" in result.stdout


def test_email_task_then_indexing_task_same_process_regression():
    """Reproduce el ORDEN exacto que rompió producción: una tarea de
    `email.py` corre PRIMERO en el proceso (dispara `configure_mappers()`
    sin ningún workaround propio, porque ya no vive ahí) y DESPUÉS se
    invoca la tarea de indexación en el MISMO proceso -- tiene que seguir
    funcionando (no reventar con `InvalidRequestError`), sin importar que
    el archivo no exista (acá solo importa que la configuración de
    mappers no esté rota, no la extracción en sí -- eso ya lo cubre
    `test_content_indexing.py`)."""
    script = (
        "import uuid\n"
        "from app.worker.tasks.email import send_notification_email\n"
        "from app.worker.db import get_worker_db\n"
        "from app.files.models import File\n"
        "with get_worker_db() as db:\n"
        "    db.query(File).first()\n"
        "from app.worker.tasks.indexing import index_file_content\n"
        "index_file_content(None, str(uuid.uuid4()))\n"
        "print('OK')\n"
    )
    result = _run_isolated(script)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "OK" in result.stdout
