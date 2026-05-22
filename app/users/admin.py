from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'rol', 'telefono', 'activo', 'creado')
    list_filter = ('rol', 'activo')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'documento')
    list_select_related = ('user',)
