# Generated by Django 2.2.23 on 2021-11-09 08:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("nuntius", "0021_create_push_campaign_models")]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="end_date",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Campaign end date"
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="start_date",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Campaign start date"
            ),
        ),
        migrations.AddField(
            model_name="pushcampaign",
            name="end_date",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Campaign end date"
            ),
        ),
        migrations.AddField(
            model_name="pushcampaign",
            name="start_date",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Campaign start date"
            ),
        ),
    ]
