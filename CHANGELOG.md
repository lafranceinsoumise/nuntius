# Changelog

## 2.1.0

* Feature : add settings `NUNTIUS_DEFAULT_FROM_EMAIL`, `NUNTIUS_DEFAULT_FROM_NAME`,
`NUNTIUS_DEFAULT_REPLY_TO_EMAIL`, and `NUNTIUS_DEFAULT_REPLY_TO_NAME`.
* Fix a bug where webhook would error when ISP normalized email.

## 2.0.1

### Bug fixes

* Fix a bug where the admin still had some references to celery tasks and would crash

## 2.0.0

### Breaking changes

* Nuntius does not depend on celery anymore, and the old way of sending emails through celery tasks is gone. It means
  that the old `NUNTIUS_CELERY_BROKER` setting is obsolete.
  
### Features

* Nuntius now has a dedicated worker command that will start up a process responsible for sending campaigns. That
  process starts up several processes to send emails and is much faster. See the documentation on how to configure.
  