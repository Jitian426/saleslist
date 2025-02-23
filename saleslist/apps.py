from django.apps import AppConfig


class SaleslistConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'saleslist'

    def ready(self):
        print("🔹 SaleslistConfig がロードされました")