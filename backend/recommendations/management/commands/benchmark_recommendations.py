## Repeatable latency checks, separate from offline quality evaluation.

import json
import random
import hashlib
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from recommendations.models import CatalogueState, Track
from recommendations.services.recommendation_service import RecommendationService


class Command(BaseCommand):
    help = "Benchmark a recommendation mode against a fixed catalogue prefix."

    def add_arguments(self, parser):
        parser.add_argument(
            "--algorithm", choices=("random", "cbf", "context_mmr"),
            required=True,
        )
        parser.add_argument("--candidate-limit", type=int)
        parser.add_argument("--history-id")
        parser.add_argument("--mood", default="happy")
        parser.add_argument("--diversity-strength", type=float, default=0.2)
        parser.add_argument("--top-n", type=int, default=10)
        parser.add_argument("--seed", type=int, default=221611)
        parser.add_argument("--warmup", type=int, default=1)
        parser.add_argument("--repeat", type=int, default=3)
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        if options["candidate_limit"] is not None and options["candidate_limit"] < 1:
            raise CommandError("--candidate-limit must be positive.")
        if options["top_n"] < 1 or options["repeat"] < 1 or options["warmup"] < 0:
            raise CommandError("--top-n and --repeat must be positive; --warmup >= 0.")
        if not 0 <= options["diversity_strength"] <= 1:
            raise CommandError("--diversity-strength must be between 0 and 1.")

        catalogue_ids = Track.objects.order_by("id").values_list("id", flat=True)
        if options["candidate_limit"] is not None:
            catalogue_ids = catalogue_ids[: options["candidate_limit"]]
        candidate_ids = list(catalogue_ids)
        if not candidate_ids:
            raise CommandError("The database contains no candidate tracks.")

        algorithm = options["algorithm"]
        history_id = options["history_id"] or candidate_ids[0]
        if algorithm != "random" and history_id not in candidate_ids:
            raise CommandError("--history-id must be in the candidate pool.")
        request_data = {
            "algorithm": algorithm,
            "history": [history_id] if algorithm != "random" else [],
            "limit": options["top_n"],
            "candidate_ids": (
                candidate_ids if options["candidate_limit"] is not None else None
            ),
            "context": (
                {
                    "mood": options["mood"],
                    "diversity_strength": options["diversity_strength"],
                }
                if algorithm == "context_mmr" else {}
            ),
        }
        timings_ms = []
        response = None
        for index in range(options["warmup"] + options["repeat"]):
            service = RecommendationService(random_source=random.Random(options["seed"]))
            started = perf_counter()
            response = service.recommend(request_data)
            wall_ms = (perf_counter() - started) * 1000
            if index >= options["warmup"]:
                timings_ms.append(round(wall_ms, 3))

        state = CatalogueState.objects.filter(pk=1).first()
        report = {
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "database_engine": connection.settings_dict["ENGINE"],
            "algorithm": algorithm,
            "catalogue_version": (
                state.version if state else response["meta"]["catalogue_version"]
            ),
            "catalogue_sha256": state.catalogue_sha256 if state else None,
            "candidate_count": response["meta"]["candidate_count"],
            "candidate_limit": options["candidate_limit"],
            "candidate_ids_sha256": hashlib.sha256(
                "\n".join(candidate_ids).encode("utf-8")
            ).hexdigest(),
            "history_id": history_id if algorithm != "random" else None,
            "mood": options["mood"] if algorithm == "context_mmr" else None,
            "diversity_strength": (
                options["diversity_strength"] if algorithm == "context_mmr" else None
            ),
            "top_n": options["top_n"],
            "seed": options["seed"],
            "warmup": options["warmup"],
            "repeat": options["repeat"],
            "wall_times_ms": timings_ms,
            "median_ms": round(median(timings_ms), 3),
            "min_ms": min(timings_ms),
            "max_ms": max(timings_ms),
            "returned_ids": [
                item["track"]["id"] for item in response["recommendations"]
            ],
        }
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if options["output"]:
            output = options["output"]
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
        self.stdout.write(rendered)
