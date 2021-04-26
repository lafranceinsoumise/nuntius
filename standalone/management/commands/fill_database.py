from itertools import islice

from django.core.management import BaseCommand
from tqdm import tqdm

from nuntius.models import BaseSubscriber
from standalone.models import Subscriber, Segment


class Command(BaseCommand):
    help = "Loads plenty of fake emails for benchmark"

    def handle(self, *args, **options):
        (segment, created) = Segment.objects.get_or_create(id="fake_emails")
        fake_emails = Subscriber.objects.filter(email__startswith="fake_email")
        fake_emails.all().delete()

        batch_size = 1000

        objs = (
            Subscriber(
                email="fake_email" + str(i) + "@example.com",
                subscriber_status=BaseSubscriber.STATUS_SUBSCRIBED,
            )
            for i in range(100000)
        )

        with tqdm(total=100000) as pbar:
            while True:
                batch = list(islice(objs, batch_size))
                if not batch:
                    break
                Subscriber.objects.bulk_create(batch, batch_size)
                pbar.update(batch_size)

        Relation = Subscriber.segments.through
        Relation.objects.filter(testsegment=segment).delete()

        objs = (
            Relation(testsegment=segment, testsubscriber=test_subscriber)
            for test_subscriber in fake_emails.all()
        )

        with tqdm(total=100000) as pbar:
            while True:
                batch = list(islice(objs, batch_size))
                if not batch:
                    break
                Relation.objects.bulk_create(batch, batch_size)
                pbar.update(batch_size)
