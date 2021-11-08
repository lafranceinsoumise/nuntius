import logging
import uuid
from itertools import islice
from uuid import UUID

from django.core.management import BaseCommand
from push_notifications.models import APNSDevice, GCMDevice
from tqdm import tqdm

from nuntius.models import BaseSubscriber
from standalone.models import Subscriber, Segment


class Command(BaseCommand):
    help = "Create plenty of segments and subscribers for benchmarking"

    def add_arguments(self, parser):
        parser.add_argument(
            "-q",
            "--quantity",
            dest="quantity",
            default=100_000,
            type=int,
            help="The number of subscribers to create",
        )
        parser.add_argument(
            "-b",
            "--batch_size",
            dest="batch_size",
            default=1000,
            type=int,
            help="The batch size for the subscriber creation",
        )

    def handle(self, *args, quantity=100_000, batch_size=1000, **options):
        (segment, created) = Segment.objects.get_or_create(id="fake_emails")
        subscribers = Subscriber.objects.filter(email__startswith="fake_email")

        if subscribers.exists():
            self.stdout.write(
                f"Deleting {subscribers.count()} existing fake subscribers."
            )
            subscribers.delete()

        self.stdout.write(
            f"Creating {quantity} subscriber objects with batch size {batch_size}."
        )

        batch_size = min(batch_size, quantity)
        objs = (
            Subscriber(
                email="fake_email" + str(i) + "@example.com",
                subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED,
            )
            for i in range(quantity)
        )

        with tqdm(total=quantity) as progress_bar:
            while True:
                batch = list(islice(objs, batch_size))
                if not batch:
                    break
                Subscriber.objects.bulk_create(batch, batch_size)
                progress_bar.update(batch_size)

        self.stdout.write(
            f"Creating {quantity} segment subscriptions with batch size {batch_size}."
        )
        Relation = Subscriber.segments.through
        Relation.objects.filter(segment=segment).delete()
        objs = (
            Relation(segment=segment, subscriber=subscriber)
            for subscriber in subscribers.all()
        )
        with tqdm(total=quantity) as progress_bar:
            while True:
                batch = list(islice(objs, batch_size))
                if not batch:
                    break
                Relation.objects.bulk_create(batch, batch_size)
                progress_bar.update(batch_size)

        self.stdout.write(
            f"Creating {quantity} APNS devices with batch size {batch_size}."
        )
        APNSDevice.objects.filter(
            registration_id__in=subscribers.values_list("email", flat=True)
        )
        objs = (
            APNSDevice(
                name="",
                active=True,
                device_id=uuid.uuid4(),
                registration_id=subscriber.email,
            )
            for subscriber in subscribers.all()
        )
        with tqdm(total=quantity) as progress_bar:
            while True:
                batch = list(islice(objs, batch_size))
                if not batch:
                    break
                APNSDevice.objects.bulk_create(batch, batch_size)
                progress_bar.update(batch_size)

        self.stdout.write(
            f"Creating {quantity} GCM devices with batch size {batch_size}."
        )
        GCMDevice.objects.filter(
            registration_id__in=subscribers.values_list("email", flat=True)
        )
        objs = (
            GCMDevice(
                name="",
                active=True,
                device_id=hex(subscriber.id),
                registration_id=subscriber.email,
            )
            for subscriber in subscribers.all()
        )
        with tqdm(total=quantity) as progress_bar:
            while True:
                batch = list(islice(objs, batch_size))
                if not batch:
                    break
                GCMDevice.objects.bulk_create(batch, batch_size)
                progress_bar.update(batch_size)
