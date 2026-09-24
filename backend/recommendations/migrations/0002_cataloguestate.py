from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CatalogueState",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, primary_key=True, serialize=False
                    ),
                ),
                ("version", models.CharField(max_length=100)),
                ("catalogue_sha256", models.CharField(max_length=64)),
                ("record_count", models.PositiveIntegerField()),
                ("imported_at", models.DateTimeField(auto_now=True)),
                ("import_mode", models.CharField(max_length=20)),
            ],
        ),
        migrations.AddConstraint(
            model_name="cataloguestate",
            constraint=models.CheckConstraint(
                condition=models.Q(id=1), name="single_catalogue_state"
            ),
        ),
    ]
