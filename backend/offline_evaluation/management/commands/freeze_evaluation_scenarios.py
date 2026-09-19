from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from offline_evaluation.freeze import freeze_scenarios
from offline_evaluation.protocol import ProtocolValidationError


class Command(BaseCommand):
    help = "Freeze the user-accepted scenario draft and preserve its caveats."

    def add_arguments(self, parser):
        parser.add_argument("--approval-date", required=True)
        parser.add_argument("--evaluation-dir", default="evaluation")

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).parent.resolve()
        evaluation_dir = Path(options["evaluation_dir"])
        if not evaluation_dir.is_absolute():
            evaluation_dir = project_root / evaluation_dir
        try:
            result = freeze_scenarios(
                project_root=project_root,
                evaluation_dir=evaluation_dir,
                approval_date=options["approval_date"],
            )
        except (OSError, KeyError, ValueError, ProtocolValidationError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS("Evaluation scenarios frozen."))
        self.stdout.write(str(result))
