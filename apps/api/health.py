"""Liveness/readiness probes (no auth, cheap, load-balancer friendly).

- ``healthz``: process alive. Touches nothing.
- ``readyz``: default database answers ``SELECT 1``. Vector/checkpoint stores
  are lazily created at runtime, so their state is reported, never fatal.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import connections
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"})


class ReadinessCheckView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        checks = {}
        try:
            with connections["default"].cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"
        checks["chroma_dir"] = (
            "ok" if Path(settings.CHROMA_DB_DIR).exists() else "not-created-yet"
        )
        ready = checks["database"] == "ok"
        checks["status"] = "ready" if ready else "not-ready"
        return Response(checks, status=200 if ready else 503)
