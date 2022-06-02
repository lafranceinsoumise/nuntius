# Generated by Django 2.1.5 on 2019-01-25 08:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("nuntius", "0003_allow_no_segments")]

    operations = [
        migrations.AddField(
            model_name="campaignsentevent",
            name="esp_message_id",
            field=models.CharField(
                max_length=254,
                null=True,
                unique=True,
                verbose_name="ID given by the sending server",
            ),
        ),
        migrations.AlterField(
            model_name="campaignsentevent",
            name="email",
            field=models.EmailField(
                max_length=254, verbose_name="Email address at event time"
            ),
        ),
        migrations.AlterField(
            model_name="campaignsentevent",
            name="result",
            field=models.CharField(
                choices=[
                    ("P", "Sending"),
                    ("RE", "Refused by server"),
                    ("OK", "Sent"),
                    ("BC", "Bounced"),
                    ("C", "Complained"),
                    ("BL", "Blocked"),
                ],
                default="P",
                max_length=2,
                verbose_name="Operation result",
            ),
        ),
    ]