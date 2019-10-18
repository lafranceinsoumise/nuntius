# Generated by Django 2.2.5 on 2019-10-22 07:34

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("nuntius", "0015_only_one_segment_model")]

    operations = [
        migrations.AlterModelOptions(
            name="campaignsentevent",
            options={
                "ordering": ["-datetime"],
                "verbose_name": "Sent event",
                "verbose_name_plural": "Sent events",
            },
        ),
        migrations.AlterField(
            model_name="campaignsentevent",
            name="campaign",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="nuntius.Campaign",
                verbose_name="Campaign",
            ),
        ),
        migrations.AlterField(
            model_name="campaignsentevent",
            name="datetime",
            field=models.DateTimeField(
                auto_now_add=True, db_index=True, verbose_name="Sending time"
            ),
        ),
        migrations.AlterField(
            model_name="campaignsentevent",
            name="email",
            field=models.EmailField(
                db_index=True,
                max_length=254,
                verbose_name="Email address at sending time",
            ),
        ),
        migrations.AddIndex(
            model_name="campaignsentevent",
            index=models.Index(
                fields=["email", "datetime"], name="nuntius_cam_email_04da96_idx"
            ),
        ),
    ]
