from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recommendations", "0003_track_genres_and_suggestions")]

    operations = [
        migrations.AddField(
            model_name="tracksuggestion",
            name="album_name",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
