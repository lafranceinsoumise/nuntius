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
 
4. Tell Nuntius how to find your subscriber model in `settings.py`
    ````python
    NUNTIUS_SUBSCRIBER_MODEL = 'myapp.MySubscriberModel'
    ````

5. Launch the nuntius worker in the background. In a production setting, this should be done through
   a process monitor like upstart or systemd.
    ```shell script
    export DJANGO_SETTINGS_MODULE=myapp.settings
    python ./manage.py nuntius_worker
    ```

6.  Unless you are using a custom admin site, admin panels for Nuntius will be
[autodiscovered](https://docs.djangoproject.com/en/2.0/ref/contrib/admin/#discovery-of-admin-files)
and added to you admin site. If you use a custom admin site, you need to register
Nuntius models with something like:

    ```python
    admin_site.register(nuntius.models.Campaign, nuntius.admin.CampaignAdmin)
    admin_site.register(nuntius.models.CampaignSentEvent, nuntius.admin.CampaignSentEventAdmin)
    ```

## Other settings
Use `NUNTIUS_DEFAULT_FROM_EMAIL`, `NUNTIUS_DEFAULT_FROM_NAME`, `NUNTIUS_DEFAULT_REPLY_TO_EMAIL`,
`NUNTIUS_DEFAULT_REPLY_TO_NAME` to change default field values in the admin form.

## Advanced usage

### List segments

If you want to have more control on your recipients, you can create a
segment model.

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

Then, add your segment model to Nuntius settings :
````python
NUNTIUS_SEGMENT_MODEL = 'myapp.lastlogindatesegment'
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

### Sending parameters

The worker will spawn several subprocesses to speed up the sending of campaigns. The number of
processes that will send emails concurrently can be configured using the `NUNTIUS_MAX_CONCURRENT_SENDERS`
setting.

Most ESP enforce a maximum send rate. Nuntius won't sent messages faster than`NUNTIUS_MAX_SENDING_RATE`,
in messages per second.

When using SMTP, some ESP limit the number of emails that can be sent using a single connection.
`NUNTIUS_MAX_MESSAGES_PER_CONNECTION` will force Nuntius to reset the connection after sending that
many messages.

The Nuntius worker checks every `NUNTIUS_POLLING_INTERVAL` seconds if any sending has been scheduled
or canceled. The default value of 2 seconds should be find for most usages.

To help you configure these parameters, you can send SIGUSR1 to the main worker process and it will
print sending statistics on `stderr`. Pay special attention to the current sending rate and to the
current bucket capacity: if your sending rate is lower than the maximum you configured, it most
likely means the value you chose for `NUNTIUS_MAX_CONCURRENT_SENDERS` is not high enough given
the latency you're getting with your ESP.

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

Nuntius will automatically listen to Anymail signals and call this method if needed.

##### Handling of non-nuntius events (optional)

If you send emails to your subscribers by other means than Nuntius (for example,
transactional emails), you will receive webhooks events which are not related to
a campaign you sent. By default, Nuntius will create a campaign result event recording
the email and the event type, but it will not link it to a campaign nor to a subscriber
model.

If you want your events to always be linked to a subscriber model, you must implement
a `get_subscriber(self, email_address)` method on your subscriber model manager.


##### BaseSubscriberManager

Nuntius is packaged with a BaseSubscriberManager, which implements both
`set_subscriber_status` and `get_subscriber`, assuming you have an `email` field
on your subscriber model. This is the default manager used by `BaseSubscriber`.


#### Bounce handling

Most ESP gives you a reputation based on your hard bounce rate.
Mosaico handles bounces smartly to change your subscribers status
when necessary.

If Nuntius receive a bounce event on an email address which has no
other sending event, `set_subscriber_status(email, status)` is called
with `AbstractSubscriber.STATUS_BOUNCED`.

If a successful sending event exists for this address,
three parameters are taken into account :
* if during the last `duration` days, there has been no more bounces than `limit`
and at least one successful sending, no action is taken
* if there has been at least one successful sending in the last
`consecutive` events, no action is taken
* otherwise, `set_subscriber_status(email, status)` is called
with `AbstractSubscriber.STATUS_BOUNCED`


You can change thoses default values :
```python
NUNTIUS_BOUNCE_PARAMS = {
    "consecutive": 1,
    "duration": 7,
    "limit": 3
}
```

**Example :**

* You send 3 campaigns a week. After a few months, a subscriber
has a full mailbox. On first and second bounced campaign, no action
is taken because there is a successful sending in the last 7 days,
and no more than 3 bounces. On the third campaign, if the user has empty
their mailbox, everything is fine. Otherwise, the subscriber is marked
as permanently bounced.
* You send one campaign a day. A user has a buggy email server.
This week, the user has already 3 bounces. When you receive the 4th
bounce, if there has been a successful sending just before,
everything is fine. Otherwise, the subscriber is marked
as permanently bounced.

## Tracking

Opening and clicks are tracked by adding a white pixel and replacing links in emails.

Nuntius also adds [UTM parameters](https://en.wikipedia.org/wiki/UTM_parameters) to every URL with the following values:
* `utm_source`: *"nuntius"*
* `utm_medium`: *"email"*
* `utm_campaign`: value configured by user at the campaign level
* `utm_content`: *"link-{number}"* based on the link position in the email
* `utm_term`: attribute `utm_term` of the segment object, or empty string if attribute does not exist

In some situations, two details may be important for you:

1. `utm_campaign`, `utm_content`, and `utm_term`, those are just defaults values, and can also be set directly on
the link. `utm_source` and `utm_medium` will always be overwritten.
2. `utm_content` and `utm_term` are set at sending time and cannot change afterwards. `utm_campaign` is
set at click time, during the redirection from nuntius tracking URL to target URL, so if you change the value
at the campaign level after sending, the value will change for all new clicks.

## License

Copyright is owned by Jill Royer and Arthur Cheysson.

You can use Nuntius under GPLv3 terms.
