# Generated by Django 3.1.1 on 2020-09-14 07:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("nuntius", "0017_campaign_utm_name")]

    operations = [migrations.RemoveField(model_name="campaign", name="task_uuid")]
