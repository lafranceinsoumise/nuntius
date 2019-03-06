# Generated by Django 2.1.7 on 2019-03-06 11:24

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("nuntius", "0008_campaign_first_sent")]

    operations = [
        migrations.AlterField(
            model_name="campaign",
            name="created",
            field=models.DateTimeField(auto_now_add=True, verbose_name="Created"),
        ),
        migrations.AlterField(
            model_name="campaign",
            name="first_sent",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="First sent"
            ),
        ),
        migrations.AlterField(
            model_name="campaign",
            name="updated",
            field=models.DateTimeField(auto_now=True, verbose_name="Updated"),
        ),
        migrations.AlterField(
            model_name="campaignsentevent",
            name="campaign",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="Campagne",
                to="nuntius.Campaign",
            ),
        ),
    ]
