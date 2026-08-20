from django.contrib import admin
from .models import User 
# Register your models here.
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display=('email', 'role', 'is_staff', 'is_active')
    search_fields=('email',)