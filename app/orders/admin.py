from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ['producto']
    readonly_fields = ('subtotal',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('numero', 'vendedor', 'cliente', 'estado', 'total', 'metodo_pago', 'creado')
    list_filter = ('estado', 'metodo_pago', 'creado')
    search_fields = ('numero', 'cliente', 'notas')
    date_hierarchy = 'creado'
    inlines = [OrderItemInline]
    readonly_fields = ('numero', 'subtotal', 'total', 'creado', 'actualizado')
