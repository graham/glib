from django.db import models

class AppFeedback(models.Model):
    user_email = models.CharField(max_length=512)
    app = models.CharField(max_length=128)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


# Create your models here.
class UserProfile(models.Model):
    user_email = models.CharField(max_length=512)
    app = models.CharField(max_length=128)
    mode = models.CharField(max_length=64, default='live')
    active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user_email', 'app', 'mode'])
        ]

    @staticmethod
    def profile_for_app(request, app_name):
        up = UserProfile.objects.filter(
            active=True,
            user_email=request.user.email,
            app=app_name
        ).first()

        if up is None:
            up = UserProfile(
                active=True,
                user_email=request.user.email,
                app=app_name
            )
            up.save()

        return up


class UserCredit(models.Model):
    user_email = models.CharField(max_length=512)    
    amount = models.IntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    origin = models.CharField(max_length=128)


class UserSubscription(models.Model):
    user_email = models.CharField(max_length=512)    
    app = models.CharField(max_length=128)
    cost_per_cycle = models.IntegerField(default=1)
    plan = models.CharField(max_length=128)
    start_date = models.DateField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user_email', 'app'])
        ]
