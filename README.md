# Nuntius

Nuntius is a newsletter application for Django.

Nuntius integrates with your Django project.
It is very agnostic about your subscribers and subscriber lists models.

It features [Mosaico](https://mosaico.io/), a drag-and-drop email
editor, for sending beautiful emails to your subscribers.

## How it works

Nuntius is agnostic about your subscribers model. You can use your current
use model, as long as it implements a few required methods.

To allow your end-users to choose recipients, it is your choice to implement
one or more "segment" models. Segment models implement a required method
`get_subscribers_queryset`.

You can then create campaigns in the Django admin panel, and send them to
existing segments.

Celery is used to queue and send emails. Nuntius must have its own celery worker.

## Installation

1. Add "nuntius" to your INSTALLED_APPS setting like this:
    ````python
        INSTALLED_APPS = [
            'django.contrib.admin',
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
            ...
            'nuntius',
        ]
    ````
2. Include Nuntius urlconf in your project `urls.py` like this:
    ````python
        path('nuntius/', include('nuntius.urls')),
    ````
3. Edit or create your subscriber model so it works with Nuntius.
   You must implement all the method from `nuntius.models.BaseSubscriber`.
   An easy way to do this is to extend `BaseSubscriber` and to have a
   `subscriber_status` `IntegerField` and an `email` `EmailField`, but
   you can implement the methods the way you want.
   
   Here is the `BaseSubscriber` code as documentation :
   
    ````python
    # nuntius.models.BaseSubscriber

    class BaseSubscriber:
        STATUS_SUBSCRIBED = 1
        STATUS_UNSUBSCRIBED = 2
        STATUS_BOUNCED = 3
        STATUS_COMPLAINED = 4
        STATUS_CHOICES = (
            (STATUS_SUBSCRIBED, _("Subscribed")),
            (STATUS_UNSUBSCRIBED, _("Unsubscribed")),
            (STATUS_BOUNCED, _("Bounced")),
            (STATUS_COMPLAINED, _("Complained"))
        )

        def get_subscriber_status(self):
            if hasattr(self, 'subscriber_status'):
                return self.subscriber_status
            raise NotImplementedError()

        def get_subscriber_email(self):
            if hasattr(self, 'email'):
                return self.email

            raise NotImplementedError()

        def get_subscriber_data(self):
            return {
                'email': self.email
            }
    ````
    
    Here is an example of a subscriber model you can implement :
    
    ````python
    # myapp.models.MySubscriberModel
    from nuntius.models import BaseSubscriber
    from django.db import models
    from django.db.models import fields
    
    class MySubscriberModel(BaseSubscriber, models.Model):
       email = fields.EmailField(max_length=255)
       subscriber_status = fields.IntegerField(choices=BaseSubscriber.STATUS_CHOICES)
 
4. Set the two required settings in your `settings.py`
    ````python
    NUNTIUS_SUBSCRIBER_MODEL = 'myapp.MySubscriberModel'
    NUNTIUS_CELERY_BROKER_URL = 'redis://'
    ````

5. Launch Redis and celery in the background. In production, you should probably use systemd for this.
    The command for celery should be something like this :
    ```python
    export DJANGO_SETTINGS_MODULE=myapp.settings
    celery -A nuntius.celery worker
    ```

Unless you are using a custom admin site, admin panels for Nuntius will be
[autodiscovered](https://docs.djangoproject.com/en/2.0/ref/contrib/admin/#discovery-of-admin-files)
and added to you admin site.

## Advanced usage

If you want to have more control on your recipients, you can create
segment models.

One example of segment is a simple model which holds a Many-to-Many relation
to subscribers. In this case, the segment can be considered as a list.

Another example is a segment model which filters subscribers depending on
the date of their last login :

```python
from django.db import models
from django.db.models import fields
from datetime import datetime

from nuntius.models import BaseSegment


class LastLoginDateSegment(BaseSegment, models.Model):
     last_login_duration = fields.DurationField()
     
     def get_display_name(self):
         return f'Last login : {str(datetime.now() - self.last_login_duration)}'
         
     def get_subscribers_queryset(self):
        return MySubscriberClass.objects.filter(last_login__gt=datetime.now() - self.last_login_duration)
        
     def get_subscribers_count(self):
        return MySubscriberClass.objects.filter(last_login__gt=datetime.now() - self.last_login_duration, subscribed=True)

```
 
* `get_subscribers_queryset` is allowed to return subscribers regardless of their
    `subscriber_status`, as `get_subscriber_status` will be called on each instance.
* `get_subscribers_count` is only there for convenience in the admin panel, it does not
    have to be accurate. If you want to have it accurate, you should however take
    your subscribers status into account.

## License

Copyright is owned by Guillaume Royer and Arthur Cheysson.

You can use Nuntius under GPLv3 terms.
