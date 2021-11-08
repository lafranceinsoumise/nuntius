# Generated by Django 2.2.23 on 2021-11-09 05:08

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import nuntius.models.mixins
import nuntius.models.push_campaigns


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.NUNTIUS_SEGMENT_MODEL),
        migrations.swappable_dependency(settings.NUNTIUS_SUBSCRIBER_MODEL),
        ("nuntius", "0020_auto_20210118_1100"),
    ]

    operations = [
        migrations.CreateModel(
            name="PushCampaign",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=255, verbose_name="Name (invisible to subscribers)"
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created"),
                ),
                (
                    "updated",
                    models.DateTimeField(auto_now=True, verbose_name="Updated"),
                ),
                (
                    "first_sent",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="First sent"
                    ),
                ),
                (
                    "status",
                    models.IntegerField(
                        choices=[
                            (0, "Waiting"),
                            (1, "Sending"),
                            (2, "Sent"),
                            (3, "Error"),
                        ],
                        default=0,
                    ),
                ),
                (
                    "utm_name",
                    models.CharField(
                        blank=True,
                        help_text="Value used as utm_campaign parameter, used by various analytics tools.",
                        max_length=255,
                        verbose_name="UTM name (visible to subscribers)",
                    ),
                ),
                (
                    "signature_key",
                    models.BinaryField(
                        default=nuntius.models.mixins.AbstractCampaign.generate_signature_key,
                        max_length=20,
                    ),
                ),
                (
                    "notification_title",
                    models.CharField(max_length=255, verbose_name="Notification title"),
                ),
                (
                    "notification_url",
                    models.CharField(max_length=255, verbose_name="Notification URL"),
                ),
                (
                    "notification_body",
                    models.TextField(verbose_name="Notification body"),
                ),
                (
                    "notification_tag",
                    models.CharField(
                        blank=True,
                        max_length=255,
                        null=True,
                        verbose_name="Notification tag",
                    ),
                ),
                (
                    "notification_icon",
                    models.CharField(
                        blank=True,
                        max_length=255,
                        null=True,
                        verbose_name="Notification icon",
                    ),
                ),
                (
                    "segment",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.NUNTIUS_SEGMENT_MODEL,
                        verbose_name="Subscriber segment",
                    ),
                ),
            ],
            options={
                "verbose_name": "push campaign",
                "verbose_name_plural": "push campaigns",
            },
            bases=(nuntius.models.mixins.CampaignStatusType, models.Model),
        ),
        migrations.AlterModelOptions(
            name="campaign",
            options={
                "verbose_name": "email campaign",
                "verbose_name_plural": "email campaigns",
            },
        ),
        migrations.AlterModelOptions(
            name="campaignsentevent",
            options={
                "ordering": ["-datetime"],
                "verbose_name": "email sent event",
                "verbose_name_plural": "email sent events",
            },
        ),
        migrations.CreateModel(
            name="PushCampaignSentEvent",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "datetime",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Sending time"
                    ),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[
                            ("?", "Unknown"),
                            ("P", "Sending"),
                            ("OK", "Sent"),
                            ("E", "Error"),
                        ],
                        default="P",
                        max_length=2,
                        verbose_name="Operation result",
                    ),
                ),
                (
                    "tracking_id",
                    models.CharField(
                        default=nuntius.models.push_campaigns.PushCampaignSentEvent.generate_tracking_id,
                        editable=False,
                        max_length=12,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    "click_count",
                    models.IntegerField(
                        default=0, editable=False, verbose_name="Click count"
                    ),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="nuntius.PushCampaign",
                        verbose_name="Push campaign",
                    ),
                ),
                (
                    "subscriber",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.NUNTIUS_SUBSCRIBER_MODEL,
                        verbose_name="Subscriber",
                    ),
                ),
            ],
            options={
                "verbose_name": "push sent event",
                "verbose_name_plural": "push sent events",
                "ordering": ["-datetime"],
            },
        ),
        migrations.AddIndex(
            model_name="pushcampaignsentevent",
            index=models.Index(
                fields=["subscriber", "datetime"], name="nuntius_pus_subscri_9ce7a8_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="pushcampaignsentevent",
            constraint=models.UniqueConstraint(
                fields=("campaign", "subscriber"),
                name="unique_push_campaign_subscriber",
            ),
        ),
    ]
