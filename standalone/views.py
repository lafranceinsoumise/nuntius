from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from push_notifications.models import GCMDevice

from firebase_admin import messaging

def envoyer_notification_push(request):
    """
    Endpoint de test pour vérifier le fonctionnement de Firebase avec Android et iOS
    :param request:
    """
    device_token = request.GET.get('token')
    titre = request.GET.get('titre', 'Notification')
    message = request.GET.get('message', 'Ceci est une notification push.')

    # Message struct https://firebase.google.com/docs/reference/fcm/rest/v1/projects.messages#Message.FIELDS.data
    fcm_message = messaging.Message(
        notification=messaging.Notification(
            title=titre,
            body=message,
            image="https://media.actionpopulaire.fr/activity/announcements/SY/9633aaa4-9e5f-4b8e-a714-4d82faac065d.mobile.jpg"
        ),
        android=messaging.AndroidConfig(
            ttl=259200,
        ),
        apns=messaging.APNSConfig(
            headers={
                "apns-expiration": str(259200),
            }
        )
    )

    try:
        print("Getting device")
        device = GCMDevice.objects.get(registration_id=device_token)
    except ObjectDoesNotExist:
        device = GCMDevice.objects.create(
        name="Test phone",
        active=True,
        registration_id=device_token)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    if device_token:
        try:
            device.send_message(fcm_message)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        return JsonResponse({'status': 'success', 'message': 'Message send'}, status=200)
