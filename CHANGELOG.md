# Changelog

## 2.3.0

* Fixes html-escaping bug when handling tracking URLs.

## 2.1.8

### Features

* Subprocesses now log unexpected exceptions as errors


## 2.1.7

### Feature
* Cache-control header on image field, so reverse proxy can cache img views

## 2.1.6

### Bug fixes
* reply to field caused sending bug

## 2.1.4

### Bug fixes

* 404 instead of 500 whenever a Mosaico image does not exist

## 2.1.3

### Languages

* Put translations for French back into the package and update them

## 2.1.2

### Bug fixes

* `tracking_id` field from `CampaignSentEvent` models SHOULD have had an index from the beginning. Updating open and
  click statistics could become very slow.

## 2.1.1

### Bug fixes

* fix python-3.6 compatibility

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
  