# Generated by Django 2.1.5 on 2019-02-05 10:47

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("nuntius", "0005_change_status_choices")]

    operations = [
        migrations.AlterField(
            model_name="campaignsentevent",
            name="subscriber",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.NUNTIUS_SUBSCRIBER_MODEL,
                verbose_name="Subscriber",
            ),
        )
    ]