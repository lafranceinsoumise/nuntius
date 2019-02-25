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
3. Define your subscriber model so it works with Nuntius.
   You must inherit from
   [`nuntius.models.AbstractSubscriber`](https://github.com/lafranceinsoumise/nuntius/blob/master/nuntius/models.py#L174)
   and implement all the necessary methods. An easy way to do this is to use directly or to extend
   [`BaseSubscriber`](https://github.com/lafranceinsoumise/nuntius/blob/master/nuntius/models.py#L204), but
   you can implement the methods of `AbstractSubscriber` the way you want.
    
    Here are the methods you must implement :
    
    * `get_subscriber_status()`
        must return one of `AbstractSubscriber.STATUS_CHOICES`. You can also simply
        define a `subscriber_status` attribute.
        
    * `get_subscriber_email()`
        must return a unique email address for the subscriber. You can also simply
        define an `email` attribute.

    * `get_subscriber_data()`
        must return the dictionnary of values which can be used as substitution in
        the emails. Default is `{"email": self.get_subscriber_email()}`.
 
4. Set the two required settings in your `settings.py`
    ````python
    NUNTIUS_SUBSCRIBER_MODEL = 'myapp.MySubscriberModel'
    NUNTIUS_CELERY_BROKER_URL = 'redis://'
    ````

5. Launch Redis and celery in the background. In production, you should probably use systemd for this.
    The command for celery should be something like this :
    ```python
    export DJANGO_SETTINGS_MODULE=myapp.settings
    celery -A nuntius.celery worker -Q nuntius
    ```

    Be careful if you have your own celery app in your project using the same broker.
    You should have two separate workers for your tasks and for Nuntius tasks,
    because Nuntius worker needs a special configuration to allow Nuntius to report
    correctly sendig state.

    Your worker for your project tasks should explicitely
    take tasks only from the default queue or any other queue you define:
    ```python
    celery -A myapp.celery worker -Q default
    ```

6.  Unless you are using a custom admin site, admin panels for Nuntius will be
[autodiscovered](https://docs.djangoproject.com/en/2.0/ref/contrib/admin/#discovery-of-admin-files)
and added to you admin site.

## Advanced usage

### List segments

If you want to have more control on your recipients, you can create
segment models.

One example of segment is a simple model which holds a Many-to-Many relation
to subscribers.

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

Then, add your segment model(s) to Nuntius settings :
````python
NUNTIUS_SEGMENT_MODELS = ['myapp.lastlogindatesegment']
````

### Custom template

You can write your own Mosaico template to fit your needs. To make it available in the admin,
list the public URL path of the template in `NUNTIUS_MOSAICO_TEMPLATES`. The template can be served
by Django static files system, or any other way at your preference.

```python
NUNTIUS_MOSAICO_TEMPLATES = [
    ("/static/mosaico_templates/versafix-2/template-versafix-2.html", "Custom template")
]
```

### ESP and Webhooks

Maintaining your own SMTP server to send your newsletter is probably
a bad idea if you have more than a few subscribers. You can use
[Anymail](https://github.com/anymail/django-anymail) along with Nuntius
in order to use an email service provider. Anymail supports
a lot of ESP, like Amazon SES, Mailgun, Mailjet, Postmark, SendGrid,
SendinBlue, or SparkPost.

Refer to the steps in [Anymail 1-2-3](https://anymail.readthedocs.io/en/stable/quickstart/)
to install Anymail. If you want to configure Anymail just for Nuntius and keep
the default email backend for other usage, you can use the setting `NUNTIUS_EMAIL_BACKEND`
rather than the default `EMAIL_BACKEND`.

In addition, configuring Nuntius with Anymail will allow you to use ESP tracking features
and to track status of your email once it is sent.

#### Webhooks

Configuring webhhoks allows Nuntius to track email status and to
give you statistics on campaign, as well as updating subscriber status
when they bounce.

1. Configure email tracking as described in
[Anymail documentation](https://anymail.readthedocs.io/en/stable/installation/#configuring-tracking-and-inbound-webhooks).
2. Implement the method `set_subscriber_status(self, email, status)` on your subscriber
model manager.

Nuntius will automatically listen to Anymail signals and call this method approprietly.


## License

Copyright is owned by Guillaume Royer and Arthur Cheysson.

You can use Nuntius under GPLv3 terms.
